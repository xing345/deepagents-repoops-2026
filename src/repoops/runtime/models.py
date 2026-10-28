from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    goal: str
    status: TaskStatus
    version: int
    result: dict[str, Any]
    created_at: float
    updated_at: float
