import sqlite3
from pathlib import Path

from repoops.runtime.checkpoints import CheckpointStore


def test_checkpoint_store_recovers_latest_state_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite3"
    store = CheckpointStore(database)
    store.save("task-1", "index", {"files": 4})
    store.save("task-1", "retrieve", {"query": "auth", "hits": 3})

    recovered = CheckpointStore(database).latest("task-1")

    assert recovered is not None
    assert recovered.step == "retrieve"
    assert recovered.state == {"query": "auth", "hits": 3}


def test_checkpoint_for_same_step_and_input_is_idempotent(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.sqlite3")
    first = store.save("task-1", "index", {"files": 4})
    second = store.save("task-1", "index", {"files": 4})

    assert first.checkpoint_id == second.checkpoint_id
    assert store.count("task-1") == 1
    assert store.has_step("task-1", "index")


def test_different_inputs_get_separate_checkpoints(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.sqlite3")
    store.save("task-1", "retrieval", {"query": "alpha"}, input_key="alpha")
    store.save("task-1", "retrieval", {"query": "beta"}, input_key="beta")

    assert store.count("task-1") == 2
    assert store.find("task-1", "retrieval", "alpha").state == {"query": "alpha"}
    assert store.find("task-1", "retrieval", "beta").state == {"query": "beta"}
    assert store.latest("task-1").input_key == "beta"


def test_replace_updates_state_in_place(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.sqlite3")
    first = store.save("task-1", "command", {"returncode": 0}, input_key="pytest")
    second = store.save(
        "task-1", "command", {"returncode": 1}, input_key="pytest", replace=True
    )

    assert first.checkpoint_id == second.checkpoint_id
    assert store.find("task-1", "command", "pytest").state == {"returncode": 1}
    assert store.count("task-1") == 1


def test_legacy_checkpoint_table_is_migrated(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE checkpoints ("
        "checkpoint_id TEXT UNIQUE NOT NULL, task_id TEXT NOT NULL, step TEXT NOT NULL, "
        "state_json TEXT NOT NULL, sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at REAL NOT NULL, UNIQUE(task_id, step))"
    )
    connection.execute(
        "INSERT INTO checkpoints (checkpoint_id, task_id, step, state_json, created_at) "
        "VALUES ('legacy', 'task-1', 'index', '{\"files\": 4}', 1.0)"
    )
    connection.commit()
    connection.close()

    store = CheckpointStore(database)

    assert store.count("task-1") == 1
    migrated = store.find("task-1", "index", "")
    assert migrated is not None
    assert migrated.state == {"files": 4}