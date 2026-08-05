"""Tests for the Checker Agent."""

import logging
from unittest.mock import MagicMock

from src.agents.checker import CheckerAgent, ValidationResult, ValidationStatus
from src.agents.protocol import AgentMessage
from src.mcp_client.client import MCPClient

logging.disable(logging.CRITICAL)

CANDIDATE_URN_1 = (
    "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.staging_patients,PROD)"
)
CANDIDATE_URN_2 = (
    "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)"
)


def make_mcp_mock(
    entity_aspects: dict[str, list[dict]] | None = None,
    search_docs: int = 0,
) -> MagicMock:
    mcp = MagicMock(spec=MCPClient)

    def get_entities_side_effect(urns):
        result = {"entities": []}
        for urn in urns:
            aspects = (entity_aspects or {}).get(urn, [])
            result["entities"].append({"urn": urn, "name": urn, "aspects": aspects})
        return result

    mcp.get_entities.side_effect = get_entities_side_effect

    search_entities = [{"urn": f"urn:li:document:doc_{i}"} for i in range(search_docs)]
    mcp.search.return_value = {"entities": search_entities}

    return mcp


def make_noop_llm() -> MagicMock:
    """Mock LLM that reports unavailable so tests use heuristic-only mode."""
    llm = MagicMock()
    llm.is_available.return_value = False
    llm.assess_json.return_value = None
    return llm


def make_message(candidates: list[dict]) -> AgentMessage:
    return AgentMessage(
        from_agent="coordinator",
        to_agent="checker",
        task="validate_candidates",
        context={"candidates": candidates, "dataset_urn": "urn:li:dataset:failing"},
    )


class TestCheckerAgent:
    def test_no_candidates_returns_empty(self):
        mcp = make_mcp_mock()
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        result = agent.run(make_message([]))
        assert result.is_completed
        assert result.result["validated_candidates"] == []

    def test_confirmed_with_failed_assertions(self):
        aspects = {CANDIDATE_URN_1: [{"name": "assertionRunEvents"}]}
        mcp = make_mcp_mock(entity_aspects=aspects, search_docs=2)
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        candidates = [{"urn": CANDIDATE_URN_1, "confidence": 0.5}]
        result = agent.run(make_message(candidates))
        assert result.is_completed
        validated = result.result["validated_candidates"]
        assert len(validated) == 1
        assert validated[0]["status"] == ValidationStatus.CONFIRMED.value

    def test_rejected_with_no_evidence(self):
        mcp = make_mcp_mock()
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        candidates = [{"urn": CANDIDATE_URN_1, "confidence": 0.1}]
        result = agent.run(make_message(candidates))
        assert result.is_completed
        all_results = result.result["all_results"]
        assert all_results[0]["status"] == ValidationStatus.REJECTED.value

    def test_probable_with_schema_change(self):
        aspects = {CANDIDATE_URN_1: [{"name": "schemaMetadata"}]}
        mcp = make_mcp_mock(entity_aspects=aspects)
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        candidates = [{"urn": CANDIDATE_URN_1, "confidence": 0.4}]
        result = agent.run(make_message(candidates))
        validated = result.result["validated_candidates"]
        assert len(validated) == 1
        assert validated[0]["status"] == ValidationStatus.PROBABLE.value

    def test_multiple_candidates(self):
        aspects = {
            CANDIDATE_URN_1: [{"name": "assertionRunEvents"}],
            CANDIDATE_URN_2: [],
        }
        mcp = make_mcp_mock(entity_aspects=aspects)
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        candidates = [
            {"urn": CANDIDATE_URN_1, "confidence": 0.5},
            {"urn": CANDIDATE_URN_2, "confidence": 0.1},
        ]
        result = agent.run(make_message(candidates))
        assert result.is_completed
        validated = result.result["validated_candidates"]
        urns = [v["candidate_urn"] for v in validated]
        assert CANDIDATE_URN_1 in urns
        assert CANDIDATE_URN_2 not in urns

    def test_entity_error_handled(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.get_entities.side_effect = RuntimeError("connection failed")
        mcp.search.return_value = {"entities": []}
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        candidates = [{"urn": CANDIDATE_URN_1, "confidence": 0.3}]
        result = agent.run(make_message(candidates))
        assert result.is_completed
        all_results = result.result["all_results"]
        assert all_results[0]["status"] == ValidationStatus.REJECTED.value

    def test_confidence_capped_at_1(self):
        aspects = {
            CANDIDATE_URN_1: [
                {"name": "assertionRunEvents"},
                {"name": "schemaMetadata"},
            ]
        }
        mcp = make_mcp_mock(entity_aspects=aspects, search_docs=3)
        agent = CheckerAgent(mcp, llm_client=make_noop_llm())
        candidates = [{"urn": CANDIDATE_URN_1, "confidence": 0.9}]
        result = agent.run(make_message(candidates))
        validated = result.result["validated_candidates"]
        assert validated[0]["confidence"] <= 1.0


class TestValidationResult:
    def test_to_dict(self):
        vr = ValidationResult(
            candidate_urn="test",
            status=ValidationStatus.CONFIRMED,
            confidence=0.9,
            reasoning="failed assertions",
            evidence=["evidence1"],
        )
        d = vr.to_dict()
        assert d["status"] == "confirmed"
        assert d["confidence"] == 0.9
        assert d["candidate_urn"] == "test"
