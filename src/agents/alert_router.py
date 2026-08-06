"""Alert router — selects Slack webhook URL based on routing rules.

Rules are loaded from agent_config.yaml under the `alert_routing` key.
Each rule has a `match` dict with optional fields:
  - platform: list of platform names to match (case-insensitive)
  - min_confidence: minimum root cause confidence to match
Rules are evaluated top-to-bottom; first match wins.
If no rule matches, falls back to default_webhook_url or SLACK_WEBHOOK_URL env var.
"""

import logging
import os
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


class AlertRouter:
    """Routes Slack alerts to different webhooks based on configurable rules."""

    def __init__(self, config_path: str | None = None) -> None:
        self.rules: list[dict[str, Any]] = []
        self.default_webhook: str = ""
        self._load_config(config_path)

    def _load_config(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "config", "agent_config.yaml"
            )

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        except (FileNotFoundError, OSError) as e:
            logger.debug("Could not load alert routing config: %s", e)
            self.default_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
            return

        routing = config.get("alert_routing", {})
        self.rules = routing.get("rules", [])
        self.default_webhook = self._resolve_env(
            routing.get("default_webhook_url", "")
        ) or os.getenv("SLACK_WEBHOOK_URL", "")

    def _resolve_env(self, value: str) -> str:
        """Resolve ${ENV_VAR} references in config values."""
        if not value:
            return ""

        def _replace(match: re.Match) -> str:
            return os.getenv(match.group(1), "")

        return _ENV_VAR_PATTERN.sub(_replace, value)

    def select_webhook(
        self,
        platform: str | None = None,
        confidence: float = 0.0,
    ) -> str:
        """Select the appropriate webhook URL for this alert.

        Args:
            platform: Dataset platform name (e.g., "snowflake", "bigquery").
            confidence: Highest root cause confidence score (0.0 to 1.0).

        Returns:
            Webhook URL string, or empty string if none configured.
        """
        for rule in self.rules:
            if self._matches(rule.get("match", {}), platform, confidence):
                webhook = self._resolve_env(rule.get("webhook_url", ""))
                if webhook:
                    logger.debug(
                        "Alert routed to '%s' via rule '%s'",
                        webhook[:40] + "..." if len(webhook) > 40 else webhook,
                        rule.get("name", "unnamed"),
                    )
                    return webhook

        return self.default_webhook

    @staticmethod
    def _matches(
        match_criteria: dict[str, Any],
        platform: str | None,
        confidence: float,
    ) -> bool:
        """Check if an alert matches a rule's criteria."""
        if not match_criteria:
            return False

        platforms = match_criteria.get("platform")
        if platforms:
            if not platform or platform.lower() not in [
                p.lower() for p in platforms
            ]:
                return False

        min_conf = match_criteria.get("min_confidence")
        if min_conf is not None and confidence < min_conf:
            return False

        return True
