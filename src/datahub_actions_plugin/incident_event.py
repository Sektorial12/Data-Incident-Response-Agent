from dataclasses import dataclass, field


@dataclass
class IncidentEvent:
    """Structured event representing an assertion failure in DataHub."""

    assertion_urn: str
    dataset_urn: str
    assertion_type: str
    result_status: str
    timestamp_ms: int
    assertion_name: str | None = None
    dataset_name: str | None = None
    platform: str | None = None
    run_id: str | None = None
    error_message: str | None = None
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
