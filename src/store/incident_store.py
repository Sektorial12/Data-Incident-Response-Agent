"""Incident store — SQLite persistence for data incidents.

Stores incident records with agent results, root causes, and timing.
Used by the dashboard, dedup logic, and MTTR metrics.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "incidents.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    assertion_urn TEXT NOT NULL,
    dataset_urn TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    error_message TEXT,
    root_causes TEXT,
    agent_results TEXT,
    elapsed_seconds REAL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    dedup_key TEXT
);

CREATE INDEX IF NOT EXISTS idx_incidents_dedup ON incidents(dedup_key, created_at);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_dataset ON incidents(dataset_urn);
"""


class IncidentStore:
    """Thread-safe SQLite store for incident records."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_SCHEMA)
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def save_incident(
        self,
        incident_id: str,
        assertion_urn: str,
        dataset_urn: str,
        error_message: str = "",
        dedup_key: str = "",
    ) -> None:
        """Insert a new incident record (on conflict, ignore)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._conn()
            conn.execute(
                """INSERT OR IGNORE INTO incidents
                   (id, assertion_urn, dataset_urn, status, error_message,
                    created_at, dedup_key)
                   VALUES (?, ?, ?, 'active', ?, ?, ?)""",
                (incident_id, assertion_urn, dataset_urn, error_message, now, dedup_key),
            )
            conn.commit()
            conn.close()
        logger.debug("Saved incident %s", incident_id)

    def update_incident(
        self,
        incident_id: str,
        status: str = "resolved",
        root_causes: list[dict[str, Any]] | None = None,
        agent_results: dict[str, Any] | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        """Update an incident with results from the completed pipeline."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._conn()
            conn.execute(
                """UPDATE incidents
                   SET status = ?, root_causes = ?, agent_results = ?,
                       elapsed_seconds = ?, resolved_at = ?
                   WHERE id = ?""",
                (
                    status,
                    json.dumps(root_causes) if root_causes else None,
                    json.dumps(agent_results) if agent_results else None,
                    elapsed_seconds,
                    now if status == "resolved" else None,
                    incident_id,
                ),
            )
            conn.commit()
            conn.close()
        logger.debug("Updated incident %s -> %s", incident_id, status)

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        """Retrieve a single incident by ID."""
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            conn.close()
        return self._row_to_dict(row) if row else None

    def list_incidents(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List incidents, optionally filtered by status."""
        with self._lock:
            conn = self._conn()
            if status:
                rows = conn.execute(
                    "SELECT * FROM incidents WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            conn.close()
        return [self._row_to_dict(r) for r in rows]

    def find_recent(
        self, dedup_key: str, within_seconds: int = 900
    ) -> dict[str, Any] | None:
        """Find a recent incident with the same dedup key.

        Used for incident deduplication — if the same assertion+dataset
        failed within the window, return the existing incident.
        """
        with self._lock:
            conn = self._conn()
            row = conn.execute(
                """SELECT * FROM incidents
                   WHERE dedup_key = ? AND status = 'active'
                     AND created_at >= datetime('now', ?)
                   ORDER BY created_at DESC LIMIT 1""",
                (dedup_key, f"-{within_seconds} seconds"),
            ).fetchone()
            conn.close()
        return self._row_to_dict(row) if row else None

    def get_metrics(self) -> dict[str, Any]:
        """Return aggregate metrics for dashboard."""
        with self._lock:
            conn = self._conn()
            total = conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE status = 'active'"
            ).fetchone()[0]
            resolved = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE status = 'resolved'"
            ).fetchone()[0]
            avg_mttr = conn.execute(
                "SELECT AVG(elapsed_seconds) FROM incidents WHERE status = 'resolved' AND elapsed_seconds IS NOT NULL"
            ).fetchone()[0]
            conn.close()
        return {
            "total": total,
            "active": active,
            "resolved": resolved,
            "avg_mttr_seconds": round(avg_mttr, 2) if avg_mttr else 0,
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for key in ("root_causes", "agent_results"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
