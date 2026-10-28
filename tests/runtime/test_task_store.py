import sqlite3
from pathlib import Path

import pytest

from repoops.runtime.models import TaskStatus
from repoops.runtime.task_store import InvalidTaskTransition, TaskConflict, TaskStore


def test_task_store_persists_and_validates_state_transitions(tmp_path: Path) -> None:
    database = tmp_path / "tasks.sqlite3"
    store = TaskStore(database)

    created = store.create("task-1", "find the authentication flow")
    assert created.status is TaskStatus.PENDING

    running = store.transition("task-1", TaskStatus.RUNNING)
    assert running.status is TaskStatus.RUNNING
    completed = store.transition("task-1", TaskStatus.SUCCEEDED, result={"files": 2})
    assert completed.status is TaskStatus.SUCCEEDED
    assert completed.result == {"files": 2}

    reopened = TaskStore(database).get("task-1")
    assert reopened.status is TaskStatus.SUCCEEDED
    assert reopened.version == 2

    with pytest.raises(InvalidTaskTransition):
        store.transition("task-1", TaskStatus.PENDING)

    restarted = store.transition("task-1", TaskStatus.RUNNING)
    assert restarted.status is TaskStatus.RUNNING
    assert restarted.version == 3


def test_pending_task_cannot_jump_to_succeeded(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.create("task-2", "inspect repository")

    with pytest.raises(InvalidTaskTransition):
        store.transition("task-2", TaskStatus.SUCCEEDED)


def test_repeated_pause_is_idempotent(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite3")
    store.create("task-2", "inspect repository")
    store.transition("task-2", TaskStatus.RUNNING)

    first = store.transition("task-2", TaskStatus.PAUSED)
    second = store.transition("task-2", TaskStatus.PAUSED)

    assert first.version == second.version
    assert second.status is TaskStatus.PAUSED


def test_transition_reports_optimistic_lock_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "tasks.sqlite3"
    store = TaskStore(database)
    store.create("task-3", "inspect repository")
    stale = store.get("task-3")

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE tasks SET version = version + 1 WHERE task_id = 'task-3'")

    monkeypatch.setattr(store, "get", lambda task_id: stale)

    with pytest.raises(TaskConflict):
        store.transition("task-3", TaskStatus.RUNNING)