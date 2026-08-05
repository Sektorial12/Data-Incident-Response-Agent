"""Agent communication protocol — message format for inter-agent communication."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentMessage:
    """Message passed between Coordinator and sub-agents."""

    from_agent: str
    to_agent: str
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    status: AgentStatus = AgentStatus.PENDING
    error: str | None = None

    def mark_in_progress(self) -> None:
        self.status = AgentStatus.IN_PROGRESS

    def mark_completed(self, result: dict[str, Any]) -> None:
        self.result = result
        self.status = AgentStatus.COMPLETED

    def mark_failed(self, error: str) -> None:
        self.error = error
        self.status = AgentStatus.FAILED

    @property
    def is_completed(self) -> bool:
        return self.status == AgentStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == AgentStatus.FAILED
