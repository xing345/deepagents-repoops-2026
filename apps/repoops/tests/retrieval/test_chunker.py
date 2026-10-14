from pathlib import Path

from repoops.retrieval.chunker import ChunkingConfig, CodeChunker


def test_chunker_returns_relative_line_aware_chunks(sample_repository: Path) -> None:
    chunks = list(
        CodeChunker(
            sample_repository,
            ChunkingConfig(max_lines=2, overlap_lines=0),
        ).build_chunks()
    )

    assert [chunk.path for chunk in chunks] == [
        "README.md",
        "README.md",
        "src/search.py",
    ]
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2
    assert "safe command runner" in chunks[1].text
    assert chunks[2].language == "python"


def test_chunker_ignores_generated_and_binary_files(sample_repository: Path) -> None:
    ignored = sample_repository / ".venv" / "ignored.py"
    ignored.parent.mkdir()
    ignored.write_text("should not be indexed", encoding="utf-8")
    (sample_repository / "data.bin").write_bytes(b"\x00\x01\x02")

    chunks = list(CodeChunker(sample_repository).build_chunks())

    indexed_paths = {chunk.path for chunk in chunks}
    assert ".venv/ignored.py" not in indexed_paths
    assert "data.bin" not in indexed_paths
