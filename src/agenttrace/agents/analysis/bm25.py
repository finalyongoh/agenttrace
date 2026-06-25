from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in WORD_RE.findall(text)]


class ChunkBM25Index:
    """BM25 검색 인덱스. algorithm.md §22.3 β×BM25."""

    def __init__(self, chunks: list[dict]):
        self._chunk_ids = [c.get("chunk_id", "") for c in chunks]
        corpus = [
            _tokenize(f"{c.get('file_path', '')} {c.get('content', '')}")
            for c in chunks
        ]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """query에 대한 BM25 점수 상위 chunk_id 반환."""
        if not self._bm25 or not self._chunk_ids:
            return []
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(zip(self._chunk_ids, scores), key=lambda x: -x[1])
        return ranked[:top_k]

    def get_scores_dict(self, query: str) -> dict[str, float]:
        """chunk_id → BM25 score 딕셔너리."""
        return dict(self.search(query, top_k=len(self._chunk_ids)))
