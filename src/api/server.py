"""FastAPI server — health, metrics, and incident API for the dashboard.

Runs alongside the DataHub Actions listener. Provides:
- GET /health — liveness probe
- GET /metrics — Prometheus-style metrics
- GET /incidents — list incidents (with optional status filter)
- GET /incidents/{id} — single incident detail
- GET /stats — aggregate metrics for dashboard
"""

import logging
import time
from typing import Any

from fastapi import FastAPI, Query

from src.store.incident_store import IncidentStore

logger = logging.getLogger(__name__)

_start_time = time.time()

# Counters for Prometheus-style metrics
_counters: dict[str, int | float] = {
    "incidents_total": 0,
    "incidents_deduplicated": 0,
    "incidents_resolved": 0,
    "incidents_failed": 0,
    "agent_duration_seconds_sum": 0.0,
    "agent_duration_seconds_count": 0,
    "llm_calls_total": 0,
    "llm_calls_failed": 0,
}


def record_incident(deduplicated: bool = False) -> None:
    """Called by the coordinator when an incident is processed."""
    _counters["incidents_total"] += 1
    if deduplicated:
        _counters["incidents_deduplicated"] += 1


def record_incident_resolved(failed: bool = False) -> None:
    if failed:
        _counters["incidents_failed"] += 1
    else:
        _counters["incidents_resolved"] += 1


def record_agent_duration(seconds: float) -> None:
    _counters["agent_duration_seconds_sum"] += seconds
    _counters["agent_duration_seconds_count"] += 1


def record_llm_call(failed: bool = False) -> None:
    _counters["llm_calls_total"] += 1
    if failed:
        _counters["llm_calls_failed"] += 1


def create_app(store: IncidentStore | None = None) -> FastAPI:
    """Create the FastAPI app, optionally with a shared store."""
    app = FastAPI(title="Data Incident Response Agent", version="0.1.0")
    _store = store or IncidentStore()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - _start_time, 1),
        }

    @app.get("/metrics")
    def metrics() -> str:
        lines = []
        for key, val in _counters.items():
            lines.append(f"# TYPE {key} counter")
            lines.append(f"{key} {val}")
        return "\n".join(lines) + "\n"

    @app.get("/incidents")
    def list_incidents(
        status: str | None = Query(None, description="Filter by status"),
        limit: int = Query(50, le=200),
        offset: int = Query(0),
    ) -> list[dict[str, Any]]:
        return _store.list_incidents(status=status, limit=limit, offset=offset)

    @app.get("/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict[str, Any] | None:
        return _store.get_incident(incident_id)

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        return _store.get_metrics()

    return app
