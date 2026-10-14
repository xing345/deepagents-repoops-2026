from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path


class PolicyViolation(ValueError):
    """Raised when a process request violates the execution policy."""


@dataclass(frozen=True, slots=True)
class ValidatedCommand:
    command: tuple[str, ...]
    executable: str
    cwd: Path


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    workspace_root: Path
    allowed_executables: frozenset[str] = frozenset({"python", "python.exe"})
    allowed_environment: frozenset[str] = field(
        default_factory=lambda: frozenset({"PATH", "SystemRoot", "WINDIR", "TEMP", "TMP"})
    )
    timeout_seconds: float = 30.0
    max_output_bytes: int = 100_000

    def __post_init__(self) -> None:
        root = self.workspace_root.resolve()
        object.__setattr__(self, "workspace_root", root)
        normalized = frozenset(Path(name).name.lower() for name in self.allowed_executables)
        object.__setattr__(self, "allowed_executables", normalized)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")

    def validate(
        self,
        command: Sequence[str] | str,
        *,
        cwd: Path | None = None,
    ) -> ValidatedCommand:
        if isinstance(command, str):
            raise PolicyViolation("command must be an argument list, not a shell string")
        if not command or any(not isinstance(argument, str) for argument in command):
            raise PolicyViolation("command must be a non-empty list of strings")
        executable = Path(command[0]).name.lower()
        if executable not in self.allowed_executables:
            raise PolicyViolation(f"executable is not allowed: {executable}")
        candidate_cwd = (cwd or self.workspace_root).resolve()
        if not self._inside_workspace(candidate_cwd):
            raise PolicyViolation("working directory must stay inside the workspace")
        if not candidate_cwd.is_dir():
            raise PolicyViolation("working directory does not exist")
        return ValidatedCommand(tuple(command), executable, candidate_cwd)

    def build_environment(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        environment = {
            key: value for key, value in os.environ.items() if key in self.allowed_environment
        }
        if extra:
            disallowed = set(extra) - self.allowed_environment
            if disallowed:
                names = ", ".join(sorted(disallowed))
                raise PolicyViolation(f"environment variables are not allowed: {names}")
            environment.update(extra)
        return environment

    def _inside_workspace(self, candidate: Path) -> bool:
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError:
            return False
        return True
