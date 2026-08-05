"""Tests for the FastAPI server endpoints and incident dedup logic."""

import pytest
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.store.incident_store import IncidentStore


@pytest.fixture
def client(tmp_path):
    store = IncidentStore(db_path=tmp_path / "test.db")
    app = create_app(store=store)
    return TestClient(app), store


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        c, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "uptime_seconds" in data


class TestMetricsEndpoint:
    def test_metrics_returns_prometheus_format(self, client):
        c, _ = client
        resp = c.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "incidents_total" in text
        assert "llm_calls_total" in text


class TestIncidentsEndpoint:
    def test_list_empty(self, client):
        c, _ = client
        resp = c.get("/incidents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client):
        c, store = client
        store.save_incident("inc-1", "a1", "d1")
        store.save_incident("inc-2", "a2", "d2")
        resp = c.get("/incidents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_filtered_by_status(self, client):
        c, store = client
        store.save_incident("inc-1", "a1", "d1")
        store.save_incident("inc-2", "a2", "d2")
        store.update_incident("inc-1", status="resolved")
        resp = c.get("/incidents?status=active")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "inc-2"

    def test_get_single_incident(self, client):
        c, store = client
        store.save_incident("inc-1", "a1", "d1")
        resp = c.get("/incidents/inc-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "inc-1"

    def test_get_nonexistent_returns_null(self, client):
        c, _ = client
        resp = c.get("/incidents/nope")
        assert resp.status_code == 200
        assert resp.json() is None


class TestStatsEndpoint:
    def test_stats_empty(self, client):
        c, _ = client
        resp = c.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["avg_mttr_seconds"] == 0

    def test_stats_with_data(self, client):
        c, store = client
        store.save_incident("inc-1", "a1", "d1")
        store.update_incident("inc-1", status="resolved", elapsed_seconds=15.0)
        resp = c.get("/stats")
        data = resp.json()
        assert data["total"] == 1
        assert data["resolved"] == 1
        assert data["avg_mttr_seconds"] == 15.0


class TestDedupLogic:
    def test_duplicate_incident_suppressed(self, tmp_path):
        from src.agents.base import BaseAgent
        from src.agents.protocol import AgentMessage, AgentStatus
        from src.coordinator import CoordinatorAgent
        from src.datahub_actions_plugin.incident_event import IncidentEvent
        from src.mcp_client.client import MCPClient

        store = IncidentStore(db_path=tmp_path / "test.db")

        class StubAgent(BaseAgent):
            name = "stub"
            system_prompt = ""

            def run(self, message: AgentMessage) -> AgentMessage:
                message.mark_completed({})
                return message

        mcp = MCPClient()
        coord = CoordinatorAgent(
            mcp_client=mcp,
            tracer=StubAgent(mcp),
            checker=StubAgent(mcp),
            notifier=StubAgent(mcp),
            reporter=StubAgent(mcp),
            store=store,
        )

        incident = IncidentEvent(
            assertion_urn="urn:li:assertion:test",
            dataset_urn="urn:li:dataset:test",
            assertion_type="METRIC",
            result_status="FAILED",
            timestamp_ms=1700000000000,
            error_message="test error",
        )

        result1 = coord.handle_incident(incident)
        assert "deduplicated" not in result1 or not result1["deduplicated"]

        result2 = coord.handle_incident(incident)
        assert result2.get("deduplicated") is True
