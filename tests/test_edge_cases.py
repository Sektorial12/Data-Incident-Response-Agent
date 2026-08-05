"""Tests for MCPClient retry/timeout, Reporter update_description, and edge cases."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.agents.protocol import AgentMessage
from src.agents.reporter import ReporterAgent
from src.agents.tracer import TracerAgent
from src.datahub_actions_plugin.incident_event import IncidentEvent
from src.mcp_client.client import MCPClient

logging.disable(logging.CRITICAL)

DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,test.downstream,PROD)"
UPSTREAM_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,test.upstream,PROD)"


class TestMCPClientRetry:
    """Test retry and timeout logic in MCPClient.call_tool."""

    def test_retry_succeeds_on_second_attempt(self):
        import asyncio

        from src.mcp_client.client import MCPClient

        mcp = MCPClient.__new__(MCPClient)
        mcp._initialized = True
        mcp.max_retries = 3
        mcp.retry_base_delay = 0.01
        mcp.timeout_seconds = 5.0

        call_count = [0]

        async def mock_call_tool(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("transient error")
            mock_item = MagicMock()
            mock_item.text = '{"result": "ok"}'
            return [mock_item]

        mcp._mcp = MagicMock()
        mcp._mcp.call_tool = mock_call_tool
        mcp._loop = asyncio.new_event_loop()

        with patch("time.sleep"):
            result = mcp.call_tool("search", {"query": "test"})
        mcp._loop.close()
        assert result["result"] == "ok"
        assert call_count[0] == 2

    def test_retry_exhausted_raises(self):
        import asyncio

        from src.mcp_client.client import MCPClient

        mcp = MCPClient.__new__(MCPClient)
        mcp._initialized = True
        mcp.max_retries = 2
        mcp.retry_base_delay = 0.01
        mcp.timeout_seconds = 5.0

        async def always_fail(*args, **kwargs):
            raise RuntimeError("persistent error")

        mcp._mcp = MagicMock()
        mcp._mcp.call_tool = always_fail
        mcp._loop = asyncio.new_event_loop()

        with patch("time.sleep"), pytest.raises(RuntimeError, match="persistent error"):
            mcp.call_tool("search", {"query": "test"})
        mcp._loop.close()

    def test_timeout_raises_after_retries(self):
        import asyncio

        from src.mcp_client.client import MCPClient

        mcp = MCPClient.__new__(MCPClient)
        mcp._initialized = True
        mcp.max_retries = 2
        mcp.retry_base_delay = 0.01
        mcp.timeout_seconds = 0.01

        async def slow_coro(*args, **kwargs):
            await asyncio.sleep(1)
            return [{"text": "{}"}]

        mcp._mcp = MagicMock()
        mcp._mcp.call_tool = slow_coro
        mcp._loop = asyncio.new_event_loop()

        with patch("time.sleep"), pytest.raises((TimeoutError, asyncio.TimeoutError)):
            mcp.call_tool("search", {"query": "test"})
        mcp._loop.close()


class TestReporterUpdateDescription:
    """Test that Reporter calls update_description on root cause datasets."""

    def test_update_description_called_for_root_cause(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:doc1"}
        mcp.add_tags.return_value = {"success": True}
        mcp.update_description.return_value = {"success": True}

        reporter = ReporterAgent(mcp)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="reporter",
            task="report",
            context={
                "dataset_urn": DATASET_URN,
                "assertion_urn": "urn:li:assertion:test",
                "error_message": "test error",
                "tracer_result": {
                    "candidates": [{"urn": UPSTREAM_URN, "confidence": 0.8}]
                },
                "checker_result": {
                    "validated_candidates": [
                        {
                            "candidate_urn": UPSTREAM_URN,
                            "status": "confirmed",
                            "confidence": 0.9,
                        }
                    ]
                },
            },
        )
        result = reporter.run(msg)
        assert result.is_completed
        mcp.update_description.assert_called_once()
        call_args = mcp.update_description.call_args
        assert (
            call_args[0][0] == UPSTREAM_URN or call_args.kwargs["urn"] == UPSTREAM_URN
        )

    def test_update_description_failure_does_not_crash(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:doc1"}
        mcp.add_tags.return_value = {"success": True}
        mcp.update_description.side_effect = RuntimeError("write failed")

        reporter = ReporterAgent(mcp)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="reporter",
            task="report",
            context={
                "dataset_urn": DATASET_URN,
                "assertion_urn": "urn:li:assertion:test",
                "error_message": "test error",
                "tracer_result": {
                    "candidates": [{"urn": UPSTREAM_URN, "confidence": 0.8}]
                },
                "checker_result": {
                    "validated_candidates": [
                        {
                            "candidate_urn": UPSTREAM_URN,
                            "status": "confirmed",
                            "confidence": 0.9,
                        }
                    ]
                },
            },
        )
        result = reporter.run(msg)
        assert result.is_completed
        assert result.result["document_urn"] == "urn:li:document:doc1"

    def test_no_update_description_when_no_root_causes(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:doc1"}

        reporter = ReporterAgent(mcp)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="reporter",
            task="report",
            context={
                "dataset_urn": DATASET_URN,
                "assertion_urn": "urn:li:assertion:test",
                "error_message": "test error",
                "tracer_result": {"candidates": []},
                "checker_result": {"validated_candidates": []},
            },
        )
        result = reporter.run(msg)
        assert result.is_completed
        mcp.update_description.assert_not_called()
        mcp.add_tags.assert_not_called()


class TestEdgeCases:
    """Test malformed events and empty lineage responses."""

    def test_malformed_incident_event_handled_by_coordinator(self):
        """Coordinator should handle malformed IncidentEvent gracefully."""
        from src.coordinator import CoordinatorAgent

        mcp = MagicMock(spec=MCPClient)
        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=TracerAgent(mcp),
        )

        incident = IncidentEvent(
            assertion_urn="",
            dataset_urn="",
            assertion_type="",
            result_status="FAILED",
            timestamp_ms=0,
            error_message=None,
        )
        result = coordinator.handle_incident(incident)
        assert result["agents"]["tracer"]["status"] == "failed"

    def test_empty_lineage_response_returns_no_candidates(self):
        """Tracer should handle empty lineage gracefully."""
        mcp = MagicMock(spec=MCPClient)
        mcp.get_lineage.return_value = {"relationships": [], "entities": []}
        mcp.get_entities.return_value = {"entities": []}
        mcp.list_schema_fields.return_value = {"fields": []}
        mcp.get_lineage_paths_between.return_value = {"paths": []}

        tracer = TracerAgent(mcp)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="tracer",
            task="trace",
            context={"dataset_urn": DATASET_URN},
        )
        result = tracer.run(msg)
        assert result.is_completed
        assert result.result["candidates"] == []

    def test_null_lineage_response_handled(self):
        """Tracer should handle None lineage response."""
        mcp = MagicMock(spec=MCPClient)
        mcp.get_lineage.return_value = None

        tracer = TracerAgent(mcp)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="tracer",
            task="trace",
            context={"dataset_urn": DATASET_URN},
        )
        result = tracer.run(msg)
        assert result.is_completed
        assert result.result["candidates"] == []
