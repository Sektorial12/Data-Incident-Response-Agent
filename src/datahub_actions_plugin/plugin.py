"""DataHub Actions plugin for the Data Incident Response Agent.

Listens for assertion failure events via the DataHub Actions framework,
extracts structured incident data, and dispatches to the coordinator.
"""

import json
import logging
from collections.abc import Callable

from datahub_actions.action.action import Action
from datahub_actions.event.event_envelope import EventEnvelope
from datahub_actions.pipeline.pipeline_context import PipelineContext

from src.datahub_actions_plugin.filters import is_assertion_failure_event
from src.datahub_actions_plugin.incident_event import IncidentEvent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class IncidentResponseAction(Action):
    """Action that receives assertion failure events and dispatches to the coordinator."""

    @classmethod
    def create(
        cls, config_dict: dict, ctx: PipelineContext
    ) -> "IncidentResponseAction":
        callback_module = config_dict.get("callback_module")
        callback_function = config_dict.get("callback_function", "handle_incident")
        datahub_server = config_dict.get("datahub_server", "http://localhost:8080")
        datahub_token = config_dict.get("datahub_token", "")

        callback: Callable[[IncidentEvent], None] | None = None
        if callback_module:
            try:
                import importlib

                mod = importlib.import_module(callback_module)
                callback = getattr(mod, callback_function)
                logger.info(
                    "Loaded incident callback: %s.%s",
                    callback_module,
                    callback_function,
                )
            except (ImportError, AttributeError) as e:
                logger.warning(
                    "Could not load callback %s.%s: %s",
                    callback_module,
                    callback_function,
                    e,
                )

        return cls(ctx, callback, datahub_server, datahub_token)

    def __init__(
        self,
        ctx: PipelineContext,
        callback: Callable[[IncidentEvent], None] | None = None,
        datahub_server: str = "http://localhost:8080",
        datahub_token: str = "",
    ) -> None:
        self.ctx = ctx
        self.callback = callback
        self.datahub_server = datahub_server
        self.datahub_token = datahub_token
        self._events_received = 0
        self._incidents_dispatched = 0

    def act(self, event: EventEnvelope) -> None:
        self._events_received += 1

        if not is_assertion_failure_event(event):
            return

        incident = self._extract_incident(event)
        if incident is None:
            return

        logger.info("Assertion failure detected: %s", incident.summary())

        if self.callback:
            try:
                self.callback(incident)
                self._incidents_dispatched += 1
            except Exception as e:
                logger.error(
                    "Callback failed for incident %s: %s", incident.assertion_urn, e
                )
        else:
            logger.warning(
                "No callback configured — incident logged only: %s", incident.summary()
            )

    def _extract_incident(self, event: EventEnvelope) -> IncidentEvent | None:
        payload = event.event if hasattr(event, "event") else {}
        if not hasattr(payload, "get"):
            return None

        assertion_urn = payload.get("entityUrn", "")
        aspect = payload.get("aspect", {})
        aspect_value_str = aspect.get("value", "{}") if hasattr(aspect, "get") else "{}"

        try:
            aspect_value = json.loads(aspect_value_str)
        except (json.JSONDecodeError, TypeError):
            logger.error("Could not parse aspect value for assertion %s", assertion_urn)
            return None

        status = aspect_value.get("status", "UNKNOWN")
        result = aspect_value.get("result", {})
        result_status = "UNKNOWN"
        if isinstance(result, dict):
            result_status = result.get("type", status)
        assertee_urn = aspect_value.get("asserteeUrn", "")
        run_id = aspect_value.get("runId", "")
        timestamp_ms = aspect_value.get("timestampMillis", 0)

        result = aspect_value.get("result", {})
        error_message = None
        if isinstance(result, dict):
            error_message = result.get("errorMessage")

        return IncidentEvent(
            assertion_urn=assertion_urn,
            dataset_urn=assertee_urn,
            assertion_type="DATASET_ROWS",
            result_status=result_status,
            timestamp_ms=timestamp_ms,
            run_id=run_id,
            error_message=error_message,
            raw_event=payload,
        )

    def close(self) -> None:
        logger.info(
            "IncidentResponseAction shutting down — events received: %d, incidents dispatched: %d",
            self._events_received,
            self._incidents_dispatched,
        )


def create_action(config_dict: dict, ctx: PipelineContext) -> Action:
    """Factory function for the DataHub Actions framework."""
    return IncidentResponseAction.create(config_dict, ctx)
