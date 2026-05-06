# models — internal data structures for idempotency
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class StoredResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def age(self) -> float:
        return (datetime.now(timezone.utc) - self.created_at).total_seconds()
