from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    query: str
    expected_paths: tuple[str, ...]
    k: int = 5

    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.query.strip():
            raise ValueError("case_id and query must be non-empty")
        if not self.expected_paths:
            raise ValueError("expected_paths must not be empty")
        if self.k < 1:
            raise ValueError("k must be positive")


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    total_cases: int
    recall_at_k: float
    mrr: float
    average_latency_ms: float
    failed_cases: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "metrics": {
                    "total_cases": self.total_cases,
                    "recall_at_k": self.recall_at_k,
                    "mrr": self.mrr,
                    "average_latency_ms": self.average_latency_ms,
                    "failed_cases": list(self.failed_cases),
                }
            },
            ensure_ascii=False,
            sort_keys=True,
        )
