from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from repoops.retrieval.index import HybridIndex

from .models import EvaluationCase, EvaluationReport


def load_cases(path: Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
            cases.append(
                EvaluationCase(
                    case_id=payload["case_id"],
                    query=payload["query"],
                    expected_paths=tuple(payload["expected_paths"]),
                    k=payload.get("k", 5),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid evaluation case at line {line_number}") from exc
    return cases


class RetrievalEvaluator:
    def __init__(self, index: HybridIndex) -> None:
        self.index = index

    def evaluate(self, cases: Iterable[EvaluationCase]) -> EvaluationReport:
        case_list = list(cases)
        if not case_list:
            return EvaluationReport(0, 0.0, 0.0, 0.0, ())
        recall_total = 0.0
        reciprocal_rank_total = 0.0
        latencies: list[float] = []
        failed_cases: list[str] = []
        for case in case_list:
            started = time.perf_counter()
            hits = self.index.search(case.query, limit=case.k)
            latencies.append((time.perf_counter() - started) * 1000)
            expected = set(case.expected_paths)
            ranked_paths = [hit.path for hit in hits]
            matched = expected.intersection(ranked_paths)
            recall_total += len(matched) / len(expected)
            if not matched:
                failed_cases.append(case.case_id)
            for rank, path in enumerate(ranked_paths, 1):
                if path in expected:
                    reciprocal_rank_total += 1.0 / rank
                    break
        return EvaluationReport(
            total_cases=len(case_list),
            recall_at_k=recall_total / len(case_list),
            mrr=reciprocal_rank_total / len(case_list),
            average_latency_ms=sum(latencies) / len(latencies),
            failed_cases=tuple(failed_cases),
        )
