"""Tests for the LLM client and LLM-enhanced Checker agent."""

from unittest.mock import MagicMock, patch

from src.agents.checker import CheckerAgent, ValidationStatus
from src.agents.protocol import AgentMessage
from src.llm.client import LLMClient
from src.mcp_client.client import MCPClient


class TestLLMClient:
    def test_no_api_key_returns_unavailable(self):
        with patch.dict("os.environ", {}, clear=True):
            client = LLMClient.from_env()
            assert not client.is_available()

    def test_anthropic_key_detected(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            client = LLMClient.from_env()
            assert client.provider == "anthropic"

    def test_openai_fallback_when_no_anthropic(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            client = LLMClient.from_env()
            assert client.provider == "openai"

    def test_anthropic_priority_over_openai(self):
        with patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "b"}, clear=True
        ):
            client = LLMClient.from_env()
            assert client.provider == "anthropic"

    def test_assess_returns_none_when_unavailable(self):
        client = LLMClient(provider="none")
        result = client.assess("system prompt", "user context")
        assert result is None

    def test_assess_json_returns_none_when_unavailable(self):
        client = LLMClient(provider="none")
        result = client.assess_json("system prompt", "user context")
        assert result is None

    def test_assess_json_parses_valid_json(self):
        client = LLMClient(provider="none")
        client._chat_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            '{"confidence_adjustment": 0.1, "reasoning": "likely cause"}'
        )
        client._chat_model.invoke.return_value = mock_response

        result = client.assess_json("system", "context")
        assert result is not None
        assert result["confidence_adjustment"] == 0.1
        assert result["reasoning"] == "likely cause"

    def test_assess_json_handles_non_json_response(self):
        client = LLMClient(provider="none")
        client._chat_model = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "This is not JSON"
        client._chat_model.invoke.return_value = mock_response

        result = client.assess_json("system", "context")
        assert result is not None
        assert "reasoning" in result
        assert result["reasoning"] == "This is not JSON"

    def test_assess_handles_invoke_exception(self):
        client = LLMClient(provider="none")
        client._chat_model = MagicMock()
        client._chat_model.invoke.side_effect = RuntimeError("API error")

        result = client.assess("system", "context")
        assert result is None


class TestCheckerWithLLM:
    """Test that Checker integrates LLM reasoning when available."""

    def _make_mcp_mock(self):
        mcp = MagicMock(spec=MCPClient)
        mcp.get_entities.return_value = {
            "entities": [
                {
                    "urn": "urn:li:dataset:(urn:li:dataPlatform:sqlite,test.upstream,PROD)",
                    "aspects": [{"name": "assertionRunEvents"}],
                }
            ]
        }
        mcp.search.return_value = {"entities": []}
        return mcp

    def _make_context(self):
        return {
            "dataset_urn": "urn:li:dataset:(urn:li:dataPlatform:sqlite,test.downstream,PROD)",
            "assertion_urn": "urn:li:assertion:test",
            "error_message": "rows count mismatch",
            "candidates": [
                {
                    "urn": "urn:li:dataset:(urn:li:dataPlatform:sqlite,test.upstream,PROD)",
                    "confidence": 0.5,
                    "reason": "has failed assertions",
                }
            ],
        }

    def test_llm_unavailable_falls_back_to_heuristic(self):
        mcp = self._make_mcp_mock()
        llm = MagicMock(spec=LLMClient)
        llm.is_available.return_value = False

        checker = CheckerAgent(mcp, llm_client=llm)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="checker",
            task="validate",
            context=self._make_context(),
        )
        result = checker.run(msg)

        validated = result.result["validated_candidates"]
        assert len(validated) == 1
        # Heuristic only: 0.5 (base) + 0.3 (failed assertions) = 0.8 -> confirmed
        assert validated[0]["status"] == ValidationStatus.CONFIRMED.value

    def test_llm_available_boosts_confidence(self):
        mcp = self._make_mcp_mock()
        llm = MagicMock(spec=LLMClient)
        llm.is_available.return_value = True
        llm.assess_json.return_value = {
            "confidence_adjustment": 0.15,
            "reasoning": "schema change matches assertion failure pattern",
        }

        checker = CheckerAgent(mcp, llm_client=llm)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="checker",
            task="validate",
            context=self._make_context(),
        )
        result = checker.run(msg)

        validated = result.result["validated_candidates"]
        assert len(validated) == 1
        # 0.5 (base) + 0.3 (heuristic) + 0.15 (LLM) = 0.95
        assert validated[0]["confidence"] == 0.95
        assert "LLM: schema change matches" in validated[0]["reasoning"]

    def test_llm_can_reduce_confidence(self):
        mcp = self._make_mcp_mock()
        llm = MagicMock(spec=LLMClient)
        llm.is_available.return_value = True
        llm.assess_json.return_value = {
            "confidence_adjustment": -0.2,
            "reasoning": "unrelated failure pattern",
        }

        checker = CheckerAgent(mcp, llm_client=llm)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="checker",
            task="validate",
            context=self._make_context(),
        )
        result = checker.run(msg)

        validated = result.result["validated_candidates"]
        # 0.5 + 0.3 - 0.2 = 0.6 -> probable (not confirmed)
        assert validated[0]["status"] == ValidationStatus.PROBABLE.value
        assert validated[0]["confidence"] == 0.6

    def test_llm_failure_does_not_crash_checker(self):
        mcp = self._make_mcp_mock()
        llm = MagicMock(spec=LLMClient)
        llm.is_available.return_value = True
        llm.assess_json.side_effect = RuntimeError("API timeout")

        checker = CheckerAgent(mcp, llm_client=llm)
        msg = AgentMessage(
            from_agent="coordinator",
            to_agent="checker",
            task="validate",
            context=self._make_context(),
        )
        result = checker.run(msg)

        # Should still produce heuristic-only result
        assert result.status.value == "completed"
        validated = result.result["validated_candidates"]
        assert len(validated) == 1
