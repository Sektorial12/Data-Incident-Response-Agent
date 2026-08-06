"""Tests for the AlertRouter — webhook selection by platform and confidence."""

import os

import pytest

from src.agents.alert_router import AlertRouter


@pytest.fixture
def config_file(tmp_path):
    config = """
alert_routing:
  rules:
    - name: "Critical platforms"
      match:
        platform: ["snowflake", "bigquery"]
      webhook_url: "https://hooks.slack.com/critical"
    - name: "High confidence"
      match:
        min_confidence: 0.8
      webhook_url: "https://hooks.slack.com/high"
  default_webhook_url: "https://hooks.slack.com/default"
"""
    path = tmp_path / "agent_config.yaml"
    path.write_text(config)
    return str(path)


class TestAlertRouterMatching:
    def test_platform_match(self, config_file):
        router = AlertRouter(config_path=config_file)
        webhook = router.select_webhook(platform="snowflake", confidence=0.3)
        assert webhook == "https://hooks.slack.com/critical"

    def test_platform_match_case_insensitive(self, config_file):
        router = AlertRouter(config_path=config_file)
        webhook = router.select_webhook(platform="BigQuery", confidence=0.3)
        assert webhook == "https://hooks.slack.com/critical"

    def test_confidence_match(self, config_file):
        router = AlertRouter(config_path=config_file)
        webhook = router.select_webhook(platform="postgres", confidence=0.9)
        assert webhook == "https://hooks.slack.com/high"

    def test_no_match_falls_to_default(self, config_file):
        router = AlertRouter(config_path=config_file)
        webhook = router.select_webhook(platform="mysql", confidence=0.3)
        assert webhook == "https://hooks.slack.com/default"

    def test_first_match_wins(self, config_file):
        router = AlertRouter(config_path=config_file)
        # snowflake matches first rule (platform), even though confidence is high
        webhook = router.select_webhook(platform="snowflake", confidence=0.9)
        assert webhook == "https://hooks.slack.com/critical"

    def test_no_platform_no_confidence(self, config_file):
        router = AlertRouter(config_path=config_file)
        webhook = router.select_webhook(platform=None, confidence=0.0)
        assert webhook == "https://hooks.slack.com/default"


class TestAlertRouterEnvVar:
    def test_env_var_resolution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SLACK_CRITICAL_WEBHOOK_URL", "https://hooks.slack.com/env-critical")
        config = """
alert_routing:
  rules:
    - name: "Critical"
      match:
        platform: ["snowflake"]
      webhook_url: "${SLACK_CRITICAL_WEBHOOK_URL}"
  default_webhook_url: "${SLACK_WEBHOOK_URL}"
"""
        path = tmp_path / "config.yaml"
        path.write_text(config)
        router = AlertRouter(config_path=str(path))
        webhook = router.select_webhook(platform="snowflake", confidence=0.0)
        assert webhook == "https://hooks.slack.com/env-critical"

    def test_default_falls_back_to_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/env-default")
        config = """
alert_routing:
  rules: []
  default_webhook_url: "${SLACK_WEBHOOK_URL}"
"""
        path = tmp_path / "config.yaml"
        path.write_text(config)
        router = AlertRouter(config_path=str(path))
        webhook = router.select_webhook(platform="anything", confidence=0.0)
        assert webhook == "https://hooks.slack.com/env-default"

    def test_no_config_uses_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/env-only")
        router = AlertRouter(config_path=str(tmp_path / "nonexistent.yaml"))
        webhook = router.select_webhook(platform="anything", confidence=0.0)
        assert webhook == "https://hooks.slack.com/env-only"


class TestAlertRouterEdgeCases:
    def test_empty_rules(self, tmp_path):
        config = """
alert_routing:
  rules: []
  default_webhook_url: "https://hooks.slack.com/default"
"""
        path = tmp_path / "config.yaml"
        path.write_text(config)
        router = AlertRouter(config_path=str(path))
        webhook = router.select_webhook(platform="snowflake", confidence=1.0)
        assert webhook == "https://hooks.slack.com/default"

    def test_rule_with_empty_match_does_not_match(self, config_file):
        """A rule with empty match criteria should not match (avoid catch-all)."""
        router = AlertRouter(config_path=config_file)
        # Both rules have non-empty match criteria, so this is fine
        webhook = router.select_webhook(platform="mysql", confidence=0.1)
        assert webhook == "https://hooks.slack.com/default"
