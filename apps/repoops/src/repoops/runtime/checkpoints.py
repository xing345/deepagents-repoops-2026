from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Checkpoint:
    checkpoint_id: str
    task_id: str
    step: str
    state: dict[str, Any]
    sequence: int
    created_at: float


class CheckpointStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS checkpoints ("
                "checkpoint_id TEXT UNIQUE NOT NULL, task_id TEXT NOT NULL, step TEXT NOT NULL, "
                "state_json TEXT NOT NULL, sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "created_at REAL NOT NULL, UNIQUE(task_id, step))"
            )

    def save(self, task_id: str, step: str, state: dict[str, Any]) -> Checkpoint:
        if not task_id.strip() or not step.strip():
            raise ValueError("task_id and step must be non-empty")
        checkpoint_id = hashlib.sha256(f"{task_id}:{step}".encode()).hexdigest()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO checkpoints "
                "(checkpoint_id, task_id, step, state_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    checkpoint_id,
                    task_id,
                    step,
                    json.dumps(state, ensure_ascii=False, sort_keys=True),
                    time.time(),
                ),
            )
        return self._get_by_id(checkpoint_id)

    def latest(self, task_id: str) -> Checkpoint | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE task_id = ? ORDER BY sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        return None if row is None else self._checkpoint(row)

    def has_step(self, task_id: str, step: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM checkpoints WHERE task_id = ? AND step = ?", (task_id, step)
            ).fetchone()
        return row is not None

    def count(self, task_id: str) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM checkpoints WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
            )

    def _get_by_id(self, checkpoint_id: str) -> Checkpoint:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown checkpoint: {checkpoint_id}")
        return self._checkpoint(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _checkpoint(row: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            task_id=row["task_id"],
            step=row["step"],
            state=json.loads(row["state_json"]),
            sequence=row["sequence"],
            created_at=row["created_at"],
        )
