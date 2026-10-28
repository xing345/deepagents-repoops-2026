import json
from pathlib import Path

import pytest

from repoops.observability.events import EventType
from repoops.observability.telemetry import JsonlTelemetry


def test_span_writes_structured_event_and_aggregates_usage(tmp_path: Path) -> None:
    telemetry = JsonlTelemetry(
        tmp_path / "runs.jsonl",
        input_cost_per_1k=0.01,
        output_cost_per_1k=0.02,
    )

    with telemetry.span("run-1", "task-1", EventType.RETRIEVAL) as span:
        span.set_usage(input_tokens=100, output_tokens=50)
        span.set_attribute("query", "authentication")

    events = telemetry.read_events()
    summary = telemetry.summarize("run-1")
    assert len(events) == 1
    assert events[0].event_type is EventType.RETRIEVAL
    assert events[0].duration_ms >= 0
    assert events[0].attributes["query"] == "authentication"
    assert summary.total_tokens == 150
    assert summary.cost_usd == pytest.approx(0.002)

    raw = json.loads((tmp_path / "runs.jsonl").read_text(encoding="utf-8"))
    assert raw["run_id"] == "run-1"
    assert raw["task_id"] == "task-1"


def test_span_records_failure_without_swallowing_exception(tmp_path: Path) -> None:
    telemetry = JsonlTelemetry(tmp_path / "runs.jsonl")

    with pytest.raises(RuntimeError, match="boom"):
        with telemetry.span("run-2", "task-2", EventType.TOOL):
            raise RuntimeError("boom")

    event = telemetry.read_events()[0]
    assert event.status == "failed"
    assert event.attributes["error_type"] == "RuntimeError"
