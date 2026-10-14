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


def test_checkpoint_for_same_step_is_idempotent(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.sqlite3")
    first = store.save("task-1", "index", {"files": 4})
    second = store.save("task-1", "index", {"files": 4})

    assert first.checkpoint_id == second.checkpoint_id
    assert store.count("task-1") == 1
    assert store.has_step("task-1", "index")
