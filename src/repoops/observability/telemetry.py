from __future__ import annotations

import json
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import EventType, RunEvent


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    event_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    failed_events: int


class JsonlTelemetry:
    def __init__(
        self,
        path: Path,
        *,
        input_cost_per_1k: float = 0.0,
        output_cost_per_1k: float = 0.0,
    ) -> None:
        if input_cost_per_1k < 0 or output_cost_per_1k < 0:
            raise ValueError("token cost rates must be non-negative")
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.input_cost_per_1k = input_cost_per_1k
        self.output_cost_per_1k = output_cost_per_1k
        self._write_lock = threading.Lock()

    @contextmanager
    def span(
        self, run_id: str, task_id: str, event_type: EventType
    ) -> Generator[TelemetrySpan, None, None]:
        span = TelemetrySpan(self, run_id, task_id, event_type)
        try:
            yield span
        except Exception as exc:
            span.finish("failed", {"error_type": type(exc).__name__})
            raise
        else:
            span.finish("succeeded")

    def read_events(self) -> list[RunEvent]:
        if not self.path.exists():
            return []
        events: list[RunEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            events.append(
                RunEvent(
                    run_id=payload["run_id"],
                    task_id=payload["task_id"],
                    event_type=EventType(payload["event_type"]),
                    status=payload["status"],
                    occurred_at=payload["occurred_at"],
                    duration_ms=payload["duration_ms"],
                    input_tokens=payload["input_tokens"],
                    output_tokens=payload["output_tokens"],
                    cost_usd=payload["cost_usd"],
                    attributes=payload["attributes"],
                )
            )
        return events

    def summarize(self, run_id: str) -> RunSummary:
        events = [event for event in self.read_events() if event.run_id == run_id]
        input_tokens = sum(event.input_tokens for event in events)
        output_tokens = sum(event.output_tokens for event in events)
        return RunSummary(
            run_id=run_id,
            event_count=len(events),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=sum(event.cost_usd for event in events),
            failed_events=sum(event.status == "failed" for event in events),
        )

    def _record(self, event: RunEvent) -> None:
        with self._write_lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


class TelemetrySpan:
    def __init__(self, telemetry: JsonlTelemetry, run_id: str, task_id: str, event_type: EventType):
        self.telemetry = telemetry
        self.run_id = run_id
        self.task_id = task_id
        self.event_type = event_type
        self.started_at = time.perf_counter()
        self.input_tokens = 0
        self.output_tokens = 0
        self.attributes: dict[str, Any] = {}
        self._finished = False

    def set_usage(self, *, input_tokens: int, output_tokens: int) -> None:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def finish(self, status: str, attributes: dict[str, Any] | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        merged_attributes = {**self.attributes, **(attributes or {})}
        cost_usd = (
            self.input_tokens / 1000 * self.telemetry.input_cost_per_1k
            + self.output_tokens / 1000 * self.telemetry.output_cost_per_1k
        )
        self.telemetry._record(
            RunEvent(
                run_id=self.run_id,
                task_id=self.task_id,
                event_type=self.event_type,
                status=status,
                occurred_at=time.time(),
                duration_ms=(time.perf_counter() - self.started_at) * 1000,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                cost_usd=cost_usd,
                attributes=merged_attributes,
            )
        )
