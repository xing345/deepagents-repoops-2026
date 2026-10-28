from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from deepagents import create_deep_agent
from langchain_core.tools import tool

from .application import RepoOpsApplication


def create_repoops_agent(
    model: Any,
    application: RepoOpsApplication,
    *,
    checkpointer: Any = None,
) -> Any:
    """Create a Deep Agent whose repository tools preserve RepoOps boundaries."""

    @tool("search_repository")
    def search_repository(task_id: str, query: str) -> str:
        """Search the indexed repository and return line-aware JSON hits."""
        hits = application.run_retrieval_task(task_id, query)
        return json.dumps(
            [{"path": hit.path, "start_line": hit.start_line, "end_line": hit.end_line,
              "snippet": hit.snippet, "score": hit.score} for hit in hits],
            ensure_ascii=False,
        )

    @tool("run_checked_command")
    def run_checked_command(task_id: str, command: Sequence[str]) -> str:
        """Run a command through the configured allowlist and workspace policy."""
        result = application.run_command(task_id, list(command))
        return json.dumps(
            {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": result.timed_out,
                "output_truncated": result.output_truncated,
            },
            ensure_ascii=False,
        )

    return create_deep_agent(
        model=model,
        tools=[search_repository, run_checked_command],
        system_prompt=(
            "You are a repository engineering agent. Use search_repository before making "
            "claims about code, and use run_checked_command for all execution. Never invent "
            "file contents or bypass the task_id-scoped policies."
        ),
        checkpointer=checkpointer,
        name="repoops-agent",
    )
