import json
from pathlib import Path

from repoops.evaluation.cli import main


def test_cli_writes_report_and_passes_threshold(
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
        + "\n",
        encoding="utf-8",
    )
    report = tmp_path / "report.json"

    exit_code = main(
        [
            "--dataset",
            str(dataset),
            "--corpus",
            str(sample_repository),
            "--report",
            str(report),
            "--min-recall",
            "1.0",
        ]
    )

    assert exit_code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["chunks"] > 0
    assert payload["metrics"]["recall_at_k"] == 1.0


def test_cli_fails_when_recall_is_below_threshold(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "case_id": "missing",
                "query": "nothing matches this",
                "expected_paths": ["missing.py"],
                "k": 3,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--dataset",
            str(dataset),
            "--corpus",
            str(sample_repository),
            "--report",
            str(tmp_path / "report.json"),
            "--min-recall",
            "0.9",
        ]
    )

    assert exit_code == 1