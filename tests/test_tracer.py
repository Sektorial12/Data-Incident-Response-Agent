"""Tests for the Tracer Agent."""

import logging
from unittest.mock import MagicMock

from src.agents.protocol import AgentMessage
from src.agents.tracer import CandidateRootCause, TracerAgent
from src.mcp_client.client import MCPClient

logging.disable(logging.CRITICAL)

DATASET_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)"
)
UPSTREAM_URN_1 = (
    "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.staging_patients,PROD)"
)
UPSTREAM_URN_2 = (
    "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)"
)


def make_message(dataset_urn: str = DATASET_URN) -> AgentMessage:
    return AgentMessage(
        from_agent="coordinator",
        to_agent="tracer",
        task="investigate_incident",
        context={"dataset_urn": dataset_urn, "max_hops": 3},
    )


def make_mcp_mock(
    lineage_nodes: list[str] | None = None,
    entity_info: dict | None = None,
    schema_fields: int = 0,
) -> MagicMock:
    mcp = MagicMock(spec=MCPClient)
    if lineage_nodes is None:
        lineage_nodes = [UPSTREAM_URN_1, UPSTREAM_URN_2]

    mcp.get_lineage.return_value = {
        "relationships": [{"urn": urn} for urn in lineage_nodes],
        "entities": [{"urn": urn} for urn in lineage_nodes],
    }

    if entity_info is None:
        entity_info = {}

    def get_entities_side_effect(urns):
        result = {"entities": []}
        for urn in urns:
            info = entity_info.get(urn, {})
            result["entities"].append(
                {
                    "urn": urn,
                    "name": info.get("name", urn),
                    "aspects": info.get("aspects", []),
                }
            )
        return result

    mcp.get_entities.side_effect = get_entities_side_effect
    mcp.list_schema_fields.return_value = {
        "fields": [{"fieldPath": f"field_{i}"} for i in range(schema_fields)]
    }
    mcp.get_lineage_paths_between.return_value = {
        "paths": [[UPSTREAM_URN_1, DATASET_URN]]
    }
    return mcp


class TestTracerAgent:
    def test_returns_candidates_on_success(self):
        mcp = make_mcp_mock()
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        assert result.is_completed
        candidates = result.result["candidates"]
        assert len(candidates) > 0
        assert all("urn" in c and "confidence" in c for c in candidates)

    def test_candidates_sorted_by_confidence(self):
        entity_info = {
            UPSTREAM_URN_1: {"aspects": [{"name": "assertionRunEvents"}]},
            UPSTREAM_URN_2: {"aspects": []},
        }
        mcp = make_mcp_mock(entity_info=entity_info)
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        candidates = result.result["candidates"]
        assert len(candidates) >= 2
        assert candidates[0]["confidence"] >= candidates[1]["confidence"]

    def test_failed_assertions_increase_confidence(self):
        entity_info = {
            UPSTREAM_URN_1: {"aspects": [{"name": "assertionRunEvents"}]},
            UPSTREAM_URN_2: {"aspects": []},
        }
        mcp = make_mcp_mock(entity_info=entity_info)
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        candidates = {c["urn"]: c for c in result.result["candidates"]}
        assert (
            candidates[UPSTREAM_URN_1]["confidence"]
            > candidates[UPSTREAM_URN_2]["confidence"]
        )

    def test_missing_dataset_urn_fails(self):
        mcp = make_mcp_mock()
        agent = TracerAgent(mcp)
        msg = AgentMessage(
            from_agent="coordinator", to_agent="tracer", task="test", context={}
        )
        result = agent.run(msg)
        assert result.is_failed
        assert "dataset_urn" in result.error

    def test_lineage_error_handled(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.get_lineage.side_effect = RuntimeError("connection failed")
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        assert result.is_failed
        assert "connection failed" in result.error

    def test_low_confidence_candidates_filtered(self):
        mcp = make_mcp_mock()
        agent = TracerAgent(mcp, config={"confidence_threshold": 0.9})
        result = agent.run(make_message())
        candidates = result.result["candidates"]
        assert all(c["confidence"] >= 0.9 for c in candidates)

    def test_path_included_in_candidate(self):
        mcp = make_mcp_mock()
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        candidates = result.result["candidates"]
        for c in candidates:
            assert "path" in c
            assert isinstance(c["path"], list)

    def test_excludes_failing_dataset_from_candidates(self):
        mcp = make_mcp_mock(lineage_nodes=[DATASET_URN, UPSTREAM_URN_1])
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        candidates = result.result["candidates"]
        urns = [c["urn"] for c in candidates]
        assert DATASET_URN not in urns

    def test_missing_lineage_adds_low_confidence(self):
        mcp = make_mcp_mock(
            lineage_nodes=[UPSTREAM_URN_1],
            entity_info={
                UPSTREAM_URN_1: {"aspects": [{"name": "schemaMetadata"}]},
            },
        )
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        candidates = result.result["candidates"]
        assert len(candidates) >= 1
        assert "incomplete lineage" in candidates[0]["reason"]

    def test_recently_created_adds_confidence(self):
        import time as _time

        recent_ms = (_time.time() * 1000) - (86400 * 1000)  # 1 day ago
        mcp = make_mcp_mock(
            lineage_nodes=[UPSTREAM_URN_1],
            entity_info={
                UPSTREAM_URN_1: {
                    "aspects": [
                        {"name": "dataPlatformInfo", "created": {"time": recent_ms}},
                        {"name": "upstreamLineage"},
                    ],
                },
            },
        )
        agent = TracerAgent(mcp)
        result = agent.run(make_message())
        candidates = result.result["candidates"]
        assert len(candidates) >= 1
        assert "recently created node" in candidates[0]["reason"]


class TestCandidateRootCause:
    def test_to_dict(self):
        c = CandidateRootCause(
            urn="test", confidence=0.8, reason="failed assertion", path=["a", "b"]
        )
        d = c.to_dict()
        assert d["urn"] == "test"
        assert d["confidence"] == 0.8
        assert d["path"] == ["a", "b"]
