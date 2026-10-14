from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    TASK = "task"
    RETRIEVAL = "retrieval"
    TOOL = "tool"
    MODEL = "model"


@dataclass(frozen=True, slots=True)
class RunEvent:
    run_id: str
    task_id: str
    event_type: EventType
    status: str
    occurred_at: float
    duration_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "event_type": self.event_type.value,
            "status": self.status,
            "occurred_at": self.occurred_at,
            "duration_ms": self.duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "attributes": self.attributes,
        }
