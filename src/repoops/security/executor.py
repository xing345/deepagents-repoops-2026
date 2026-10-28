from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .policy import ExecutionPolicy


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool
    shell_used: bool


class SafeExecutor:
    def __init__(self, policy: ExecutionPolicy) -> None:
        self.policy = policy

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ExecutionResult:
        validated = self.policy.validate(command, cwd=cwd)
        process_environment = self.policy.build_environment(env)
        try:
            completed = subprocess.run(
                list(validated.command),
                cwd=validated.cwd,
                env=process_environment,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.policy.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stdout_truncated = self._cap_output(exc.stdout or "")
            stderr, stderr_truncated = self._cap_output(exc.stderr or "")
            return ExecutionResult(
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
                output_truncated=stdout_truncated or stderr_truncated,
                shell_used=False,
            )
        stdout, stdout_truncated = self._cap_output(completed.stdout)
        stderr, stderr_truncated = self._cap_output(completed.stderr)
        return ExecutionResult(
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            output_truncated=stdout_truncated or stderr_truncated,
            shell_used=False,
        )

    def _cap_output(self, output: str | bytes) -> tuple[str, bool]:
        if isinstance(output, bytes):
            decoded = output.decode("utf-8", errors="replace")
        else:
            decoded = output
        encoded = decoded.encode("utf-8")
        if len(encoded) <= self.policy.max_output_bytes:
            return decoded, False
        truncated = encoded[: self.policy.max_output_bytes].decode("utf-8", errors="ignore")
        return truncated, True
