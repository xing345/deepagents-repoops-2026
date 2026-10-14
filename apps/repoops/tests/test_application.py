import sys
from pathlib import Path

from repoops.application import RepoOpsApplication
from repoops.runtime.models import TaskStatus
from repoops.security.policy import ExecutionPolicy


def test_application_runs_retrieval_task_and_recovers_state(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    policy = ExecutionPolicy(
        workspace_root=sample_repository,
        allowed_executables=frozenset({Path(sys.executable).name}),
    )
    app = RepoOpsApplication(sample_repository, state_dir, policy=policy)
    app.rebuild_index()
    app.create_task("task-1", "find the safe command runner")

    hits = app.run_retrieval_task("task-1", "safe command runner")

    assert hits[0].path == "README.md"
    assert app.tasks.get("task-1").status is TaskStatus.SUCCEEDED
    assert app.checkpoints.latest("task-1").step == "retrieval"
    assert app.telemetry.summarize("task-1").event_count == 1

    recovered_app = RepoOpsApplication(sample_repository, state_dir, policy=policy)
    recovered_hits = recovered_app.run_retrieval_task("task-1", "safe command runner")
    assert recovered_hits[0].path == "README.md"
    assert recovered_app.checkpoints.count("task-1") == 1


def test_application_routes_commands_through_policy_executor(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    policy = ExecutionPolicy(
        workspace_root=sample_repository,
        allowed_executables=frozenset({Path(sys.executable).name}),
    )
    app = RepoOpsApplication(sample_repository, tmp_path / "state", policy=policy)
    app.create_task("task-2", "run a safe check")

    result = app.run_command("task-2", [sys.executable, "-c", "print('ok')"])

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"
    assert app.tasks.get("task-2").status is TaskStatus.SUCCEEDED
