"""Base agent class for the Data Incident Response Agent system."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from src.agents.protocol import AgentMessage
from src.mcp_client.client import MCPClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all agents in the incident response system."""

    name: str = "base"
    system_prompt: str = ""

    def __init__(
        self, mcp_client: MCPClient, config: dict[str, Any] | None = None
    ) -> None:
        self.mcp = mcp_client
        self.config = config or {}
        self.logger = logging.getLogger(f"agent.{self.name}")

    @abstractmethod
    def run(self, message: AgentMessage) -> AgentMessage:
        """Execute the agent's task and return the updated message."""
        ...

    def _log_start(self, message: AgentMessage) -> None:
        self.logger.info(
            "Starting task: %s (from %s)", message.task, message.from_agent
        )

    def _log_complete(self, message: AgentMessage) -> None:
        self.logger.info("Task completed: %s", message.task)

    def _log_failure(self, message: AgentMessage, error: str) -> None:
        self.logger.error("Task failed: %s — %s", message.task, error)
