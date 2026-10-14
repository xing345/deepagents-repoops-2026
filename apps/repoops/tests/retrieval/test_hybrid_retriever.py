from pathlib import Path

from repoops.retrieval.index import HashEmbeddingProvider, HybridIndex


def test_hybrid_search_combines_lexical_and_vector_signals(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    index = HybridIndex(
        tmp_path / "repo.sqlite3",
        embedding=HashEmbeddingProvider(dimensions=64),
    )
    index.rebuild(sample_repository)

    hits = index.search("safe command execution", limit=3)

    assert hits
    assert hits[0].path == "README.md"
    assert 0.0 <= hits[0].score <= 1.0
    assert hits[0].start_line >= 1
    assert hits[0].end_line >= hits[0].start_line
    assert hits[0].snippet


def test_rebuild_is_idempotent_and_finds_code_symbols(
    sample_repository: Path,
    tmp_path: Path,
) -> None:
    index = HybridIndex(tmp_path / "repo.sqlite3")
    index.rebuild(sample_repository)
    first_count = index.chunk_count()
    index.rebuild(sample_repository)

    assert index.chunk_count() == first_count
    assert index.search("search_code", limit=1)[0].path == "src/search.py"
