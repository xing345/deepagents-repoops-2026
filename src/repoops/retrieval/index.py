from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Protocol

from ..storage import connect
from .chunker import CodeChunker
from .models import SearchHit


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class HashEmbeddingProvider:
    """Deterministic offline vectorizer used for tests and local smoke runs."""

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return tuple(vector)
        return tuple(value / norm for value in vector)


class HybridIndex:
    def __init__(self, database_path: Path, embedding: EmbeddingProvider | None = None) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding = embedding or HashEmbeddingProvider()
        self._initialize()

    def rebuild(self, repository_root: Path) -> None:
        chunks = list(CodeChunker(repository_root).build_chunks())
        with connect(self.database_path) as connection:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM chunks_fts")
            connection.executemany(
                "INSERT INTO chunks "
                "(chunk_id, path, start_line, end_line, text, language, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        chunk.chunk_id,
                        chunk.path,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.text,
                        chunk.language,
                        json.dumps(self.embedding.embed(chunk.text)),
                    )
                    for chunk in chunks
                ],
            )
            connection.executemany(
                "INSERT INTO chunks_fts (chunk_id, path, text) VALUES (?, ?, ?)",
                [(chunk.chunk_id, chunk.path, chunk.text) for chunk in chunks],
            )

    def chunk_count(self) -> int:
        with connect(self.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        lexical_weight: float = 0.55,
        vector_weight: float = 0.45,
    ) -> list[SearchHit]:
        if limit < 1:
            raise ValueError("limit must be positive")
        if lexical_weight < 0 or vector_weight < 0 or lexical_weight + vector_weight == 0:
            raise ValueError("retrieval weights must be non-negative and not both zero")
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]+", query.lower())
        if not tokens:
            return []
        total_weight = lexical_weight + vector_weight
        lexical_weight /= total_weight
        vector_weight /= total_weight
        fts_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
        with connect(self.database_path) as connection:
            lexical_rows = connection.execute(
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? "
                "ORDER BY bm25(chunks_fts)",
                (fts_query,),
            ).fetchall()
            rows = connection.execute(
                "SELECT chunk_id, path, start_line, end_line, text, embedding FROM chunks"
            ).fetchall()

        lexical_scores = {row[0]: 1.0 / (rank + 1) for rank, row in enumerate(lexical_rows)}
        query_vector = self.embedding.embed(query)
        candidates: list[SearchHit] = []
        for chunk_id, path, start_line, end_line, text, raw_embedding in rows:
            vector = json.loads(raw_embedding)
            vector_score = max(0.0, self._dot(query_vector, vector))
            lexical_score = lexical_scores.get(chunk_id, 0.0)
            score = lexical_weight * lexical_score + vector_weight * vector_score
            if score == 0.0:
                continue
            candidates.append(
                SearchHit(
                    chunk_id=chunk_id,
                    path=path,
                    start_line=start_line,
                    end_line=end_line,
                    snippet=text[:1200],
                    score=min(1.0, score),
                    lexical_score=lexical_score,
                    vector_score=vector_score,
                )
            )
        candidates.sort(key=lambda hit: (-hit.score, hit.path, hit.start_line))
        return candidates[:limit]

    def _initialize(self) -> None:
        with connect(self.database_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS chunks ("
                "chunk_id TEXT PRIMARY KEY, path TEXT NOT NULL, start_line INTEGER NOT NULL, "
                "end_line INTEGER NOT NULL, text TEXT NOT NULL, language TEXT NOT NULL, "
                "embedding TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
                "chunk_id UNINDEXED, path, text)"
            )

    @staticmethod
    def _dot(left: tuple[float, ...], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=False))
