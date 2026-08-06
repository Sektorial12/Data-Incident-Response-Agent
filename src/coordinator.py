"""Coordinator agent — orchestrates the incident response workflow.

Receives IncidentEvent from the DataHub Actions plugin, dispatches to
sub-agents (Tracer, Checker, Notifier, Reporter), and aggregates results.
"""

import logging
import time
import uuid
from typing import Any

from src.agents.base import BaseAgent
from src.agents.protocol import AgentMessage, AgentStatus
from src.datahub_actions_plugin.incident_event import IncidentEvent
from src.mcp_client.client import MCPClient
from src.store.incident_store import IncidentStore

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """Orchestrates the incident response by dispatching to sub-agents."""

    name = "coordinator"

    def __init__(
        self,
        mcp_client: MCPClient,
        config: dict[str, Any] | None = None,
        tracer: BaseAgent | None = None,
        checker: BaseAgent | None = None,
        notifier: BaseAgent | None = None,
        reporter: BaseAgent | None = None,
        store: IncidentStore | None = None,
    ) -> None:
        self.mcp = mcp_client
        self.config = config or {}
        self.tracer = tracer
        self.checker = checker
        self.notifier = notifier
        self.reporter = reporter
        self.timeout_seconds = self.config.get("timeout_seconds", 30)
        self.store = store

    def handle_incident(self, incident: IncidentEvent) -> dict[str, Any]:
        """Main entry point — receive incident and orchestrate response."""
        start_time = time.time()
        logger.info("=== Coordinator handling incident: %s ===", incident.summary())

        incident_id = str(uuid.uuid4())
        dedup_key = f"{incident.assertion_urn}:{incident.dataset_urn}"
        dedup_window = self.config.get("dedup_window_seconds", 900)

        if self.store:
            existing = self.store.find_recent(dedup_key, within_seconds=dedup_window)
            if existing:
                logger.info(
                    "Duplicate incident suppressed (key=%s, existing=%s, age within %ds window)",
                    dedup_key,
                    existing["id"],
                    dedup_window,
                )
                return {
                    "incident_id": existing["id"],
                    "deduplicated": True,
                    "message": "Suppressed duplicate incident within dedup window",
                    "assertion_urn": incident.assertion_urn,
                    "dataset_urn": incident.dataset_urn,
                }
            self.store.save_incident(
                incident_id=incident_id,
                assertion_urn=incident.assertion_urn,
                dataset_urn=incident.dataset_urn,
                error_message=incident.error_message,
                dedup_key=dedup_key,
            )

        results: dict[str, Any] = {
            "incident_id": incident_id,
            "incident": incident.summary(),
            "dataset_urn": incident.dataset_urn,
            "assertion_urn": incident.assertion_urn,
            "status": incident.result_status,
            "agents": {},
        }

        tracer_result = self._dispatch_agent(
            "tracer",
            self.tracer,
            incident,
            extra_context={"dataset_urn": incident.dataset_urn, "max_hops": 3},
        )
        results["agents"]["tracer"] = tracer_result

        candidates = []
        if tracer_result.get("status") == AgentStatus.COMPLETED.value:
            candidates = tracer_result.get("result", {}).get("candidates", [])

        checker_result = self._dispatch_agent(
            "checker",
            self.checker,
            incident,
            extra_context={
                "candidates": candidates,
                "dataset_urn": incident.dataset_urn,
            },
        )
        results["agents"]["checker"] = checker_result

        validated_candidates = []
        if checker_result.get("status") == AgentStatus.COMPLETED.value:
            validated_candidates = checker_result.get("result", {}).get(
                "validated_candidates", []
            )

        notifier_result = self._dispatch_agent(
            "notifier",
            self.notifier,
            incident,
            extra_context={
                "candidates": validated_candidates,
                "dataset_urn": incident.dataset_urn,
            },
        )
        results["agents"]["notifier"] = notifier_result

        reporter_result = self._dispatch_agent(
            "reporter",
            self.reporter,
            incident,
            extra_context={
                "tracer_result": tracer_result.get("result"),
                "checker_result": checker_result.get("result"),
                "dataset_urn": incident.dataset_urn,
            },
        )
        results["agents"]["reporter"] = reporter_result

        elapsed = time.time() - start_time
        results["elapsed_seconds"] = round(elapsed, 2)
        logger.info("=== Coordinator completed in %.2fs ===", elapsed)

        if self.store:
            validated = results.get("agents", {}).get("checker", {}).get(
                "result", {}
            ).get("validated_candidates", [])
            self.store.update_incident(
                incident_id=incident_id,
                status="resolved",
                root_causes=validated,
                agent_results=results.get("agents", {}),
                elapsed_seconds=round(elapsed, 2),
            )

        return results

    def _dispatch_agent(
        self,
        agent_name: str,
        agent: BaseAgent | None,
        incident: IncidentEvent,
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a sub-agent with error handling."""
        if agent is None:
            logger.warning("Agent %s not configured — skipping", agent_name)
            return {"status": "skipped", "reason": "not configured"}

        context: dict[str, Any] = {
            "incident": incident.summary(),
            "assertion_urn": incident.assertion_urn,
            "dataset_urn": incident.dataset_urn,
            "result_status": incident.result_status,
            "error_message": incident.error_message,
        }
        if extra_context:
            context.update(extra_context)

        message = AgentMessage(
            from_agent=self.name,
            to_agent=agent_name,
            task=f"investigate_incident:{incident.assertion_urn}",
            context=context,
        )

        try:
            message.mark_in_progress()
            logger.info("Dispatching %s for task: %s", agent_name, message.task)
            message = agent.run(message)
            if message.is_completed:
                logger.info("%s completed successfully", agent_name)
                return {"status": AgentStatus.COMPLETED.value, "result": message.result}
            elif message.is_failed:
                logger.error("%s failed: %s", agent_name, message.error)
                return {"status": AgentStatus.FAILED.value, "error": message.error}
            else:
                logger.warning(
                    "%s returned unexpected status: %s", agent_name, message.status
                )
                return {"status": message.status.value, "result": message.result}
        except Exception as e:
            logger.error("%s raised exception: %s", agent_name, e)
            return {"status": AgentStatus.FAILED.value, "error": str(e)}


def handle_incident(incident: IncidentEvent) -> dict[str, Any] | None:
    """Callback for the DataHub Actions plugin.

    Creates a CoordinatorAgent with MCP client and all sub-agents wired,
    then dispatches the incident response pipeline.
    """
    from src.agents.checker import CheckerAgent
    from src.agents.notifier import NotifierAgent
    from src.agents.reporter import ReporterAgent
    from src.agents.tracer import TracerAgent
    from src.llm.client import LLMClient

    mcp = MCPClient()
    llm = LLMClient.from_env()
    store = IncidentStore()
    coordinator = CoordinatorAgent(
        mcp_client=mcp,
        tracer=TracerAgent(mcp),
        checker=CheckerAgent(mcp, llm_client=llm),
        notifier=NotifierAgent(mcp),
        reporter=ReporterAgent(mcp),
        store=store,
    )
    try:
        result = coordinator.handle_incident(incident)
        logger.info("Incident response result: %s", result)
        return result
    except Exception as e:
        logger.error("Coordinator failed: %s", e)
        return None
