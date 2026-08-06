"""Event filtering for DataHub Actions plugin.

Filters MetadataChangeLogEvent_v1 events to only pass through
assertion run events that represent failures.
"""

import json
import logging

from datahub_actions.event.event_envelope import EventEnvelope

logger = logging.getLogger(__name__)


def is_assertion_failure_event(event: EventEnvelope) -> bool:
    """Check if an event is an assertion run event with a failure status.

    Args:
        event: The EventEnvelope from the Kafka source.

    Returns:
        True if the event represents an assertion failure, False otherwise.
    """
    event_type = getattr(event, "event_type", None)
    if event_type != "MetadataChangeLogEvent_v1":
        return False

    payload = event.event if hasattr(event, "event") else {}
    if not hasattr(payload, "get"):
        return False

    entity_type = payload.get("entityType", "")
    aspect_name = payload.get("aspectName", "")
    change_type = payload.get("changeType", "")

    if entity_type != "assertion":
        return False

    if aspect_name != "assertionRunEvent":
        return False

    if change_type not in ("UPSERT", "CREATE", "RESTATE"):
        return False

    aspect = payload.get("aspect")
    if not aspect or not hasattr(aspect, "get"):
        return False

    aspect_value_str = aspect.get("value")
    if not aspect_value_str:
        return False

    try:
        aspect_value = json.loads(aspect_value_str)
    except (json.JSONDecodeError, TypeError):
        logger.debug("Could not parse aspect value as JSON")
        return False

    result = aspect_value.get("result", {})
    result_type = ""
    if isinstance(result, dict):
        result_type = result.get("type", "")

    return result_type.upper() in ("FAILURE", "ERROR")
