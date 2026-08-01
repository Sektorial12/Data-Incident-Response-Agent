"""Checker Agent — validates candidate root causes from the Tracer.

Given a candidate root cause and the original assertion failure, retrieves
metadata, checks for failed assertions, schema changes, freshness issues,
and returns a validation result: confirmed, probable, or rejected.
"""

import logging
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from src.agents.base import BaseAgent
from src.agents.protocol import AgentMessage
from src.mcp_client.client import MCPClient

logger = logging.getLogger(__name__)

CHECKER_SYSTEM_PROMPT = """\
You are the Checker Agent in a Data Incident Response system.
Given a candidate root cause and the original assertion failure, your job is to:
1. Retrieve the candidate's metadata (assertions, schema, freshness, documents)
2. Determine if the candidate's issues could explain the assertion failure
3. Check if the candidate has its own failed assertions
4. Check if the candidate's schema changed recently
5. Check if the candidate has freshness issues
6. Search for any incident documents related to this dataset
7. Return a validation result: confirmed, probable, or rejected, with reasoning
"""


class ValidationStatus(str, Enum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    REJECTED = "rejected"


@dataclass
class ValidationResult:
    """Result of validating a candidate root cause."""

    candidate_urn: str
    status: ValidationStatus
    confidence: float
    reasoning: str
    evidence: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "status": self.status.value,
        }


class CheckerAgent(BaseAgent):
    """Validates candidate root causes by examining metadata."""

    name = "checker"
    system_prompt = CHECKER_SYSTEM_PROMPT

    def __init__(self, mcp_client: MCPClient, config: dict[str, Any] | None = None) -> None:
        super().__init__(mcp_client, config)
        self.confidence_threshold = self.config.get("confidence_threshold", 0.5)

    def run(self, message: AgentMessage) -> AgentMessage:
        """Execute the validation workflow."""
        self._log_start(message)

        candidates = message.context.get("candidates", [])
        if not candidates:
            message.mark_completed({"validated_candidates": [], "summary": "no candidates to validate"})
            self._log_complete(message)
            return message

        results: list[dict[str, Any]] = []
        for candidate in candidates:
            urn = candidate.get("urn", "")
            if not urn:
                continue
            validation = self._validate_candidate(urn, candidate, message.context)
            results.append(validation.to_dict())

        confirmed = [r for r in results if r["status"] == ValidationStatus.CONFIRMED.value]
        probable = [r for r in results if r["status"] == ValidationStatus.PROBABLE.value]
        validated = confirmed + probable

        self.logger.info(
            "Validated %d candidates: %d confirmed, %d probable, %d rejected",
            len(results),
            len(confirmed),
            len(probable),
            len(results) - len(confirmed) - len(probable),
        )

        message.mark_completed({
            "validated_candidates": validated,
            "all_results": results,
            "summary": f"{len(confirmed)} confirmed, {len(probable)} probable, {len(results) - len(validated)} rejected",
        })
        self._log_complete(message)
        return message

    def _validate_candidate(
        self,
        urn: str,
        candidate: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """Validate a single candidate root cause."""
        self.logger.debug("Validating candidate: %s", urn)

        evidence: list[str] = []
        confidence = candidate.get("confidence", 0.0)
        reasons: list[str] = []

        try:
            entities_result = self.mcp.get_entities([urn])
            entity_info = self._extract_entity_info(entities_result, urn)
        except Exception as e:
            self.logger.debug("Could not get entities for %s: %s", urn, e)
            entity_info = {}

        if entity_info.get("has_failed_assertions"):
            evidence.append("candidate has its own failed assertions")
            confidence += 0.3
            reasons.append("failed assertions on upstream node")

        if entity_info.get("recently_modified"):
            evidence.append("candidate schema was recently modified")
            confidence += 0.2
            reasons.append("schema modification detected")

        if entity_info.get("freshness_stale"):
            evidence.append("candidate has freshness issues")
            confidence += 0.15
            reasons.append("freshness issues detected")

        try:
            search_result = self.mcp.search(urn, num_results=5)
            related_docs = self._count_related_documents(search_result, urn)
            if related_docs > 0:
                evidence.append(f"found {related_docs} related documents")
                confidence += 0.1
        except Exception as e:
            self.logger.debug("Search failed for %s: %s", urn, e)

        confidence = min(confidence, 1.0)

        if confidence >= 0.7:
            status = ValidationStatus.CONFIRMED
        elif confidence >= self.confidence_threshold:
            status = ValidationStatus.PROBABLE
        else:
            status = ValidationStatus.REJECTED

        reasoning = "; ".join(reasons) if reasons else "no specific issues found"
        if status == ValidationStatus.REJECTED:
            reasoning = "insufficient evidence to confirm as root cause"

        return ValidationResult(
            candidate_urn=urn,
            status=status,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            evidence=evidence,
        )

    def _extract_entity_info(self, entities_result: dict[str, Any], urn: str) -> dict[str, Any]:
        """Extract relevant info from get_entities response."""
        info: dict[str, Any] = {}

        if isinstance(entities_result, dict):
            entities = entities_result.get("entities", [])
            for entity in entities:
                if isinstance(entity, dict) and entity.get("urn") == urn:
                    aspects = entity.get("aspects", [])
                    for aspect in aspects:
                        if isinstance(aspect, dict):
                            name = aspect.get("name", "")
                            if name == "assertionRunEvents":
                                info["has_failed_assertions"] = True
                            if name == "schemaMetadata":
                                info["recently_modified"] = True
                            if name == "datasetProperties":
                                info["freshness_stale"] = False
                    break

        return info

    def _count_related_documents(self, search_result: dict[str, Any], urn: str) -> int:
        """Count documents related to this URN in search results."""
        if isinstance(search_result, dict):
            entities = search_result.get("entities", [])
            return sum(
                1
                for e in entities
                if isinstance(e, dict) and "document" in e.get("urn", "").lower()
            )
        return 0
