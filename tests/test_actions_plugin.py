"""Tests for the DataHub Actions plugin event filtering and extraction."""

import json
import logging
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from src.datahub_actions_plugin.filters import is_assertion_failure_event
from src.datahub_actions_plugin.incident_event import IncidentEvent
from src.datahub_actions_plugin.plugin import IncidentResponseAction

logging.disable(logging.CRITICAL)


@dataclass
class MockEventEnvelope:
    event_type: str
    event: Any


def make_mcl_event(
    entity_type: str = "assertion",
    aspect_name: str = "assertionRunEvent",
    change_type: str = "UPSERT",
    aspect_value: dict | None = None,
    entity_urn: str = "urn:li:assertion:test-assertion",
) -> MockEventEnvelope:
    if aspect_value is None:
        aspect_value = {
            "status": "COMPLETE",
            "asserteeUrn": "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)",
            "runId": "test-run-1",
            "timestampMillis": 1700000000000,
            "result": {"type": "FAILURE", "errorMessage": "billing_amount has negative values"},
        }
    return MockEventEnvelope(
        event_type="MetadataChangeLogEvent_v1",
        event={
            "entityType": entity_type,
            "entityUrn": entity_urn,
            "changeType": change_type,
            "aspectName": aspect_name,
            "aspect": {
                "value": json.dumps(aspect_value),
                "contentType": "application/json",
            },
        },
    )


class TestEventFiltering:
    def test_accepts_assertion_failure_event(self):
        event = make_mcl_event()
        assert is_assertion_failure_event(event) is True

    def test_rejects_non_assertion_entity_type(self):
        event = make_mcl_event(entity_type="dataset")
        assert is_assertion_failure_event(event) is False

    def test_rejects_non_assertion_aspect(self):
        event = make_mcl_event(aspect_name="schemaMetadata")
        assert is_assertion_failure_event(event) is False

    def test_rejects_success_status(self):
        event = make_mcl_event(
            aspect_value={
                "status": "SUCCESS",
                "asserteeUrn": "urn:li:dataset:test",
                "timestampMillis": 1,
            }
        )
        assert is_assertion_failure_event(event) is False

    def test_rejects_wrong_event_type(self):
        event = MockEventEnvelope(event_type="EntityChangeEvent_v1", event={})
        assert is_assertion_failure_event(event) is False

    def test_rejects_delete_change_type(self):
        event = make_mcl_event(change_type="DELETE")
        assert is_assertion_failure_event(event) is False

    def test_accepts_error_result_type(self):
        event = make_mcl_event(
            aspect_value={
                "status": "COMPLETE",
                "result": {"type": "ERROR"},
                "asserteeUrn": "urn:li:dataset:test",
                "timestampMillis": 1,
            }
        )
        assert is_assertion_failure_event(event) is True


class TestIncidentExtraction:
    def test_extracts_incident_fields(self):
        ctx = MagicMock()
        action = IncidentResponseAction(ctx)
        event = make_mcl_event()
        incident = action._extract_incident(event)
        assert incident is not None
        assert incident.assertion_urn == "urn:li:assertion:test-assertion"
        assert incident.result_status == "FAILURE"
        assert incident.run_id == "test-run-1"
        assert incident.timestamp_ms == 1700000000000
        assert incident.error_message == "billing_amount has negative values"
        assert incident.is_failure is True

    def test_returns_none_for_unparseable_aspect(self):
        ctx = MagicMock()
        action = IncidentResponseAction(ctx)
        event = MockEventEnvelope(
            event_type="MetadataChangeLogEvent_v1",
            event={
                "entityType": "assertion",
                "entityUrn": "urn:li:assertion:test",
                "aspectName": "assertionRunEvent",
                "changeType": "UPSERT",
                "aspect": {"value": "not-json", "contentType": "application/json"},
            },
        )
        incident = action._extract_incident(event)
        assert incident is None


class TestIncidentEvent:
    def test_is_failure_true_for_failed(self):
        incident = IncidentEvent(
            assertion_urn="urn:li:assertion:x",
            dataset_urn="urn:li:dataset:y",
            assertion_type="DATASET_ROWS",
            result_status="FAILED",
            timestamp_ms=0,
        )
        assert incident.is_failure is True

    def test_is_failure_true_for_error(self):
        incident = IncidentEvent(
            assertion_urn="urn:li:assertion:x",
            dataset_urn="urn:li:dataset:y",
            assertion_type="DATASET_ROWS",
            result_status="ERROR",
            timestamp_ms=0,
        )
        assert incident.is_failure is True

    def test_is_failure_false_for_success(self):
        incident = IncidentEvent(
            assertion_urn="urn:li:assertion:x",
            dataset_urn="urn:li:dataset:y",
            assertion_type="DATASET_ROWS",
            result_status="SUCCESS",
            timestamp_ms=0,
        )
        assert incident.is_failure is False

    def test_summary_includes_name_when_present(self):
        incident = IncidentEvent(
            assertion_urn="urn:li:assertion:x",
            dataset_urn="urn:li:dataset:y",
            assertion_type="DATASET_ROWS",
            result_status="FAILED",
            timestamp_ms=0,
            assertion_name="billingAmountPositive",
        )
        assert "billingAmountPositive" in incident.summary()


class TestActionDispatch:
    def test_callback_invoked_on_failure_event(self):
        callback = MagicMock()
        ctx = MagicMock()
        action = IncidentResponseAction(ctx, callback=callback)
        event = make_mcl_event()
        action.act(event)
        callback.assert_called_once()
        incident = callback.call_args[0][0]
        assert isinstance(incident, IncidentEvent)
        assert incident.result_status == "FAILURE"

    def test_callback_not_invoked_on_non_failure(self):
        callback = MagicMock()
        ctx = MagicMock()
        action = IncidentResponseAction(ctx, callback=callback)
        event = make_mcl_event(entity_type="dataset")
        action.act(event)
        callback.assert_not_called()

    def test_no_callback_logs_warning(self):
        ctx = MagicMock()
        action = IncidentResponseAction(ctx, callback=None)
        event = make_mcl_event()
        # Should not raise
        action.act(event)
