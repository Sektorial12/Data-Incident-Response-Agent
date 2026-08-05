"""Notifier Agent — sends Slack alerts for data incidents.

Formats validated root causes into an actionable Slack message and sends
via Incoming Webhook.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.agents.base import BaseAgent
from src.agents.protocol import AgentMessage
from src.mcp_client.client import MCPClient

logger = logging.getLogger(__name__)

NOTIFIER_SYSTEM_PROMPT = """\
You are the Notifier Agent in a Data Incident Response system.
Given an incident summary with validated root causes, your job is to:
1. Format a clear, actionable Slack alert
2. Include: dataset name, assertion that failed, root cause, confidence, lineage path
3. Include a link to the DataHub dataset page
4. Include a link to the incident report (if available)
5. Use appropriate emoji/formatting for severity
"""


class NotifierAgent(BaseAgent):
    """Sends Slack alerts for data incidents."""

    name = "notifier"
    system_prompt = NOTIFIER_SYSTEM_PROMPT

    def __init__(
        self, mcp_client: MCPClient, config: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mcp_client, config)
        self.webhook_url = self.config.get(
            "slack_webhook_url",
            os.getenv("SLACK_WEBHOOK_URL", ""),
        )
        self.datahub_frontend_url = self.config.get(
            "datahub_frontend_url",
            os.getenv("DATAHUB_FRONTEND_URL", "http://localhost:9002"),
        )

    def run(self, message: AgentMessage) -> AgentMessage:
        """Format and send the Slack alert."""
        self._log_start(message)

        candidates = message.context.get("candidates", [])
        dataset_urn = message.context.get("dataset_urn", "")
        assertion_urn = message.context.get("assertion_urn", "")
        error_message = message.context.get("error_message", "")

        alert_text = self._format_alert(
            dataset_urn=dataset_urn,
            assertion_urn=assertion_urn,
            error_message=error_message,
            candidates=candidates,
        )

        if not self.webhook_url or "your/webhook" in self.webhook_url:
            self.logger.warning("Slack webhook URL not configured — logging alert only")
            self.logger.info("Alert:\n%s", alert_text)
            message.mark_completed(
                {
                    "notified": False,
                    "reason": "webhook not configured",
                    "alert_text": alert_text,
                }
            )
            self._log_complete(message)
            return message

        try:
            self._send_slack(alert_text)
            message.mark_completed({"notified": True, "alert_text": alert_text})
            self._log_complete(message)
        except Exception as e:
            self.logger.error("Slack notification failed: %s", e)
            message.mark_completed(
                {
                    "notified": False,
                    "reason": str(e),
                    "alert_text": alert_text,
                }
            )

        return message

    def _format_alert(
        self,
        dataset_urn: str,
        assertion_urn: str,
        error_message: str | None,
        candidates: list[dict[str, Any]],
    ) -> str:
        """Format the Slack alert message."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        dataset_name = self._extract_dataset_name(dataset_urn)

        lines: list[str] = [
            ":rotating_light: *Data Incident Detected*",
            f"*Time:* {timestamp}",
            f"*Dataset:* `{dataset_name}`",
            f"*Assertion:* `{assertion_urn}`",
        ]

        if error_message:
            lines.append(f"*Error:* {error_message}")

        if candidates:
            lines.append(f"\n*Root Cause Candidates ({len(candidates)}):*")
            for i, c in enumerate(candidates[:3], 1):
                conf = c.get("confidence", 0)
                reason = c.get("reasoning", c.get("reason", "unknown"))
                candidate_urn = c.get("candidate_urn", c.get("urn", ""))
                lines.append(
                    f"  {i}. `{candidate_urn}` (confidence: {conf:.0%}) — {reason}"
                )
        else:
            lines.append("\n*Root Cause:* No validated candidates found")

        dataset_url = (
            f"{self.datahub_frontend_url}/dataset/{self._url_encode(dataset_urn)}"
        )
        lines.append(f"\n<{dataset_url}|View in DataHub>")

        return "\n".join(lines)

    def _send_slack(self, text: str) -> None:
        """Send a message to Slack via Incoming Webhook."""
        payload = json.dumps({"text": text, "mrkdwn": True}).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Slack returned status {resp.status}")

    @staticmethod
    def _extract_dataset_name(urn: str) -> str:
        """Extract a human-readable name from a dataset URN."""
        if "sqlite," in urn:
            parts = urn.split("sqlite,")
            if len(parts) > 1:
                rest = parts[1].rstrip(")")
                return rest.split(",")[0] if "," in rest else rest
        return urn

    @staticmethod
    def _url_encode(urn: str) -> str:
        """URL-encode a URN for use in DataHub URLs."""
        import urllib.parse

        return urllib.parse.quote(urn, safe="")
