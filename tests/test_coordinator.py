"""Tests for the agent communication protocol and coordinator."""

import logging
from unittest.mock import MagicMock

import pytest

from src.agents.base import BaseAgent
from src.agents.protocol import AgentMessage, AgentStatus
from src.coordinator import CoordinatorAgent
from src.datahub_actions_plugin.incident_event import IncidentEvent
from src.mcp_client.client import MCPClient

logging.disable(logging.CRITICAL)


def make_incident() -> IncidentEvent:
    return IncidentEvent(
        assertion_urn="urn:li:assertion:billingAmountPositive",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)",
        assertion_type="DATASET_ROWS",
        result_status="FAILED",
        timestamp_ms=1700000000000,
        error_message="billing_amount has negative values",
    )


class TestAgentMessage:
    def test_initial_status_is_pending(self):
        msg = AgentMessage(from_agent="coordinator", to_agent="tracer", task="test")
        assert msg.status == AgentStatus.PENDING
        assert not msg.is_completed
        assert not msg.is_failed

    def test_mark_in_progress(self):
        msg = AgentMessage(from_agent="coordinator", to_agent="tracer", task="test")
        msg.mark_in_progress()
        assert msg.status == AgentStatus.IN_PROGRESS

    def test_mark_completed(self):
        msg = AgentMessage(from_agent="coordinator", to_agent="tracer", task="test")
        msg.mark_completed({"candidates": []})
        assert msg.is_completed
        assert msg.result == {"candidates": []}

    def test_mark_failed(self):
        msg = AgentMessage(from_agent="coordinator", to_agent="tracer", task="test")
        msg.mark_failed("timeout")
        assert msg.is_failed
        assert msg.error == "timeout"


class MockAgent(BaseAgent):
    name = "mock"
    system_prompt = "mock"

    def __init__(self, mcp_client=None, config=None, result=None, should_fail=False):
        super().__init__(mcp_client or MagicMock(), config)
        self._result = result or {"candidates": []}
        self._should_fail = should_fail

    def run(self, message: AgentMessage) -> AgentMessage:
        if self._should_fail:
            message.mark_failed("mock failure")
        else:
            message.mark_completed(self._result)
        return message


class TestCoordinatorAgent:
    def test_skips_unconfigured_agents(self):
        mcp = MagicMock(spec=MCPClient)
        coordinator = CoordinatorAgent(mcp_client=mcp)
        incident = make_incident()
        result = coordinator.handle_incident(incident)
        assert result["agents"]["tracer"]["status"] == "skipped"
        assert result["agents"]["checker"]["status"] == "skipped"
        assert result["agents"]["notifier"]["status"] == "skipped"
        assert result["agents"]["reporter"]["status"] == "skipped"

    def test_dispatches_tracer_and_receives_result(self):
        mcp = MagicMock(spec=MCPClient)
        tracer = MockAgent(result={"candidates": [{"urn": "urn:li:dataset:upstream1", "confidence": 0.8}]})
        coordinator = CoordinatorAgent(mcp_client=mcp, tracer=tracer)
        incident = make_incident()
        result = coordinator.handle_incident(incident)
        assert result["agents"]["tracer"]["status"] == "completed"
        assert "candidates" in result["agents"]["tracer"]["result"]

    def test_agent_failure_does_not_crash_coordinator(self):
        mcp = MagicMock(spec=MCPClient)
        tracer = MockAgent(should_fail=True)
        coordinator = CoordinatorAgent(mcp_client=mcp, tracer=tracer)
        incident = make_incident()
        result = coordinator.handle_incident(incident)
        assert result["agents"]["tracer"]["status"] == "failed"
        assert "mock failure" in result["agents"]["tracer"]["error"]

    def test_exception_in_agent_is_caught(self):
        mcp = MagicMock(spec=MCPClient)

        class CrashingAgent(BaseAgent):
            name = "crasher"
            system_prompt = ""

            def run(self, message):
                raise RuntimeError("boom")

        coordinator = CoordinatorAgent(mcp_client=mcp, tracer=CrashingAgent(mcp))
        incident = make_incident()
        result = coordinator.handle_incident(incident)
        assert result["agents"]["tracer"]["status"] == "failed"
        assert "boom" in result["agents"]["tracer"]["error"]

    def test_full_pipeline_with_all_agents(self):
        mcp = MagicMock(spec=MCPClient)
        tracer = MockAgent(result={"candidates": [{"urn": "urn:li:dataset:upstream1", "confidence": 0.9}]})
        checker = MockAgent(result={"validated_candidates": [{"urn": "urn:li:dataset:upstream1", "confidence": 0.85}]})
        notifier = MockAgent(result={"notified": True})
        reporter = MockAgent(result={"document_urn": "urn:li:document:123"})

        coordinator = CoordinatorAgent(
            mcp_client=mcp,
            tracer=tracer,
            checker=checker,
            notifier=notifier,
            reporter=reporter,
        )
        incident = make_incident()
        result = coordinator.handle_incident(incident)

        assert result["agents"]["tracer"]["status"] == "completed"
        assert result["agents"]["checker"]["status"] == "completed"
        assert result["agents"]["notifier"]["status"] == "completed"
        assert result["agents"]["reporter"]["status"] == "completed"
        assert "elapsed_seconds" in result
