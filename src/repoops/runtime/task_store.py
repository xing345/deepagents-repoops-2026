from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..storage import connect
from .models import TaskRecord, TaskStatus


class InvalidTaskTransition(ValueError):
    """Raised when a task attempts an illegal state transition."""


class TaskConflict(RuntimeError):
    """Raised when an optimistic-lock update loses a race with another writer."""


# A succeeded task can be reopened by a new step: an agent may issue several
# retrievals or commands under one task id.  The status always describes the
# most recent step, so "succeeded" is a resting state, not a tombstone.
_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.FAILED}),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.SUCCEEDED, TaskStatus.FAILED}
    ),
    TaskStatus.PAUSED: frozenset({TaskStatus.PAUSED, TaskStatus.RUNNING, TaskStatus.FAILED}),
    TaskStatus.SUCCEEDED: frozenset({TaskStatus.SUCCEEDED, TaskStatus.RUNNING}),
    TaskStatus.FAILED: frozenset({TaskStatus.FAILED, TaskStatus.RUNNING}),
}


class TaskStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.database_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS tasks ("
                "task_id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL, "
                "version INTEGER NOT NULL, result_json TEXT NOT NULL, created_at REAL NOT NULL, "
                "updated_at REAL NOT NULL)"
            )

    def create(self, task_id: str, goal: str) -> TaskRecord:
        if not task_id.strip() or not goal.strip():
            raise ValueError("task_id and goal must be non-empty")
        now = time.time()
        with connect(self.database_path) as connection:
            try:
                connection.execute(
                    "INSERT INTO tasks "
                    "(task_id, goal, status, version, result_json, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (task_id, goal, TaskStatus.PENDING.value, 0, "{}", now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"task already exists: {task_id}") from exc
        return self.get(task_id)

    def get(self, task_id: str) -> TaskRecord:
        with connect(self.database_path) as connection:
            row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown task: {task_id}")
        return self._record(row)

    def transition(
        self,
        task_id: str,
        target: TaskStatus,
        *,
        result: dict[str, Any] | None = None,
    ) -> TaskRecord:
        """Move a task to ``target`` under an optimistic lock.

        The ``version`` predicate makes the update conditional: if another
        writer changed the row after ``get`` returned, zero rows are affected
        and ``TaskConflict`` is raised instead of silently overwriting.
        """

        current = self.get(task_id)
        if target not in _TRANSITIONS[current.status]:
            raise InvalidTaskTransition(
                f"cannot transition task {task_id} from {current.status} to {target}"
            )
        if target is current.status and result is None:
            return current
        next_result = current.result if result is None else result
        now = time.time()
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = ?, version = ?, result_json = ?, updated_at = ? "
                "WHERE task_id = ? AND version = ?",
                (
                    target.value,
                    current.version + 1,
                    json.dumps(next_result, ensure_ascii=False, sort_keys=True),
                    now,
                    task_id,
                    current.version,
                ),
            )
            if cursor.rowcount != 1:
                raise TaskConflict(
                    f"task {task_id} changed concurrently "
                    f"(expected version {current.version}); reload and retry"
                )
        return self.get(task_id)

    @staticmethod
    def _record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            goal=row["goal"],
            status=TaskStatus(row["status"]),
            version=row["version"],
            result=json.loads(row["result_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )