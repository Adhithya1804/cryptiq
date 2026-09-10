"""Unit tests for the authoritative cryptographic knowledge retriever (RAG layer).

Ensures:
- Authoritative standards are retrievable and accurately attributed.
- NIST FIPS 203 (ML-KEM), FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA), NIST SP 800-131A are indexed.
- Avionics / constrained-platform domain guidance is indexed.
- Top-k bounding, relevance ranking, and graceful handling of empty queries.
"""

from app.engine.knowledge.corpus import get_all_documents
from app.engine.knowledge.retriever import InMemoryKnowledgeRetriever


def test_corpus_contains_mandatory_authoritative_standards():
    """Knowledge corpus must contain NIST standards and drone/avionics guidance."""
    corpus = get_all_documents()
    doc_ids = {doc.document_id for doc in corpus}

    assert "NIST-FIPS-203" in doc_ids
    assert "NIST-FIPS-204" in doc_ids
    assert "NIST-FIPS-205" in doc_ids
    assert "NIST-SP-800-131A" in doc_ids
    assert "CRYPTIQ-ENG-AVIONICS" in doc_ids


def test_retriever_finds_hash_guidance_for_sha256():
    """Querying about SHA-256 and content addressing retrieves NIST SP 800-131A."""
    retriever = InMemoryKnowledgeRetriever()
    results = retriever.retrieve("SHA-256 hash content addressing data integrity", top_k=3)

    assert len(results) > 0
    doc_ids = [r.document_id for r in results]
    assert any("800-131A" in d or "AVIONICS" in d for d in doc_ids)
    assert results[0].relevance_score > 0
    # Relevant chunk discusses hash security or acceptable use
    assert any("hash" in r.content.lower() for r in results)


def test_retriever_finds_drone_avionics_bandwidth_guidance():
    """Querying about drone signature size overhead retrieves avionics guidance and FIPS 204."""
    retriever = InMemoryKnowledgeRetriever()
    results = retriever.retrieve("drone telemetry bandwidth signature size overhead ML-DSA", top_k=4)

    assert len(results) > 0
    doc_ids = [r.document_id for r in results]
    assert any(d in ("CRYPTIQ-ENG-AVIONICS", "NIST-FIPS-204") for d in doc_ids)


def test_retriever_finds_mlkem_for_key_exchange():
    """Querying about key establishment/exchange retrieves NIST FIPS 203."""
    retriever = InMemoryKnowledgeRetriever()
    results = retriever.retrieve("key establishment Diffie-Hellman ML-KEM encapsulation", top_k=3)

    assert len(results) > 0
    doc_ids = [r.document_id for r in results]
    assert "NIST-FIPS-203" in doc_ids


def test_retriever_respects_top_k():
    """Retriever strictly bounds results to requested top_k."""
    retriever = InMemoryKnowledgeRetriever()
    results = retriever.retrieve("cryptography security signature key", top_k=2)
    assert len(results) <= 2


def test_retriever_handles_empty_query_gracefully():
    """Empty or whitespace queries return empty list without error."""
    retriever = InMemoryKnowledgeRetriever()
    assert retriever.retrieve("") == []
    assert retriever.retrieve("   ") == []


def test_retriever_scores_are_sorted_descending():
    """Retrieved results are sorted in descending order of relevance."""
    retriever = InMemoryKnowledgeRetriever()
    results = retriever.retrieve("quantum computer Shor algorithm migration", top_k=5)
    scores = [r.relevance_score for r in results]
    assert scores == sorted(scores, reverse=True)
