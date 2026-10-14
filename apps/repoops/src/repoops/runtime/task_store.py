from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .models import TaskRecord, TaskStatus


class InvalidTaskTransition(ValueError):
    """Raised when a task attempts an illegal state transition."""


_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.FAILED}),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.SUCCEEDED, TaskStatus.FAILED}
    ),
    TaskStatus.PAUSED: frozenset({TaskStatus.PAUSED, TaskStatus.RUNNING, TaskStatus.FAILED}),
    TaskStatus.SUCCEEDED: frozenset({TaskStatus.SUCCEEDED}),
    TaskStatus.FAILED: frozenset({TaskStatus.FAILED, TaskStatus.RUNNING}),
}


class TaskStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        current = self.get(task_id)
        if target not in _TRANSITIONS[current.status]:
            raise InvalidTaskTransition(
                f"cannot transition task {task_id} from {current.status} to {target}"
            )
        if target is current.status:
            return current
        now = time.time()
        next_result = current.result if result is None else result
        with self._connect() as connection:
            connection.execute(
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
        return self.get(task_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

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
