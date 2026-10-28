import json
from pathlib import Path

from repoops.evaluation.runner import RetrievalEvaluator, load_cases
from repoops.retrieval.index import HybridIndex


def test_evaluator_computes_recall_mrr_latency_and_failures(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "case_id": "readme",
                "query": "safe command runner",
                "expected_paths": ["README.md"],
                "k": 3,
            }
        )
        + "\n"
        + json.dumps(
            {
                "case_id": "missing",
                "query": "does not exist",
                "expected_paths": ["missing.py"],
                "k": 3,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    index = HybridIndex(tmp_path / "index.sqlite3")
    index.rebuild(sample_repository)

    report = RetrievalEvaluator(index).evaluate(load_cases(dataset))

    assert report.total_cases == 2
    assert report.recall_at_k == 0.5
    assert report.mrr == 0.5
    assert report.failed_cases == ("missing",)
    assert report.average_latency_ms >= 0
    serialized = json.loads(report.to_json())
    assert serialized["metrics"]["recall_at_k"] == 0.5


def test_dataset_loader_reads_multiple_cases(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"case_id":"one","query":"a","expected_paths":["a.py"]}\n'
        '{"case_id":"two","query":"b","expected_paths":["b.py"],"k":1}\n',
        encoding="utf-8",
    )

    cases = load_cases(dataset)

    assert [case.case_id for case in cases] == ["one", "two"]
    assert cases[0].k == 5
    assert cases[1].k == 1
