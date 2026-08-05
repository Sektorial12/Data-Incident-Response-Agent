"""Tracer Agent — traces upstream lineage to find root cause candidates.

Given a dataset URN with an assertion failure, retrieves upstream lineage,
examines each node's metadata, and returns ranked candidate root causes.
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from src.agents.base import BaseAgent
from src.agents.protocol import AgentMessage
from src.mcp_client.client import MCPClient
from src.skills.loader import augment_prompt

logger = logging.getLogger(__name__)

TRACER_SYSTEM_PROMPT = augment_prompt(
    """\
You are the Tracer Agent in a Data Incident Response system.
Given a dataset URN with an assertion failure, your job is to:
1. Retrieve the dataset's upstream lineage (up to 3 hops)
2. For each upstream node, examine its metadata (schema, assertions, freshness)
3. Identify candidate root causes: nodes with recent changes, failed assertions,
   schema modifications, or freshness issues
4. For each candidate, use get_lineage_paths_between to find the exact path
   from the candidate to the failing dataset
5. Return a ranked list of candidate root causes with confidence scores
""",
    "datahub-lineage",
)


@dataclass
class CandidateRootCause:
    """A candidate root cause identified by the Tracer Agent."""

    urn: str
    confidence: float
    reason: str
    path: list[str] = field(default_factory=list)
    name: str | None = None
    platform: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TracerAgent(BaseAgent):
    """Traces upstream lineage and identifies root cause candidates."""

    name = "tracer"
    system_prompt = TRACER_SYSTEM_PROMPT

    def __init__(
        self, mcp_client: MCPClient, config: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mcp_client, config)
        self.max_hops = self.config.get("max_lineage_hops", 3)
        self.confidence_threshold = self.config.get("confidence_threshold", 0.05)

    def run(self, message: AgentMessage) -> AgentMessage:
        """Execute the tracing workflow."""
        self._log_start(message)

        dataset_urn = message.context.get("dataset_urn", "")
        max_hops = message.context.get("max_hops", self.max_hops)

        if not dataset_urn:
            message.mark_failed("No dataset_urn in context")
            return message

        try:
            candidates = self._trace_upstream(dataset_urn, max_hops)
            message.mark_completed({"candidates": [c.to_dict() for c in candidates]})
            self._log_complete(message)
        except Exception as e:
            self.logger.error("Tracer failed: %s", e)
            message.mark_failed(str(e))

        return message

    def _trace_upstream(
        self, dataset_urn: str, max_hops: int
    ) -> list[CandidateRootCause]:
        """Retrieve upstream lineage and identify root cause candidates."""
        self.logger.info(
            "Tracing upstream from %s (max %d hops)", dataset_urn, max_hops
        )

        lineage = self.mcp.get_lineage(
            dataset_urn, direction="UPSTREAM", max_hops=max_hops
        )
        upstream_nodes = self._extract_upstream_nodes(lineage)

        self.logger.info("Found %d upstream nodes", len(upstream_nodes))

        candidates: list[CandidateRootCause] = []
        for node_urn in upstream_nodes:
            if node_urn == dataset_urn:
                continue
            candidate = self._evaluate_node(node_urn, dataset_urn)
            if candidate and candidate.confidence >= self.confidence_threshold:
                candidates.append(candidate)

        candidates.sort(key=lambda c: c.confidence, reverse=True)

        if not candidates:
            self.logger.info(
                "No candidates above threshold %.2f", self.confidence_threshold
            )
        else:
            self.logger.info(
                "Identified %d candidates: %s",
                len(candidates),
                ", ".join(f"{c.urn}:{c.confidence:.2f}" for c in candidates),
            )

        return candidates

    def _extract_upstream_nodes(self, lineage_result: dict[str, Any]) -> list[str]:
        """Extract URNs of upstream nodes from lineage response."""
        nodes: list[str] = []

        if isinstance(lineage_result, dict):
            relationships = lineage_result.get("relationships", [])
            for rel in relationships:
                if isinstance(rel, dict):
                    urn = (
                        rel.get("urn")
                        or rel.get("destinationUrn")
                        or rel.get("sourceUrn")
                    )
                    if urn and urn not in nodes:
                        nodes.append(urn)

            entities = lineage_result.get("entities", [])
            for entity in entities:
                if isinstance(entity, dict):
                    urn = entity.get("urn")
                    if urn and urn not in nodes:
                        nodes.append(urn)

        return nodes

    def _evaluate_node(
        self, node_urn: str, failing_dataset_urn: str
    ) -> CandidateRootCause | None:
        """Evaluate a single upstream node as a potential root cause."""
        self.logger.debug("Evaluating node: %s", node_urn)

        confidence = 0.0
        reasons: list[str] = []

        try:
            entities_result = self.mcp.get_entities([node_urn])
            entity_info = self._extract_entity_info(entities_result, node_urn)
        except Exception as e:
            self.logger.debug("Could not get entities for %s: %s", node_urn, e)
            entity_info = {}

        try:
            schema_result = self.mcp.list_schema_fields(node_urn)
            self._count_schema_fields(schema_result)
        except Exception as e:
            self.logger.debug("Could not get schema for %s: %s", node_urn, e)

        if entity_info.get("has_failed_assertions"):
            confidence += 0.5
            reasons.append("has failed assertions")

        if entity_info.get("recently_modified"):
            confidence += 0.3
            reasons.append("recently modified")

        if entity_info.get("freshness_stale"):
            confidence += 0.2
            reasons.append("freshness stale")

        if entity_info.get("missing_lineage"):
            confidence += 0.05
            reasons.append("incomplete lineage")

        if entity_info.get("recently_created"):
            confidence += 0.1
            reasons.append("recently created node")

        confidence = min(confidence, 1.0)

        if not reasons:
            confidence = 0.1
            reasons.append("upstream node in lineage path")

        path = self._find_path(node_urn, failing_dataset_urn)

        return CandidateRootCause(
            urn=node_urn,
            confidence=confidence,
            reason="; ".join(reasons),
            path=path,
            name=entity_info.get("name"),
            platform=entity_info.get("platform"),
        )

    def _extract_entity_info(
        self, entities_result: dict[str, Any], urn: str
    ) -> dict[str, Any]:
        """Extract relevant info from get_entities response."""
        info: dict[str, Any] = {}

        if isinstance(entities_result, dict):
            entities = entities_result.get("entities", [])
            for entity in entities:
                if isinstance(entity, dict) and entity.get("urn") == urn:
                    info["name"] = entity.get("name") or entity.get("qualifiedName")
                    info["platform"] = entity.get("platform")
                    aspects = entity.get("aspects", [])
                    aspect_names = set()
                    for aspect in aspects:
                        if isinstance(aspect, dict):
                            aspect_name = aspect.get("name", "")
                            aspect_names.add(aspect_name)
                            if aspect_name == "assertionRunEvents":
                                info["has_failed_assertions"] = True
                            if aspect_name == "schemaMetadata":
                                info["recently_modified"] = True
                            if aspect_name == "datasetProperties":
                                info["freshness_stale"] = False
                            if aspect_name == "dataPlatformInfo":
                                created = aspect.get("created", {})
                                if isinstance(created, dict):
                                    created_time = created.get("time")
                                    if created_time:
                                        import time as _time

                                        age_seconds = (
                                            _time.time() * 1000 - created_time
                                        ) / 1000
                                        if age_seconds < 86400 * 7:
                                            info["recently_created"] = True

                    if "upstreamLineage" not in aspect_names:
                        info["missing_lineage"] = True
                    break

        return info

    def _count_schema_fields(self, schema_result: dict[str, Any]) -> int:
        """Count schema fields from list_schema_fields response."""
        if isinstance(schema_result, dict):
            fields = schema_result.get("fields", [])
            return len(fields) if isinstance(fields, list) else 0
        return 0

    def _find_path(self, source_urn: str, target_urn: str) -> list[str]:
        """Find lineage path between two URNs."""
        try:
            result = self.mcp.get_lineage_paths_between(
                source_urn=source_urn,
                target_urn=target_urn,
                direction="downstream",
            )
            if isinstance(result, dict):
                paths = result.get("paths", [])
                if paths and isinstance(paths[0], list):
                    return paths[0]
                if paths and isinstance(paths[0], dict):
                    return [p.get("urn", str(p)) for p in paths[0].get("nodes", [])]
        except Exception as e:
            self.logger.debug(
                "Could not find path %s -> %s: %s", source_urn, target_urn, e
            )

        return [source_urn, target_urn]
