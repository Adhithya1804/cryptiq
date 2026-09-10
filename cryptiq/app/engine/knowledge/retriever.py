"""In-memory semantic and lexical knowledge retriever.

Provides fast, deterministic, non-hallucinated retrieval of authoritative PQC standards
and domain guidance without external vector database dependencies.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from app.engine.knowledge.corpus import KNOWLEDGE_BASE_VERSION, get_all_chunks
from app.engine.knowledge.models import KnowledgeChunk, KnowledgeResult

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_-]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_PATTERN.findall(text) if len(t) > 1]


class KnowledgeRetriever(Protocol):
    """Abstract protocol for knowledge retrieval."""

    @property
    def version(self) -> str:
        ...

    def search(
        self,
        query: str,
        *,
        topics: Sequence[str] | None = None,
        top_k: int = 4,
    ) -> list[KnowledgeResult]:
        ...


class InMemoryKnowledgeRetriever:
    """Deterministic, in-process knowledge retriever using BM25-style lexical matching."""

    def __init__(self, chunks: Sequence[KnowledgeChunk] | None = None) -> None:
        self._chunks: list[KnowledgeChunk] = list(chunks if chunks is not None else get_all_chunks())
        self._version = KNOWLEDGE_BASE_VERSION
        self._k1 = 1.5
        self._b = 0.75

        # Index chunks
        self._doc_lengths: list[int] = []
        self._doc_term_freqs: list[Counter[str]] = []
        self._df: Counter[str] = Counter()
        self._N = len(self._chunks)

        for chunk in self._chunks:
            # Combine title, section, topics and content into indexable text
            doc_text = f"{chunk.title} {chunk.section} {' '.join(chunk.topics)} {chunk.content}"
            tokens = _tokenize(doc_text)
            tf = Counter(tokens)
            self._doc_term_freqs.append(tf)
            self._doc_lengths.append(len(tokens))
            for term in tf:
                self._df[term] += 1

        self._avg_dl = sum(self._doc_lengths) / self._N if self._N > 0 else 1.0

    @property
    def version(self) -> str:
        return self._version

    def search(
        self,
        query: str,
        *,
        topics: Sequence[str] | None = None,
        top_k: int = 4,
    ) -> list[KnowledgeResult]:
        """Search curated corpus for relevant sections and return attributable citations."""
        if not self._chunks:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens and not topics:
            return []

        target_topics = {t.lower() for t in topics} if topics else set()

        scores: list[tuple[float, KnowledgeChunk]] = []
        for i, chunk in enumerate(self._chunks):
            tf = self._doc_term_freqs[i]
            dl = self._doc_lengths[i]

            score = 0.0
            for term in query_tokens:
                if term in tf:
                    freq = tf[term]
                    df = self._df[term]
                    # Standard BM25 IDF formulation
                    idf = math.log(1.0 + (self._N - df + 0.5) / (df + 0.5))
                    num = freq * (self._k1 + 1.0)
                    den = freq + self._k1 * (1.0 - self._b + self._b * (dl / self._avg_dl))
                    score += idf * (num / den)

            # Topic matching boost
            chunk_topics = {t.lower() for t in chunk.topics}
            if target_topics:
                matching_topics = target_topics & chunk_topics
                if matching_topics:
                    score += 2.5 * len(matching_topics)

            if score > 0.0:
                scores.append((score, chunk))

        scores.sort(key=lambda item: item[0], reverse=True)
        results: list[KnowledgeResult] = []
        for score, chunk in scores[:top_k]:
            results.append(
                KnowledgeResult(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    publisher=chunk.publisher,
                    url=chunk.url,
                    section=chunk.section,
                    version=chunk.version,
                    content=chunk.content,
                    relevance_score=score,
                )
            )

        return results

    retrieve = search
