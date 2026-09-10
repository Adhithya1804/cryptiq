"""Authoritative knowledge models for PQC standards and domain guidance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeChunk:
    """A bounded section of an authoritative standard or guidance document."""

    chunk_id: str
    document_id: str
    title: str
    publisher: str
    url: str
    section: str
    version: str
    topics: tuple[str, ...]
    content: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "section": self.section,
            "version": self.version,
            "topics": list(self.topics),
            "content": self.content,
        }


@dataclass(frozen=True)
class KnowledgeDocument:
    """A full curated document."""

    document_id: str
    title: str
    publisher: str
    url: str
    version: str
    publication_date: str
    topics: tuple[str, ...]
    chunks: tuple[KnowledgeChunk, ...]


@dataclass(frozen=True)
class KnowledgeResult:
    """A retrieved, attributable source citation with relevance score."""

    document_id: str
    chunk_id: str
    title: str
    publisher: str
    url: str
    section: str
    version: str
    content: str
    relevance_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "section": self.section,
            "version": self.version,
            "content": self.content,
            "relevance_score": round(self.relevance_score, 4),
        }
