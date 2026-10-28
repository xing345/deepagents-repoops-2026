from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..storage import connect

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS checkpoints ("
    "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
    "checkpoint_id TEXT UNIQUE NOT NULL, "
    "task_id TEXT NOT NULL, "
    "step TEXT NOT NULL, "
    "input_key TEXT NOT NULL DEFAULT '', "
    "state_json TEXT NOT NULL, "
    "created_at REAL NOT NULL, "
    "UNIQUE(task_id, step, input_key))"
)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    checkpoint_id: str
    task_id: str
    step: str
    input_key: str
    state: dict[str, Any]
    sequence: int
    created_at: float


class CheckpointStore:
    """Step-level checkpoints keyed by ``(task_id, step, input_key)``.

    Keying on the input is what makes resume correct: a second retrieval with
    a different query must create a new checkpoint instead of being dropped by
    a ``UNIQUE(task_id, step)`` constraint.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.database_path) as connection:
            connection.execute(_SCHEMA)
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(checkpoints)")
            }
            if "input_key" not in columns:
                self._migrate_from_v1(connection)

    @staticmethod
    def _migrate_from_v1(connection: sqlite3.Connection) -> None:
        """Rebuild the pre-0.2 table whose unique key was ``(task_id, step)``.

        Old rows carry no input key, so they are preserved under ``''``.  This
        keeps resumable state from earlier runs instead of silently dropping it.
        """

        connection.execute("ALTER TABLE checkpoints RENAME TO checkpoints_legacy")
        connection.execute(_SCHEMA)
        connection.execute(
            "INSERT INTO checkpoints "
            "(checkpoint_id, task_id, step, input_key, state_json, created_at) "
            "SELECT checkpoint_id, task_id, step, '', state_json, created_at "
            "FROM checkpoints_legacy"
        )
        connection.execute("DROP TABLE checkpoints_legacy")

    def save(
        self,
        task_id: str,
        step: str,
        state: dict[str, Any],
        *,
        input_key: str = "",
        replace: bool = False,
    ) -> Checkpoint:
        """Persist a checkpoint.

        ``replace=False`` keeps the first write for a given input key, which is
        what read-only steps want (same input, same cached result).
        ``replace=True`` upserts the state, which is what audit steps want when
        the same command is executed again.
        """

        if not task_id.strip() or not step.strip():
            raise ValueError("task_id and step must be non-empty")
        checkpoint_id = hashlib.sha256(f"{task_id}:{step}:{input_key}".encode()).hexdigest()
        verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        with connect(self.database_path) as connection:
            connection.execute(
                f"{verb} INTO checkpoints "
                "(checkpoint_id, task_id, step, input_key, state_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    checkpoint_id,
                    task_id,
                    step,
                    input_key,
                    json.dumps(state, ensure_ascii=False, sort_keys=True),
                    time.time(),
                ),
            )
        return self._get_by_id(checkpoint_id)

    def find(self, task_id: str, step: str, input_key: str = "") -> Checkpoint | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE task_id = ? AND step = ? AND input_key = ?",
                (task_id, step, input_key),
            ).fetchone()
        return None if row is None else self._checkpoint(row)

    def latest(self, task_id: str) -> Checkpoint | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE task_id = ? ORDER BY sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        return None if row is None else self._checkpoint(row)

    def has_step(self, task_id: str, step: str) -> bool:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM checkpoints WHERE task_id = ? AND step = ?", (task_id, step)
            ).fetchone()
        return row is not None

    def count(self, task_id: str) -> int:
        with connect(self.database_path) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM checkpoints WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
            )

    def _get_by_id(self, checkpoint_id: str) -> Checkpoint:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown checkpoint: {checkpoint_id}")
        return self._checkpoint(row)

    @staticmethod
    def _checkpoint(row: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            task_id=row["task_id"],
            step=row["step"],
            input_key=row["input_key"],
            state=json.loads(row["state_json"]),
            sequence=row["sequence"],
            created_at=row["created_at"],
        )