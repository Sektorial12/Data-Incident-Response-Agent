"""Seed the incident store with test data and start the API server.

Usage:
    cd code && python scripts/seed_and_serve.py
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.server import create_app
from src.store.incident_store import IncidentStore

import uvicorn


def seed():
    store = IncidentStore()

    # Active incident — high confidence root cause
    inc1_id = str(uuid.uuid4())
    store.save_incident(
        incident_id=inc1_id,
        assertion_urn="urn:li:assertion:billing_amount_not_negative",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,billing.mart_revenue,PROD)",
        error_message="billing_amount has negative values",
        dedup_key="urn:li:assertion:billing_amount_not_negative|urn:li:dataset:(urn:li:dataPlatform:snowflake,billing.mart_revenue,PROD)",
    )
    store.update_incident(
        incident_id=inc1_id,
        status="active",
        root_causes=[
            {
                "candidate_urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stg_payments,PROD)",
                "confidence": 0.92,
                "reasoning": "Upstream stg_payments table has NULL values in amount column, propagated through mart_revenue",
            },
            {
                "candidate_urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stg_refunds,PROD)",
                "confidence": 0.65,
                "reasoning": "Refund amounts are negative by design but not filtered before joining into mart_revenue",
            },
        ],
        agent_results={
            "tracer": {"status": "completed", "result": {"candidates": 5}},
            "checker": {"status": "completed", "result": {"validated": 2}},
            "notifier": {"status": "completed", "result": {"notified": True}},
            "reporter": {"status": "completed", "result": {"document_urn": "urn:li:document:incident_report_001"}},
        },
        elapsed_seconds=12.4,
    )

    # Resolved incident
    inc2_id = str(uuid.uuid4())
    store.save_incident(
        incident_id=inc2_id,
        assertion_urn="urn:li:assertion:patient_id_not_null",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:bigquery,healthcare.patients,PROD)",
        error_message="patient_id contains NULL values",
        dedup_key="urn:li:assertion:patient_id_not_null|urn:li:dataset:(urn:li:dataPlatform:bigquery,healthcare.patients,PROD)",
    )
    store.update_incident(
        incident_id=inc2_id,
        status="resolved",
        root_causes=[
            {
                "candidate_urn": "urn:li:dataset:(urn:li:dataPlatform:bigquery,raw.patient_intake,PROD)",
                "confidence": 0.88,
                "reasoning": "patient_intake staging table missing NOT NULL constraint on patient_id column",
            },
        ],
        agent_results={
            "tracer": {"status": "completed"},
            "checker": {"status": "completed"},
            "notifier": {"status": "completed"},
            "reporter": {"status": "completed"},
        },
        elapsed_seconds=8.7,
    )

    # Another resolved incident with a failed agent
    inc3_id = str(uuid.uuid4())
    store.save_incident(
        incident_id=inc3_id,
        assertion_urn="urn:li:assertion:order_count_daily_check",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:redshift,sales.daily_orders,PROD)",
        error_message="Daily order count dropped below threshold",
        dedup_key="urn:li:assertion:order_count_daily_check|urn:li:dataset:(urn:li:dataPlatform:redshift,sales.daily_orders,PROD)",
    )
    store.update_incident(
        incident_id=inc3_id,
        status="resolved",
        root_causes=[
            {
                "candidate_urn": "urn:li:dataset:(urn:li:dataPlatform:redshift,raw.orders_stream,PROD)",
                "confidence": 0.55,
                "reasoning": "Orders stream had a partial outage, reduced volume propagated to daily aggregation",
            },
        ],
        agent_results={
            "tracer": {"status": "completed"},
            "checker": {"status": "completed"},
            "notifier": {"status": "failed", "error": "webhook timeout"},
            "reporter": {"status": "completed"},
        },
        elapsed_seconds=22.1,
    )

    all_incidents = store.list_incidents(limit=100)
    print(f"Seeded {len(all_incidents)} incidents")
    return store


if __name__ == "__main__":
    store = seed()
    app = create_app(store)
    print("Starting API server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
