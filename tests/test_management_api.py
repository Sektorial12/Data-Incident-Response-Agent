"""Tests for management API endpoints."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from src.api.management import router, set_agent_proc
from src.api.server import create_app
from src.store.incident_store import IncidentStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAHUB_SERVER_URL", "http://localhost:8080")
    monkeypatch.setenv("DATAHUB_ACCESS_TOKEN", "test-token")
    store = IncidentStore(db_path=str(tmp_path / "test.db"))
    app = create_app(store=store)
    return TestClient(app)


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    config = {
        "llm": {"model": "auto"},
        "alert_routing": {
            "rules": [{"name": "test", "match": {"platform": ["snowflake"]}, "webhook_url": "${SLACK_URL}"}],
            "default_webhook_url": "${SLACK_DEFAULT}",
            "dedup_window_seconds": 900,
        },
    }
    path = tmp_path / "agent_config.yaml"
    path.write_text(yaml.safe_dump(config))
    import src.api.management as mgmt
    monkeypatch.setattr(mgmt, "_CONFIG_PATH", path)
    return path


class TestAssertionEndpoints:
    def test_list_assertions_handles_error(self, client):
        with patch("src.api.management.requests.post", side_effect=Exception("connection refused")):
            resp = client.get("/manage/assertions")
        assert resp.status_code == 502

    def test_list_assertions_returns_data(self, client):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "searchAcrossEntities": {
                    "searchResults": [
                        {"entity": {"urn": "urn:li:assertion:test1", "info": {"type": "DATASET_ROWS", "datasetAssertion": {"dataset": "urn:li:dataset:x", "operator": "EQUAL_TO"}}}}
                    ]
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("src.api.management.requests.post", return_value=mock_resp):
            resp = client.get("/manage/assertions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["assertions"][0]["urn"] == "urn:li:assertion:test1"

    def test_trigger_failure_returns_run_id(self, client):
        with patch("datahub.emitter.rest_emitter.DataHubRestEmitter") as mock_emitter:
            resp = client.post("/manage/assertions/trigger", json={
                "assertion_urn": "urn:li:assertion:test",
                "dataset_urn": "urn:li:dataset:test",
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "emitted"
        assert "run_id" in resp.json()


class TestConfigEndpoints:
    def test_get_config(self, client, config_path, monkeypatch):
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        resp = client.get("/manage/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_routing"]["dedup_window_seconds"] == 900
        assert data["env"]["slack_webhook_configured"] is True

    def test_update_routing(self, client, config_path):
        resp = client.put("/manage/config/routing", json={
            "rules": [{"name": "new", "match": {"platform": ["bigquery"]}, "webhook_url": "https://example.com"}],
            "default_webhook_url": "https://default.com",
            "dedup_window_seconds": 600,
        })
        assert resp.status_code == 200
        assert resp.json()["rules_count"] == 1
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert config["alert_routing"]["dedup_window_seconds"] == 600
        assert config["alert_routing"]["rules"][0]["name"] == "new"


class TestAgentLifecycle:
    def test_agent_status_stopped(self, client):
        set_agent_proc(None)
        resp = client.get("/manage/agent/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_agent_stop_when_stopped(self, client):
        set_agent_proc(None)
        resp = client.post("/manage/agent/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_stopped"

    def test_agent_restart_no_cli(self, client):
        set_agent_proc(None)
        with patch("subprocess.Popen", side_effect=FileNotFoundError()):
            resp = client.post("/manage/agent/restart")
        assert resp.status_code == 500
