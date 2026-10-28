from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CodeChunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    text: str
    language: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    snippet: str
    score: float
    lexical_score: float
    vector_score: float
