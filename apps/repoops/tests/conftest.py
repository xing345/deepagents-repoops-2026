from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_repository(tmp_path: Path) -> Path:
    """Create a small deterministic repository fixture for offline tests."""
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text(
        "# Sample\n\nThis repository has a safe command runner.\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "search.py").write_text(
        "def search_code(query: str) -> list[str]:\n"
        "    return [query]\n",
        encoding="utf-8",
    )
    return tmp_path
