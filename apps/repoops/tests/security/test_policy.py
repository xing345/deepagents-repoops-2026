import sys
from pathlib import Path

import pytest

from repoops.security.policy import ExecutionPolicy, PolicyViolation


def test_policy_accepts_allowed_program_inside_workspace(tmp_path: Path) -> None:
    policy = ExecutionPolicy(
        workspace_root=tmp_path,
        allowed_executables=frozenset({Path(sys.executable).name}),
    )

    validated = policy.validate([sys.executable, "-c", "print('ok')"], cwd=tmp_path)

    assert validated.executable == Path(sys.executable).name.lower()
    assert validated.cwd == tmp_path.resolve()


def test_policy_rejects_shell_strings_and_workspace_escape(tmp_path: Path) -> None:
    policy = ExecutionPolicy(
        workspace_root=tmp_path,
        allowed_executables=frozenset({Path(sys.executable).name}),
    )

    with pytest.raises(PolicyViolation, match="argument list"):
        policy.validate("python -c print('unsafe')")
    with pytest.raises(PolicyViolation, match="workspace"):
        policy.validate([sys.executable, "-c", "print('unsafe')"], cwd=tmp_path.parent)


def test_policy_rejects_unapproved_executable(tmp_path: Path) -> None:
    policy = ExecutionPolicy(workspace_root=tmp_path, allowed_executables=frozenset())

    with pytest.raises(PolicyViolation, match="not allowed"):
        policy.validate([sys.executable, "-c", "print('unsafe')"], cwd=tmp_path)
