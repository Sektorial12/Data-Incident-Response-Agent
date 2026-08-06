"""Tests for the Notifier and Reporter agents."""

import logging
from unittest.mock import MagicMock, patch

from src.agents.notifier import NotifierAgent
from src.agents.protocol import AgentMessage
from src.agents.reporter import ReporterAgent
from src.mcp_client.client import MCPClient

logging.disable(logging.CRITICAL)

DATASET_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)"
)
ASSERTION_URN = "urn:li:assertion:billingAmountPositive"


def make_notifier_message(candidates=None) -> AgentMessage:
    return AgentMessage(
        from_agent="coordinator",
        to_agent="notifier",
        task="send_alert",
        context={
            "dataset_urn": DATASET_URN,
            "assertion_urn": ASSERTION_URN,
            "error_message": "billing_amount has negative values",
            "candidates": candidates or [],
        },
    )


def make_reporter_message() -> AgentMessage:
    return AgentMessage(
        from_agent="coordinator",
        to_agent="reporter",
        task="write_report",
        context={
            "dataset_urn": DATASET_URN,
            "assertion_urn": ASSERTION_URN,
            "error_message": "billing_amount has negative values",
            "tracer_result": {
                "candidates": [
                    {
                        "urn": "urn:li:dataset:upstream1",
                        "confidence": 0.8,
                        "path": ["urn:li:dataset:upstream1", DATASET_URN],
                    },
                ],
            },
            "checker_result": {
                "validated_candidates": [
                    {
                        "candidate_urn": "urn:li:dataset:upstream1",
                        "status": "confirmed",
                        "confidence": 0.9,
                        "reasoning": "failed assertions",
                        "evidence": ["evidence1"],
                    },
                ],
            },
        },
    )


class TestNotifierAgent:
    def test_logs_alert_when_webhook_not_configured(self):
        mcp = MagicMock(spec=MCPClient)
        agent = NotifierAgent(mcp, config={"slack_webhook_url": ""})
        agent.router.default_webhook = ""
        agent.router.rules = []
        result = agent.run(make_notifier_message())
        assert result.is_completed
        assert result.result["notified"] is False
        assert "webhook not configured" in result.result["reason"]
        assert "alert_text" in result.result

    def test_alert_contains_dataset_and_assertion(self):
        mcp = MagicMock(spec=MCPClient)
        agent = NotifierAgent(mcp, config={"slack_webhook_url": ""})
        result = agent.run(make_notifier_message())
        alert = result.result["alert_text"]
        assert "mart_billing" in alert
        assert ASSERTION_URN in alert
        assert "billing_amount has negative values" in alert

    def test_alert_includes_candidates(self):
        mcp = MagicMock(spec=MCPClient)
        agent = NotifierAgent(mcp, config={"slack_webhook_url": ""})
        candidates = [
            {
                "candidate_urn": "urn:li:dataset:upstream1",
                "confidence": 0.9,
                "reasoning": "failed assertions",
            },
        ]
        result = agent.run(make_notifier_message(candidates))
        alert = result.result["alert_text"]
        assert "upstream1" in alert
        assert "90%" in alert

    def test_sends_to_slack_when_configured(self):
        mcp = MagicMock(spec=MCPClient)
        agent = NotifierAgent(
            mcp, config={"slack_webhook_url": "https://hooks.slack.com/services/test"}
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            result = agent.run(make_notifier_message())
            assert result.is_completed
            assert result.result["notified"] is True
            mock_urlopen.assert_called_once()

    def test_slack_failure_handled(self):
        mcp = MagicMock(spec=MCPClient)
        agent = NotifierAgent(
            mcp, config={"slack_webhook_url": "https://hooks.slack.com/services/test"}
        )
        with patch("urllib.request.urlopen", side_effect=RuntimeError("network error")):
            result = agent.run(make_notifier_message())
            assert result.is_completed
            assert result.result["notified"] is False
            assert "network error" in result.result["reason"]


class TestReporterAgent:
    def test_generates_report_and_saves_document(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:123"}
        mcp.add_tags.return_value = {"success": True}
        agent = ReporterAgent(mcp)
        result = agent.run(make_reporter_message())
        assert result.is_completed
        assert result.result["document_urn"] == "urn:li:document:123"
        assert result.result["report_length"] > 100
        mcp.save_document.assert_called_once()
        mcp.add_tags.assert_called_once()

    def test_report_contains_incident_summary(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:123"}
        mcp.add_tags.return_value = {}
        agent = ReporterAgent(mcp)
        result = agent.run(make_reporter_message())
        preview = result.result["report_preview"]
        assert "Incident Report" in preview
        assert "mart_billing" in preview

    def test_report_contains_root_cause_analysis(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:123"}
        mcp.add_tags.return_value = {}
        agent = ReporterAgent(mcp)
        result = agent.run(make_reporter_message())
        preview = result.result["report_preview"]
        assert "Root Cause" in preview
        assert "upstream1" in preview

    def test_save_document_failure_handled(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.side_effect = RuntimeError("API error")
        mcp.add_tags.return_value = {}
        agent = ReporterAgent(mcp)
        result = agent.run(make_reporter_message())
        assert result.is_completed
        assert result.result["document_urn"] is None

    def test_add_tags_failure_handled(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:123"}
        mcp.add_tags.side_effect = RuntimeError("tag error")
        agent = ReporterAgent(mcp)
        result = agent.run(make_reporter_message())
        assert result.is_completed
        assert result.result["document_urn"] is not None

    def test_empty_validated_candidates(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.save_document.return_value = {"urn": "urn:li:document:456"}
        mcp.add_tags.return_value = {}
        agent = ReporterAgent(mcp)
        msg = make_reporter_message()
        msg.context["checker_result"] = {"validated_candidates": []}
        result = agent.run(msg)
        assert result.is_completed
        mcp.add_tags.assert_not_called()
