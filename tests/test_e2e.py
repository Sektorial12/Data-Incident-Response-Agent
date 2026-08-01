"""End-to-end integration test for the full incident response pipeline.

Simulates an assertion failure event flowing through the entire pipeline:
Coordinator -> Tracer -> Checker -> Notifier -> Reporter
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.agents.checker import CheckerAgent, ValidationStatus
from src.agents.notifier import NotifierAgent
from src.agents.reporter import ReporterAgent
from src.agents.tracer import TracerAgent
from src.coordinator import CoordinatorAgent
from src.datahub_actions_plugin.incident_event import IncidentEvent
from src.mcp_client.client import MCPClient

logging.disable(logging.CRITICAL)

DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)"
UPSTREAM_1 = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.staging_patients,PROD)"
UPSTREAM_2 = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)"
ASSERTION_URN = "urn:li:assertion:billingAmountPositive"


def make_incident() -> IncidentEvent:
    return IncidentEvent(
        assertion_urn=ASSERTION_URN,
        dataset_urn=DATASET_URN,
        assertion_type="DATASET_ROWS",
        result_status="FAILED",
        timestamp_ms=1700000000000,
        error_message="billing_amount has negative values",
    )


def make_full_mcp_mock() -> MagicMock:
    """Create an MCP mock that simulates real DataHub responses."""
    mcp = MagicMock(spec=MCPClient)

    # Tracer: get_lineage returns upstream nodes
    mcp.get_lineage.return_value = {
        "relationships": [{"urn": UPSTREAM_1}, {"urn": UPSTREAM_2}],
        "entities": [{"urn": UPSTREAM_1}, {"urn": UPSTREAM_2}],
    }

    # Tracer/Checker: get_entities returns metadata
    def get_entities_side_effect(urns):
        result = {"entities": []}
        for urn in urns:
            if urn == UPSTREAM_1:
                aspects = [{"name": "assertionRunEvents"}, {"name": "schemaMetadata"}]
            elif urn == UPSTREAM_2:
                aspects = []
            else:
                aspects = []
            result["entities"].append({"urn": urn, "name": urn, "aspects": aspects})
        return result

    mcp.get_entities.side_effect = get_entities_side_effect

    mcp.list_schema_fields.return_value = {"fields": [{"fieldPath": "patient_id"}, {"fieldPath": "billing_amount"}]}

    # Tracer: get_lineage_paths_between
    mcp.get_lineage_paths_between.return_value = {"paths": [[UPSTREAM_1, DATASET_URN]]}

    # Checker: search returns some docs
    mcp.search.return_value = {"entities": [{"urn": "urn:li:document:doc1"}]}

    # Reporter: save_document returns URN
    mcp.save_document.return_value = {"urn": "urn:li:document:incident-001"}

    # Reporter: add_tags succeeds
    mcp.add_tags.return_value = {"success": True}

    return mcp


class TestE2EPipeline:
    """Full pipeline integration test with all agents wired."""

    def test_full_pipeline_completes_all_agents(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())

        assert "agents" in result
        assert result["agents"]["tracer"]["status"] == "completed"
        assert result["agents"]["checker"]["status"] == "completed"
        assert result["agents"]["notifier"]["status"] == "completed"
        assert result["agents"]["reporter"]["status"] == "completed"
        assert "elapsed_seconds" in result

    def test_tracer_finds_candidates(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        tracer_result = result["agents"]["tracer"]["result"]
        candidates = tracer_result["candidates"]
        assert len(candidates) >= 1
        assert any(c["urn"] == UPSTREAM_1 for c in candidates)

    def test_checker_validates_candidates(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        checker_result = result["agents"]["checker"]["result"]
        validated = checker_result["validated_candidates"]
        # UPSTREAM_1 has assertionRunEvents aspect → should be validated
        assert any(v["candidate_urn"] == UPSTREAM_1 for v in validated)

    def test_notifier_formats_alert(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        notifier_result = result["agents"]["notifier"]["result"]
        assert "alert_text" in notifier_result
        assert "mart_billing" in notifier_result["alert_text"]

    def test_reporter_saves_document(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        reporter_result = result["agents"]["reporter"]["result"]
        assert reporter_result["document_urn"] == "urn:li:document:incident-001"
        assert reporter_result["report_length"] > 100

    def test_reporter_tags_root_cause(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        coordinator.handle_incident(make_incident())
        mcp.add_tags.assert_called()
        call_args = mcp.add_tags.call_args
        tag_urns = call_args.kwargs.get("tag_urns") if call_args.kwargs else call_args[0].get("tag_urns", [])
        assert "urn:li:tag:incident-root-cause" in tag_urns

    def test_pipeline_survives_agent_failure(self):
        """If tracer fails, downstream agents should still run with empty data."""
        mcp = make_full_mcp_mock()
        mcp.get_lineage.side_effect = RuntimeError("lineage unavailable")

        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        assert result["agents"]["tracer"]["status"] == "failed"
        # Checker should still run (with empty candidates)
        assert result["agents"]["checker"]["status"] == "completed"
        # Notifier and Reporter should still run
        assert result["agents"]["notifier"]["status"] == "completed"
        assert result["agents"]["reporter"]["status"] == "completed"

    def test_pipeline_survives_reporter_failure(self):
        """If reporter fails, other agents should have completed."""
        mcp = make_full_mcp_mock()
        mcp.save_document.side_effect = RuntimeError("write failed")

        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        assert result["agents"]["tracer"]["status"] == "completed"
        assert result["agents"]["checker"]["status"] == "completed"
        assert result["agents"]["notifier"]["status"] == "completed"
        # Reporter should still complete (error handled internally)
        assert result["agents"]["reporter"]["status"] == "completed"
        assert result["agents"]["reporter"]["result"]["document_urn"] is None

    def test_elapsed_time_recorded(self):
        mcp = make_full_mcp_mock()
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
            checker=CheckerAgent(mcp),
            notifier=NotifierAgent(mcp, config={"slack_webhook_url": ""}),
            reporter=ReporterAgent(mcp),
        )

        result = coordinator.handle_incident(make_incident())
        assert result["elapsed_seconds"] >= 0
        assert isinstance(result["elapsed_seconds"], float)
