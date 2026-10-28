from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .models import CodeChunk

_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".md": "markdown",
    ".rst": "text",
    ".txt": "text",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
}


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    max_lines: int = 80
    overlap_lines: int = 12
    max_file_bytes: int = 512 * 1024
    extensions: frozenset[str] = field(default_factory=lambda: frozenset(_LANGUAGES))
    ignored_directories: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {".git", ".venv", "venv", "node_modules", "dist", "build", "__pycache__", "reports"}
        )
    )

    def __post_init__(self) -> None:
        if self.max_lines < 1:
            raise ValueError("max_lines must be positive")
        if not 0 <= self.overlap_lines < self.max_lines:
            raise ValueError("overlap_lines must be in [0, max_lines)")
        if self.max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")


class CodeChunker:
    def __init__(self, root: Path, config: ChunkingConfig | None = None) -> None:
        self.root = root.resolve()
        self.config = config or ChunkingConfig()

    def build_chunks(self) -> Iterator[CodeChunk]:
        for file_path in sorted(self.root.rglob("*")):
            if not file_path.is_file() or self._is_ignored(file_path):
                continue
            if file_path.suffix.lower() not in self.config.extensions:
                continue
            try:
                data = file_path.read_bytes()
            except OSError:
                continue
            if len(data) > self.config.max_file_bytes or b"\x00" in data:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            yield from self._chunk_text(file_path, text)

    def _is_ignored(self, file_path: Path) -> bool:
        relative_parts = file_path.relative_to(self.root).parts
        return any(part in self.config.ignored_directories for part in relative_parts)

    def _chunk_text(self, file_path: Path, text: str) -> Iterator[CodeChunk]:
        lines = text.splitlines(keepends=True)
        if not lines and text:
            lines = [text]
        if not lines:
            return
        relative_path = file_path.relative_to(self.root).as_posix()
        step = self.config.max_lines - self.config.overlap_lines
        for start in range(0, len(lines), step):
            end = min(start + self.config.max_lines, len(lines))
            chunk_text = "".join(lines[start:end])
            if chunk_text.strip():
                identity = f"{relative_path}:{start + 1}:{end}:{chunk_text}"
                yield CodeChunk(
                    chunk_id=hashlib.sha1(identity.encode("utf-8")).hexdigest(),
                    path=relative_path,
                    start_line=start + 1,
                    end_line=end,
                    text=chunk_text,
                    language=_LANGUAGES.get(file_path.suffix.lower(), "text"),
                )
            if end == len(lines):
                break
