"""Coordinator agent — entry point for incident response.

Receives IncidentEvent from the DataHub Actions plugin and dispatches
to sub-agents (Tracer, Checker, Notifier, Reporter).
"""

import logging

from src.datahub_actions_plugin.incident_event import IncidentEvent

logger = logging.getLogger(__name__)


def handle_incident(incident: IncidentEvent) -> None:
    """Handle an assertion failure incident.

    This is the callback invoked by the DataHub Actions plugin.
    Currently a stub — will be expanded in Phase 3.
    """
    logger.info("Coordinator received incident: %s", incident.summary())
    logger.info("Dataset URN: %s", incident.dataset_urn)
    logger.info("Assertion URN: %s", incident.assertion_urn)
    logger.info("Status: %s", incident.result_status)
    if incident.error_message:
        logger.info("Error: %s", incident.error_message)

    # Phase 3 will implement:
    # 1. Dispatch Tracer Agent (upstream lineage trace)
    # 2. Dispatch Checker Agent (validate root cause candidates)
    # 3. Dispatch Notifier Agent (Slack alert)
    # 4. Dispatch Reporter Agent (write incident report to DataHub)
    logger.info("Coordinator: sub-agent dispatch not yet implemented (Phase 3)")
