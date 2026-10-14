from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .observability.events import EventType
from .observability.telemetry import JsonlTelemetry
from .retrieval.index import HybridIndex
from .retrieval.models import SearchHit
from .runtime.checkpoints import CheckpointStore
from .runtime.models import TaskRecord, TaskStatus
from .runtime.task_store import TaskStore
from .security.executor import ExecutionResult, SafeExecutor
from .security.policy import ExecutionPolicy


class RepoOpsApplication:
    """Offline-first orchestration boundary for the RepoOps Agent."""

    def __init__(
        self,
        repository_root: Path,
        state_dir: Path,
        *,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.index = HybridIndex(self.state_dir / "index.sqlite3")
        self.tasks = TaskStore(self.state_dir / "tasks.sqlite3")
        self.checkpoints = CheckpointStore(self.state_dir / "checkpoints.sqlite3")
        self.telemetry = JsonlTelemetry(self.state_dir / "events.jsonl")
        self.executor = SafeExecutor(policy or ExecutionPolicy(self.repository_root))

    def rebuild_index(self) -> int:
        self.index.rebuild(self.repository_root)
        return self.index.chunk_count()

    def create_task(self, task_id: str, goal: str) -> TaskRecord:
        return self.tasks.create(task_id, goal)

    def run_retrieval_task(self, task_id: str, query: str) -> list[SearchHit]:
        existing = self.checkpoints.latest(task_id)
        if (
            existing is not None
            and existing.step == "retrieval"
            and existing.state.get("query") == query
        ):
            return [SearchHit(**payload) for payload in existing.state["hits"]]
        self._ensure_running(task_id)
        try:
            with self.telemetry.span(task_id, task_id, EventType.RETRIEVAL) as span:
                hits = self.index.search(query)
                span.set_attribute("query", query)
                span.set_attribute("hit_count", len(hits))
                self.checkpoints.save(
                    task_id,
                    "retrieval",
                    {"query": query, "hits": [asdict(hit) for hit in hits]},
                )
            self.tasks.transition(
                task_id,
                TaskStatus.SUCCEEDED,
                result={"query": query, "hit_count": len(hits)},
            )
            return hits
        except Exception:
            self.tasks.transition(task_id, TaskStatus.FAILED)
            raise

    def run_command(self, task_id: str, command: Sequence[str]) -> ExecutionResult:
        self._ensure_running(task_id)
        try:
            with self.telemetry.span(task_id, task_id, EventType.TOOL) as span:
                result = self.executor.run(command, cwd=self.repository_root)
                span.set_attribute("returncode", result.returncode)
                span.set_attribute("timed_out", result.timed_out)
            self.checkpoints.save(
                task_id,
                "command",
                {
                    "command": list(command),
                    "returncode": result.returncode,
                    "timed_out": result.timed_out,
                },
            )
            if result.returncode == 0 and not result.timed_out:
                self.tasks.transition(task_id, TaskStatus.SUCCEEDED)
            else:
                self.tasks.transition(task_id, TaskStatus.FAILED)
            return result
        except Exception:
            self.tasks.transition(task_id, TaskStatus.FAILED)
            raise

    def _ensure_running(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task.status in {TaskStatus.PENDING, TaskStatus.PAUSED, TaskStatus.FAILED}:
            self.tasks.transition(task_id, TaskStatus.RUNNING)
