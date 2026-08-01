from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IncidentEvent:
    """Structured event representing an assertion failure in DataHub."""

    assertion_urn: str
    dataset_urn: str
    assertion_type: str
    result_status: str
    timestamp_ms: int
    assertion_name: Optional[str] = None
    dataset_name: Optional[str] = None
    platform: Optional[str] = None
    run_id: Optional[str] = None
    error_message: Optional[str] = None
    raw_event: dict = field(default_factory=dict, repr=False)

    @property
    def is_failure(self) -> bool:
        return self.result_status.upper() in ("FAILED", "ERROR")

    def summary(self) -> str:
        return (
            f"IncidentEvent(assertion={self.assertion_name or self.assertion_urn}, "
            f"dataset={self.dataset_name or self.dataset_urn}, "
            f"status={self.result_status}, type={self.assertion_type})"
        )
