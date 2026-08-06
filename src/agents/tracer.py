"""Tracer Agent — traces upstream lineage to find root cause candidates.

Given a dataset URN with an assertion failure, retrieves upstream lineage,
examines each node's metadata, and returns ranked candidate root causes.
"""

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from src.agents.base import BaseAgent
from src.agents.entity_utils import extract_entity_info
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
        self.weights = self.config.get("tracer_weights", {
            "failed_assertions": 0.5,
            "recently_modified": 0.3,
            "freshness_stale": 0.2,
            "missing_lineage": 0.05,
            "recently_created": 0.1,
            "default_upstream": 0.1,
        })

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
        """Extract URNs of upstream nodes from lineage response.

        Handles MCP server format: {"upstreams": {"searchResults": [{"entity": {"urn": ...}}]}}
        Also handles legacy format with "relationships" and "entities" keys.
        """
        nodes: list[str] = []

        if isinstance(lineage_result, dict):
            # MCP server format: searchResults under "upstreams" or "downstreams"
            for direction_key in ("upstreams", "downstreams"):
                direction_data = lineage_result.get(direction_key)
                if isinstance(direction_data, dict):
                    search_results = direction_data.get("searchResults", [])
                    for sr in search_results:
                        if isinstance(sr, dict):
                            entity = sr.get("entity", {})
                            if isinstance(entity, dict):
                                urn = entity.get("urn")
                                if urn and urn not in nodes:
                                    nodes.append(urn)

            # Legacy format: relationships / entities at top level
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
            entity_info = extract_entity_info(entities_result, node_urn)
        except Exception as e:
            self.logger.debug("Could not get entities for %s: %s", node_urn, e)
            entity_info = {}

        if entity_info.get("has_failed_assertions"):
            confidence += self.weights["failed_assertions"]
            reasons.append("has failed assertions")

        if entity_info.get("recently_modified"):
            confidence += self.weights["recently_modified"]
            reasons.append("recently modified")

        if entity_info.get("freshness_stale"):
            confidence += self.weights["freshness_stale"]
            reasons.append("freshness stale")

        if entity_info.get("missing_lineage"):
            confidence += self.weights["missing_lineage"]
            reasons.append("incomplete lineage")

        if entity_info.get("recently_created"):
            confidence += self.weights["recently_created"]
            reasons.append("recently created node")

        confidence = min(confidence, 1.0)

        if not reasons:
            confidence = self.weights["default_upstream"]
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
