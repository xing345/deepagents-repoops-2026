import json
import sys
from pathlib import Path

import pytest

from repoops.application import RepoOpsApplication
from repoops.runtime.models import TaskStatus
from repoops.security.policy import ExecutionPolicy


def _policy(root: Path) -> ExecutionPolicy:
    return ExecutionPolicy(
        workspace_root=root,
        allowed_executables=frozenset({Path(sys.executable).name}),
    )


def _app(root: Path, state_dir: Path) -> RepoOpsApplication:
    return RepoOpsApplication(root, state_dir, policy=_policy(root))


def test_application_runs_retrieval_task_and_recovers_state(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    app = _app(sample_repository, state_dir)
    app.rebuild_index()
    app.create_task("task-1", "find the safe command runner")

    hits = app.run_retrieval_task("task-1", "safe command runner")

    assert hits[0].path == "README.md"
    assert app.tasks.get("task-1").status is TaskStatus.SUCCEEDED
    assert app.checkpoints.latest("task-1").step == "retrieval"
    assert app.telemetry.summarize("task-1").event_count == 1

    recovered_app = _app(sample_repository, state_dir)
    recovered_hits = recovered_app.run_retrieval_task("task-1", "safe command runner")
    assert recovered_hits[0].path == "README.md"
    assert recovered_app.checkpoints.count("task-1") == 1
    assert recovered_app.telemetry.summarize("task-1").event_count == 1


def test_second_query_gets_its_own_checkpoint(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    app = _app(sample_repository, tmp_path / "state")
    app.rebuild_index()
    app.create_task("task-2", "two different searches")

    first = app.run_retrieval_task("task-2", "safe command runner")
    second = app.run_retrieval_task("task-2", "search_code")

    assert first[0].path == "README.md"
    assert second[0].path == "src/search.py"
    assert app.tasks.get("task-2").result["query"] == "search_code"
    assert app.checkpoints.count("task-2") == 2
    assert app.checkpoints.find("task-2", "retrieval", "safe command runner") is not None

    cached = app.run_retrieval_task("task-2", "safe command runner")

    assert cached[0].path == "README.md"
    assert app.checkpoints.count("task-2") == 2


def test_application_routes_commands_through_policy_executor(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    app = _app(sample_repository, tmp_path / "state")
    app.create_task("task-3", "run a safe check")

    result = app.run_command("task-3", [sys.executable, "-c", "print('ok')"])

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    assert app.tasks.get("task-3").status is TaskStatus.SUCCEEDED


def test_commands_are_replayed_instead_of_cached(
    sample_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(sample_repository, tmp_path / "state")
    app.create_task("task-4", "run the same check twice")
    calls: list[list[str]] = []
    original = app.executor.run

    def counting_run(
        command: list[str],
        *,
        cwd: Path | None = None,
        env: object | None = None,
    ) -> object:
        calls.append(list(command))
        return original(command, cwd=cwd)

    monkeypatch.setattr(app.executor, "run", counting_run)
    command = [sys.executable, "-c", "print('ok')"]

    app.run_command("task-4", command)
    app.run_command("task-4", command)

    assert len(calls) == 2
    assert app.checkpoints.count("task-4") == 1
    key = json.dumps(command, ensure_ascii=False)
    assert app.checkpoints.find("task-4", "command", key) is not None