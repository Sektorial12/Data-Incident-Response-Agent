"""Tests for the IncidentStore SQLite persistence layer."""

import json
import tempfile
from pathlib import Path

import pytest

from src.store.incident_store import IncidentStore


@pytest.fixture
def store(tmp_path):
    return IncidentStore(db_path=tmp_path / "test_incidents.db")


class TestIncidentStoreSaveGet:
    def test_save_and_get_incident(self, store):
        store.save_incident(
            incident_id="inc-1",
            assertion_urn="urn:li:assertion:abc",
            dataset_urn="urn:li:dataset:xyz",
            error_message="null values detected",
            dedup_key="urn:li:assertion:abc:urn:li:dataset:xyz",
        )
        incident = store.get_incident("inc-1")
        assert incident is not None
        assert incident["id"] == "inc-1"
        assert incident["assertion_urn"] == "urn:li:assertion:abc"
        assert incident["dataset_urn"] == "urn:li:dataset:xyz"
        assert incident["status"] == "active"
        assert incident["error_message"] == "null values detected"
        assert incident["dedup_key"] == "urn:li:assertion:abc:urn:li:dataset:xyz"

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_incident("does-not-exist") is None

    def test_duplicate_id_ignored(self, store):
        store.save_incident(
            incident_id="inc-1",
            assertion_urn="urn:li:assertion:abc",
            dataset_urn="urn:li:dataset:xyz",
        )
        store.save_incident(
            incident_id="inc-1",
            assertion_urn="urn:li:assertion:abc",
            dataset_urn="urn:li:dataset:xyz",
        )
        incidents = store.list_incidents()
        assert len(incidents) == 1


class TestIncidentStoreUpdate:
    def test_update_marks_resolved(self, store):
        store.save_incident(
            incident_id="inc-1",
            assertion_urn="urn:li:assertion:abc",
            dataset_urn="urn:li:dataset:xyz",
        )
        store.update_incident(
            incident_id="inc-1",
            status="resolved",
            root_causes=[{"urn": "urn:li:dataset:root", "confidence": 0.9}],
            agent_results={"tracer": {"status": "completed"}},
            elapsed_seconds=12.5,
        )
        incident = store.get_incident("inc-1")
        assert incident["status"] == "resolved"
        assert incident["elapsed_seconds"] == 12.5
        assert incident["resolved_at"] is not None
        assert incident["root_causes"] == [
            {"urn": "urn:li:dataset:root", "confidence": 0.9}
        ]
        assert incident["agent_results"] == {"tracer": {"status": "completed"}}

    def test_update_nonexistent_silent(self, store):
        store.update_incident(incident_id="nope", status="resolved")
        assert store.get_incident("nope") is None


class TestIncidentStoreList:
    def test_list_all_incidents(self, store):
        for i in range(5):
            store.save_incident(
                incident_id=f"inc-{i}",
                assertion_urn=f"urn:li:assertion:{i}",
                dataset_urn=f"urn:li:dataset:{i}",
            )
        incidents = store.list_incidents()
        assert len(incidents) == 5

    def test_list_filtered_by_status(self, store):
        store.save_incident("inc-1", "a1", "d1")
        store.save_incident("inc-2", "a2", "d2")
        store.update_incident("inc-1", status="resolved")
        active = store.list_incidents(status="active")
        resolved = store.list_incidents(status="resolved")
        assert len(active) == 1
        assert active[0]["id"] == "inc-2"
        assert len(resolved) == 1
        assert resolved[0]["id"] == "inc-1"

    def test_list_with_limit(self, store):
        for i in range(10):
            store.save_incident(f"inc-{i}", f"a{i}", f"d{i}")
        incidents = store.list_incidents(limit=3)
        assert len(incidents) == 3


class TestIncidentStoreDedup:
    def test_find_recent_returns_active(self, store):
        store.save_incident(
            "inc-1", "a1", "d1", dedup_key="a1:d1"
        )
        recent = store.find_recent("a1:d1", within_seconds=900)
        assert recent is not None
        assert recent["id"] == "inc-1"

    def test_find_recent_returns_none_after_resolve(self, store):
        store.save_incident("inc-1", "a1", "d1", dedup_key="a1:d1")
        store.update_incident("inc-1", status="resolved")
        recent = store.find_recent("a1:d1", within_seconds=900)
        assert recent is None

    def test_find_recent_different_key_returns_none(self, store):
        store.save_incident("inc-1", "a1", "d1", dedup_key="a1:d1")
        recent = store.find_recent("different:key", within_seconds=900)
        assert recent is None


class TestIncidentStoreMetrics:
    def test_metrics_empty_store(self, store):
        m = store.get_metrics()
        assert m["total"] == 0
        assert m["active"] == 0
        assert m["resolved"] == 0
        assert m["avg_mttr_seconds"] == 0

    def test_metrics_with_incidents(self, store):
        store.save_incident("inc-1", "a1", "d1")
        store.save_incident("inc-2", "a2", "d2")
        store.update_incident("inc-1", status="resolved", elapsed_seconds=10.0)
        store.update_incident("inc-2", status="resolved", elapsed_seconds=20.0)
        m = store.get_metrics()
        assert m["total"] == 2
        assert m["active"] == 0
        assert m["resolved"] == 2
        assert m["avg_mttr_seconds"] == 15.0
