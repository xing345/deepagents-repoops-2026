from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from repoops.evaluation.runner import RetrievalEvaluator, load_cases
from repoops.retrieval.index import HybridIndex

DEFAULT_DATASET = Path("evaluation/datasets/repoops_self.jsonl")
DEFAULT_REPORT = Path("reports/retrieval-eval.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repoops-eval",
        description="Run the offline retrieval regression suite over a local corpus.",
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--corpus", type=Path, default=Path("src"))
    parser.add_argument("--min-recall", type=float, default=0.9)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dataset.is_file():
        print(f"dataset not found: {args.dataset}", file=sys.stderr)
        return 2
    if not args.corpus.is_dir():
        print(f"corpus not found: {args.corpus}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="repoops-eval-") as workspace:
        index = HybridIndex(Path(workspace) / "index.sqlite3")
        index.rebuild(args.corpus)
        chunks = index.chunk_count()
        report = RetrievalEvaluator(index).evaluate(load_cases(args.dataset))

    payload = json.loads(report.to_json())
    payload["corpus"] = args.corpus.as_posix()
    payload["chunks"] = chunks
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    metrics = payload["metrics"]
    print(
        f"cases={metrics['total_cases']} chunks={chunks} "
        f"recall@k={metrics['recall_at_k']:.3f} mrr={metrics['mrr']:.3f} "
        f"latency={metrics['average_latency_ms']:.2f}ms"
    )
    if metrics["failed_cases"]:
        print(f"failed: {', '.join(metrics['failed_cases'])}")
    print(f"report={args.report}")

    if metrics["recall_at_k"] < args.min_recall:
        print(
            f"recall {metrics['recall_at_k']:.3f} is below the required {args.min_recall:.3f}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())