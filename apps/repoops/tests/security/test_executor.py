import sys
from pathlib import Path

from repoops.security.executor import SafeExecutor
from repoops.security.policy import ExecutionPolicy


def _policy(root: Path, **kwargs: object) -> ExecutionPolicy:
    return ExecutionPolicy(
        workspace_root=root,
        allowed_executables=frozenset({Path(sys.executable).name}),
        **kwargs,
    )


def test_executor_runs_without_shell_and_caps_output(tmp_path: Path) -> None:
    executor = SafeExecutor(_policy(tmp_path, max_output_bytes=24))

    result = executor.run([sys.executable, "-c", "print('x' * 200)"], cwd=tmp_path)

    assert result.returncode == 0
    assert result.shell_used is False
    assert result.output_truncated is True
    assert len(result.stdout.encode("utf-8")) <= 24


def test_executor_reports_timeout(tmp_path: Path) -> None:
    executor = SafeExecutor(_policy(tmp_path, timeout_seconds=0.1))

    result = executor.run([sys.executable, "-c", "import time; time.sleep(1)"], cwd=tmp_path)

    assert result.timed_out is True
    assert result.returncode is None
