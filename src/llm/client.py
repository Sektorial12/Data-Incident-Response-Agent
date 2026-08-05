"""LLM client — model-agnostic reasoning layer for agents.

Supports Anthropic Claude and OpenAI via LangChain. Falls back to
heuristic-only mode (returns None) when no API key is configured.

Usage:
    llm = LLMClient.from_env()
    if llm.is_available():
        reasoning = llm.assess(prompt, context)
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMClient:
    """Model-agnostic LLM wrapper using LangChain chat models.

    Detects available provider from environment variables:
    - ANTHROPIC_API_KEY  -> ChatAnthropic (Claude)
    - OPENAI_API_KEY     -> ChatOpenAI (GPT-4, etc.)

    If neither is set, is_available() returns False and agents
    fall back to heuristic-only mode.
    """

    def __init__(
        self,
        provider: str = "anthropic",
        model: str | None = None,
        temperature: float = 0.1,
    ) -> None:
        self.provider = provider
        self.model = model or self._default_model(provider)
        self.temperature = temperature
        self._chat_model = None
        self._init_chat_model()

    def _default_model(self, provider: str) -> str:
        if provider == "anthropic":
            return "claude-3-5-sonnet-20241022"
        if provider == "openai":
            return "gpt-4o"
        return "unknown"

    def _init_chat_model(self) -> None:
        try:
            if self.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic

                self._chat_model = ChatAnthropic(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=4096,
                )
                logger.info(
                    "LLMClient initialized — provider: anthropic, model: %s", self.model
                )

            elif self.provider == "openai":
                from langchain_openai import ChatOpenAI

                self._chat_model = ChatOpenAI(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=4096,
                )
                logger.info(
                    "LLMClient initialized — provider: openai, model: %s", self.model
                )

            else:
                logger.warning("Unknown LLM provider: %s", self.provider)
        except ImportError as e:
            logger.warning("LLM provider %s not available: %s", self.provider, e)
        except Exception as e:
            logger.warning("Failed to initialize LLM (%s): %s", self.provider, e)

    def is_available(self) -> bool:
        return self._chat_model is not None

    def assess(self, system_prompt: str, user_context: str) -> str | None:
        """Send a prompt to the LLM and return the text response.

        Args:
            system_prompt: Instructions defining the LLM's role and task.
            user_context: Structured context (e.g., JSON string of incident data).

        Returns:
            LLM response text, or None if LLM is unavailable or call fails.
        """
        if not self.is_available():
            logger.debug("LLM not available — skipping assessment")
            return None

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_context),
            ]
            response = self._chat_model.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error("LLM assessment failed: %s", e)
            return None

    def assess_json(
        self, system_prompt: str, user_context: str
    ) -> dict[str, Any] | None:
        """Like assess() but parses the response as JSON.

        Returns None if the LLM is unavailable, the call fails, or the
        response is not valid JSON.
        """
        text = self.assess(system_prompt, user_context)
        if text is None:
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "LLM response was not valid JSON, returning raw text in 'reasoning'"
            )
            return {"reasoning": text}

    @classmethod
    def from_env(
        cls, model: str | None = None, temperature: float = 0.1
    ) -> "LLMClient":
        """Create an LLMClient from environment variables.

        Priority:
        1. ANTHROPIC_API_KEY  -> Anthropic
        2. OPENAI_API_KEY     -> OpenAI
        3. Neither            -> unavailable (is_available() returns False)
        """
        if os.getenv("ANTHROPIC_API_KEY"):
            return cls(provider="anthropic", model=model, temperature=temperature)
        if os.getenv("OPENAI_API_KEY"):
            return cls(provider="openai", model=model, temperature=temperature)
        logger.info("No LLM API key found — agents will use heuristic-only mode")
        return cls(provider="none")
