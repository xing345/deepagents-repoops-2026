from __future__ import annotations

import json
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
        """Search the index, reusing the cached result for an identical query.

        Retrieval is read-only, so a checkpoint with the same input key is a
        safe cache: replaying a task never re-runs the search.  Different
        queries create different checkpoints, which the pre-0.2 schema could
        not represent.
        """

        cached = self.checkpoints.find(task_id, "retrieval", query)
        if cached is not None:
            hits = [SearchHit(**payload) for payload in cached.state["hits"]]
            self._ensure_running(task_id)
            self._mark_succeeded(
                task_id, {"query": query, "hit_count": len(hits), "cached": True}
            )
            return hits

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
                    input_key=query,
                )
            self._mark_succeeded(task_id, {"query": query, "hit_count": len(hits)})
            return hits
        except Exception:
            self._mark_failed(task_id)
            raise

    def run_command(self, task_id: str, command: Sequence[str]) -> ExecutionResult:
        """Execute a command through the policy-controlled executor.

        Commands are deliberately *not* cached: they can have side effects, so
        replaying a task must re-run them.  The checkpoint records the latest
        result under the command itself, purely for audit and traceability.
        """

        self._ensure_running(task_id)
        command_list = [str(argument) for argument in command]
        try:
            with self.telemetry.span(task_id, task_id, EventType.TOOL) as span:
                result = self.executor.run(command_list, cwd=self.repository_root)
                span.set_attribute("returncode", result.returncode)
                span.set_attribute("timed_out", result.timed_out)
            self.checkpoints.save(
                task_id,
                "command",
                {"command": command_list, "result": asdict(result)},
                input_key=json.dumps(command_list, ensure_ascii=False),
                replace=True,
            )
            if result.returncode == 0 and not result.timed_out:
                self._mark_succeeded(task_id, {"command": command_list, "returncode": 0})
            else:
                self._mark_failed(
                    task_id, {"command": command_list, "returncode": result.returncode}
                )
            return result
        except Exception:
            self._mark_failed(task_id)
            raise

    def _ensure_running(self, task_id: str) -> None:
        task = self.tasks.get(task_id)
        if task.status is not TaskStatus.RUNNING:
            self.tasks.transition(task_id, TaskStatus.RUNNING)

    def _mark_succeeded(self, task_id: str, result: dict[str, object]) -> None:
        self.tasks.transition(task_id, TaskStatus.SUCCEEDED, result=result)

    def _mark_failed(self, task_id: str, result: dict[str, object] | None = None) -> None:
        self.tasks.transition(task_id, TaskStatus.FAILED, result=result)