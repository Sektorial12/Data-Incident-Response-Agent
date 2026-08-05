"""Reporter Agent — generates incident reports and writes them back to DataHub.

Creates a comprehensive markdown incident report, saves it as a document
on the failing dataset, and tags the root cause dataset.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from src.agents.base import BaseAgent
from src.agents.protocol import AgentMessage
from src.mcp_client.client import MCPClient
from src.skills.loader import augment_prompt

logger = logging.getLogger(__name__)

REPORTER_SYSTEM_PROMPT = augment_prompt(
    """\
You are the Reporter Agent in a Data Incident Response system.
Given an incident with validated root causes, your job is to:
1. Generate a comprehensive incident report in markdown
2. Include: incident summary, timeline, root cause analysis, lineage path,
   affected datasets, recommended actions
3. Save the report as a document on the failing dataset in DataHub
4. Tag the root cause dataset with "incident-root-cause" tag
5. Update the failing dataset's description to reference the incident
""",
    "datahub-enrich",
)


class ReporterAgent(BaseAgent):
    """Generates and saves incident reports to DataHub."""

    name = "reporter"
    system_prompt = REPORTER_SYSTEM_PROMPT

    def __init__(
        self, mcp_client: MCPClient, config: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mcp_client, config)

    def run(self, message: AgentMessage) -> AgentMessage:
        """Generate report and write back to DataHub."""
        self._log_start(message)

        dataset_urn = message.context.get("dataset_urn", "")
        assertion_urn = message.context.get("assertion_urn", "")
        error_message = message.context.get("error_message", "")
        tracer_result = message.context.get("tracer_result") or {}
        checker_result = message.context.get("checker_result") or {}

        report = self._generate_report(
            dataset_urn=dataset_urn,
            assertion_urn=assertion_urn,
            error_message=error_message,
            tracer_result=tracer_result,
            checker_result=checker_result,
        )

        document_urn = None
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        try:
            doc_result = self.mcp.save_document(
                document_type="Note",
                title=f"Incident Report — {self._extract_dataset_name(dataset_urn)}",
                content=report,
                related_assets=[dataset_urn],
            )
            document_urn = (
                doc_result.get("urn") if isinstance(doc_result, dict) else None
            )
            self.logger.info("Incident report saved to DataHub: %s", document_urn)
        except Exception as e:
            self.logger.error("Failed to save document: %s", e)

        validated = checker_result.get("validated_candidates", [])
        root_cause_urns = [
            v.get("candidate_urn", "") for v in validated if v.get("candidate_urn")
        ]
        if root_cause_urns:
            try:
                self.mcp.add_tags(
                    tag_urns=["urn:li:tag:incident-root-cause"],
                    entity_urns=root_cause_urns,
                )
                self.logger.info("Tagged %d root cause datasets", len(root_cause_urns))
            except Exception as e:
                self.logger.warning("Failed to tag root cause: %s", e)

        if root_cause_urns:
            for rc_urn in root_cause_urns:
                try:
                    incident_ref = f"\n\n---\n**Incident Report:** {document_urn or 'N/A'} ({timestamp})\n"
                    self.mcp.update_description(rc_urn, incident_ref, operation="append")
                    self.logger.debug("Updated description for %s", rc_urn)
                except Exception as e:
                    self.logger.warning(
                        "Failed to update description for %s: %s", rc_urn, e
                    )

        message.mark_completed(
            {
                "document_urn": document_urn,
                "report_length": len(report),
                "report_preview": report[:500],
            }
        )
        self._log_complete(message)
        return message

    def _generate_report(
        self,
        dataset_urn: str,
        assertion_urn: str,
        error_message: str | None,
        tracer_result: dict[str, Any],
        checker_result: dict[str, Any],
    ) -> str:
        """Generate a markdown incident report."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        dataset_name = self._extract_dataset_name(dataset_urn)

        candidates = tracer_result.get("candidates", [])
        validated = checker_result.get("validated_candidates", [])

        lines: list[str] = [
            "# Data Incident Report",
            "",
            f"**Generated:** {timestamp}",
            f"**Dataset:** `{dataset_name}`",
            f"**Assertion:** `{assertion_urn}`",
            "",
            "## Incident Summary",
            "",
            f"An assertion failure was detected on dataset `{dataset_name}`.",
        ]

        if error_message:
            lines.append(f"**Error:** {error_message}")

        lines.extend(
            [
                "",
                "## Root Cause Analysis",
                "",
            ]
        )

        if validated:
            for i, vc in enumerate(validated, 1):
                candidate_urn = vc.get("candidate_urn", "")
                confidence = vc.get("confidence", 0)
                reasoning = vc.get("reasoning", "unknown")
                evidence = vc.get("evidence", [])

                lines.append(f"### Candidate {i}: `{candidate_urn}`")
                lines.append(f"- **Status:** {vc.get('status', 'unknown')}")
                lines.append(f"- **Confidence:** {confidence:.0%}")
                lines.append(f"- **Reasoning:** {reasoning}")
                if evidence:
                    lines.append(f"- **Evidence:** {', '.join(evidence)}")
                lines.append("")
        else:
            lines.append("No validated root causes were identified.\n")

        lines.extend(
            [
                "## Lineage Analysis",
                "",
            ]
        )

        if candidates:
            for c in candidates[:5]:
                urn = c.get("urn", "")
                conf = c.get("confidence", 0)
                path = c.get("path", [])
                path_str = (
                    " -> ".join(self._extract_dataset_name(p) for p in path)
                    if path
                    else "N/A"
                )
                lines.append(f"- `{urn}` (confidence: {conf:.0%}, path: {path_str})")
        else:
            lines.append("No upstream candidates were found.")

        lines.extend(
            [
                "",
                "## Recommended Actions",
                "",
                "1. Investigate the root cause dataset(s) identified above",
                "2. Check if the assertion failure is reproducible",
                "3. Review the data pipeline for any recent changes",
                "4. Consider adding additional assertions on upstream datasets",
                "",
                "## Incident Metadata",
                "",
                "- **Agent:** Data Incident Response Agent v0.1",
                "- **Tools used:** MCP Server (get_lineage, get_entities, save_document, add_tags)",
                "- **Pipeline:** Actions Plugin -> Coordinator -> Tracer -> Checker -> Reporter",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _extract_dataset_name(urn: str) -> str:
        """Extract a human-readable name from a dataset URN."""
        if "sqlite," in urn:
            parts = urn.split("sqlite,")
            if len(parts) > 1:
                rest = parts[1].rstrip(")")
                return rest.split(",")[0] if "," in rest else rest
        return urn
