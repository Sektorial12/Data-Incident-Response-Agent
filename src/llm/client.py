"""LLM client — model-agnostic reasoning layer for agents.

Supports Anthropic Claude, OpenAI GPT, and Google Gemini via LangChain.
Falls back to heuristic-only mode (returns None) when no API key is configured.

Usage:
    llm = LLMClient.from_env()
    if llm.is_available():
        reasoning = llm.assess(prompt, context)
"""

import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Retryable error indicators (quota, rate limit, server overload)
_RETRYABLE_MARKERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "rate_limit",
    "rate limit",
    "quota",
    "overloaded",
    "503",
    "502",
    "temporarily unavailable",
)
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BASE_DELAY = 2.0


class LLMClient:
    """Model-agnostic LLM wrapper using LangChain chat models.

    Detects available provider from environment variables:
    - ANTHROPIC_API_KEY  -> ChatAnthropic (Claude)
    - OPENAI_API_KEY     -> ChatOpenAI (GPT-4, etc.)
    - GOOGLE_API_KEY     -> ChatGoogleGenerativeAI (Gemini)

    If none is set, is_available() returns False and agents
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
        if provider == "google":
            return "gemini-flash-lite-latest"
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

            elif self.provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI

                self._chat_model = ChatGoogleGenerativeAI(
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=4096,
                )
                logger.info(
                    "LLMClient initialized — provider: google, model: %s", self.model
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

        Retries on quota/rate-limit errors with exponential backoff.

        Args:
            system_prompt: Instructions defining the LLM's role and task.
            user_context: Structured context (e.g., JSON string of incident data).

        Returns:
            LLM response text, or None if LLM is unavailable or call fails.
        """
        if not self.is_available():
            logger.debug("LLM not available — skipping assessment")
            return None

        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_context),
        ]

        for attempt in range(_LLM_MAX_RETRIES + 1):
            try:
                response = self._chat_model.invoke(messages)
                content = response.content if hasattr(response, "content") else str(response)
                # Google Gemini returns content as a list of part dicts: [{'type': 'text', 'text': '...'}]
                if isinstance(content, list):
                    parts = []
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            parts.append(part["text"])
                        elif isinstance(part, str):
                            parts.append(part)
                    return "".join(parts)
                return str(content)
            except Exception as e:
                err_str = str(e)
                if attempt < _LLM_MAX_RETRIES and self._is_retryable(err_str):
                    delay = _LLM_RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "LLM rate-limited (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1,
                        _LLM_MAX_RETRIES + 1,
                        err_str[:120],
                        delay,
                    )
                    time.sleep(delay)
                    continue
                logger.error("LLM assessment failed: %s", err_str[:200])
                return None
        return None

    @staticmethod
    def _is_retryable(error_msg: str) -> bool:
        """Check if an error message indicates a retryable condition."""
        msg_lower = error_msg.lower()
        return any(marker.lower() in msg_lower for marker in _RETRYABLE_MARKERS)

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
        # Strip markdown code fences (Gemini often wraps JSON in ```json ... ```)
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            stripped = "\n".join(lines)
        try:
            return json.loads(stripped)
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
        3. GOOGLE_API_KEY     -> Google (Gemini)
        4. None               -> unavailable (is_available() returns False)
        """
        if os.getenv("ANTHROPIC_API_KEY"):
            return cls(provider="anthropic", model=model, temperature=temperature)
        if os.getenv("OPENAI_API_KEY"):
            return cls(provider="openai", model=model, temperature=temperature)
        if os.getenv("GOOGLE_API_KEY"):
            return cls(provider="google", model=model, temperature=temperature)
        logger.info("No LLM API key found — agents will use heuristic-only mode")
        return cls(provider="none")
