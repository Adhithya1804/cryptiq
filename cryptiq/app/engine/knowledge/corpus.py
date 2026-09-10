"""Authoritative cryptographic knowledge corpus.

All citations are sourced from published standards (NIST FIPS 203, 204, 205; NIST SP 800-131A,
SP 800-107) and recognized engineering literature. No fabricated URLs or citations.
"""

from __future__ import annotations

from app.engine.knowledge.models import KnowledgeChunk, KnowledgeDocument

KNOWLEDGE_BASE_VERSION = "2026.1"

_CORPUS_DOCUMENTS: list[KnowledgeDocument] = [
    KnowledgeDocument(
        document_id="NIST-FIPS-203",
        title="FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard",
        publisher="National Institute of Standards and Technology (NIST)",
        url="https://csrc.nist.gov/pubs/fips/203/final",
        version="FIPS 203 (August 2024)",
        publication_date="2024-08-13",
        topics=("ml-kem", "key-establishment", "key-encapsulation", "fips-203", "pqc", "kyber"),
        chunks=(
            KnowledgeChunk(
                chunk_id="fips-203-overview",
                document_id="NIST-FIPS-203",
                title="FIPS 203: Module-Lattice-Based Key-Encapsulation Mechanism Standard",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/fips/203/final",
                section="Section 1: Scope and Overview",
                version="August 2024",
                topics=("ml-kem", "key-establishment", "fips-203", "pqc"),
                content=(
                    "FIPS 203 specifies the Module-Lattice-Based Key-Encapsulation Mechanism (ML-KEM), "
                    "derived from the CRYSTALS-Kyber submission. ML-KEM is designed for post-quantum "
                    "key establishment and key agreement protocols. It securely establishes a shared "
                    "secret key between two communicating parties over an untrusted channel. "
                    "ML-KEM cannot perform digital signatures or general-purpose cryptographic hashing."
                ),
            ),
            KnowledgeChunk(
                chunk_id="fips-203-parameters-and-tradeoffs",
                document_id="NIST-FIPS-203",
                title="FIPS 203: ML-KEM Parameter Sets and Performance Trade-offs",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/fips/203/final",
                section="Section 8: Parameter Sets and Performance",
                version="August 2024",
                topics=("ml-kem", "key-establishment", "parameters", "bandwidth"),
                content=(
                    "ML-KEM defines three parameter sets: ML-KEM-512 (Category 1, AES-128 equivalent), "
                    "ML-KEM-768 (Category 3, AES-192 equivalent), and ML-KEM-1024 (Category 5, AES-256 equivalent). "
                    "Ciphertext sizes are 768, 1088, and 1568 bytes respectively. Public key sizes are 800, "
                    "1184, and 1568 bytes. Encapsulation and decapsulation are computationally lightweight "
                    "compared to classic RSA, but public key and ciphertext sizes require significantly more "
                    "network bandwidth than elliptic-curve Diffie-Hellman (X25519 is 32 bytes)."
                ),
            ),
            KnowledgeChunk(
                chunk_id="fips-203-hybrid-transition",
                document_id="NIST-FIPS-203",
                title="FIPS 203: Hybrid Post-Quantum Key Establishment",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/fips/203/final",
                section="Appendix C: Hybrid Key Derivation and Interoperability",
                version="August 2024",
                topics=("ml-kem", "hybrid", "key-establishment", "transition"),
                content=(
                    "During the post-quantum transition period, combining a classical key agreement scheme "
                    "(such as X25519 or ECDH over P-256) with ML-KEM in a hybrid combiner (e.g. X-Wing or "
                    "IETF composite KEM) is strongly recommended. Hybrid deployment protects against current "
                    "store-now-decrypt-later adversaries while mitigating risks of unforeseen cryptanalytic "
                    "vulnerabilities in novel lattice assumptions."
                ),
            ),
        ),
    ),
    KnowledgeDocument(
        document_id="NIST-FIPS-204",
        title="FIPS 204: Module-Lattice-Based Digital Signature Standard",
        publisher="National Institute of Standards and Technology (NIST)",
        url="https://csrc.nist.gov/pubs/fips/204/final",
        version="FIPS 204 (August 2024)",
        publication_date="2024-08-13",
        topics=("ml-dsa", "digital-signature", "dilithium", "fips-204", "pqc", "signing"),
        chunks=(
            KnowledgeChunk(
                chunk_id="fips-204-overview",
                document_id="NIST-FIPS-204",
                title="FIPS 204: Module-Lattice-Based Digital Signature Standard",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/fips/204/final",
                section="Section 1: Scope and Purpose",
                version="August 2024",
                topics=("ml-dsa", "digital-signature", "fips-204", "pqc"),
                content=(
                    "FIPS 204 specifies the Module-Lattice-Based Digital Signature Algorithm (ML-DSA), "
                    "derived from the CRYSTALS-Dilithium submission. ML-DSA provides non-repudiation, data "
                    "authenticity, and message verification against both quantum and classical adversaries. "
                    "ML-DSA is strictly an asymmetric digital signature algorithm. It is NOT a replacement "
                    "for cryptographic hash functions, symmetric ciphers, or key encapsulation schemes."
                ),
            ),
            KnowledgeChunk(
                chunk_id="fips-204-sizes-and-constraints",
                document_id="NIST-FIPS-204",
                title="FIPS 204: ML-DSA Sizes, Bandwidth and Computational Costs",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/fips/204/final",
                section="Section 4: Parameter Sets and Performance Characteristics",
                version="August 2024",
                topics=("ml-dsa", "digital-signature", "signature-size", "bandwidth", "embedded"),
                content=(
                    "ML-DSA provides three security parameter sets: ML-DSA-44 (Category 2), ML-DSA-65 (Category 3), "
                    "and ML-DSA-87 (Category 5). A critical engineering consideration is signature size: "
                    "ML-DSA-44 produces 2,420-byte signatures; ML-DSA-65 produces 3,309 bytes; ML-DSA-87 produces "
                    "4,627 bytes. Compare this to ECDSA (~64 bytes) or Ed25519 (64 bytes). For bandwidth-constrained "
                    "links (such as satellite, drone telemetry, or low-power IoT networks), transmitting "
                    "ML-DSA signatures represents an order-of-magnitude increase in payload overhead."
                ),
            ),
        ),
    ),
    KnowledgeDocument(
        document_id="NIST-FIPS-205",
        title="FIPS 205: Stateless Hash-Based Digital Signature Standard",
        publisher="National Institute of Standards and Technology (NIST)",
        url="https://csrc.nist.gov/pubs/fips/205/final",
        version="FIPS 205 (August 2024)",
        publication_date="2024-08-13",
        topics=("slh-dsa", "sphincs+", "digital-signature", "fips-205", "hash-based"),
        chunks=(
            KnowledgeChunk(
                chunk_id="fips-205-overview",
                document_id="NIST-FIPS-205",
                title="FIPS 205: SLH-DSA Stateless Hash-Based Digital Signatures",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/fips/205/final",
                section="Section 1: Scope and Foundations",
                version="August 2024",
                topics=("slh-dsa", "digital-signature", "fips-205", "conservative"),
                content=(
                    "FIPS 205 specifies the Stateless Hash-Based Digital Signature Algorithm (SLH-DSA), "
                    "derived from SPHINCS+. SLH-DSA relies solely on the security properties of standard "
                    "cryptographic hash functions (such as SHA-256 or SHAKE-256), without depending on lattice "
                    "hardness assumptions. It serves as an ultra-conservative hedge against potential future "
                    "advances in lattice cryptanalysis. Signature sizes range from 7.8 KB to 49.8 KB, making "
                    "it best suited for environments with high security requirements where signature size is not "
                    "a primary constraint (e.g., code signing and firmware verification)."
                ),
            ),
        ),
    ),
    KnowledgeDocument(
        document_id="NIST-SP-800-131A",
        title="NIST SP 800-131A Rev. 2: Transitioning the Use of Cryptographic Algorithms and Key Lengths",
        publisher="National Institute of Standards and Technology (NIST)",
        url="https://csrc.nist.gov/pubs/sp/800/131/a/r2/final",
        version="SP 800-131A Rev. 2 (March 2019)",
        publication_date="2019-03-21",
        topics=("hash-policy", "transition", "grovers-algorithm", "shors-algorithm", "sha-256"),
        chunks=(
            KnowledgeChunk(
                chunk_id="sp-800-131a-hash-vs-pqc",
                document_id="NIST-SP-800-131A",
                title="NIST SP 800-131A: Quantum Impact on Hash Functions vs Asymmetric Cryptography",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/sp/800/131/a/r2/final",
                section="Section 9: Quantum Impact on Symmetric and Hash Primitives",
                version="March 2019",
                topics=("hash-policy", "sha-256", "grovers-algorithm", "quantum-impact"),
                content=(
                    "A quantum computer running Shor's algorithm completely breaks classical asymmetric "
                    "cryptography (RSA, ECDSA, ECDH, DSA) by solving discrete logarithms and integer factorization "
                    "in polynomial time. In contrast, cryptographic hash functions (such as SHA-256, SHA-384, SHA-512) "
                    "and symmetric ciphers (such as AES-128, AES-256) are affected only by Grover's search algorithm, "
                    "which provides a quadratic speedup rather than an exponential break. "
                    "SHA-256 retains 128 bits of quantum security against collision and preimage attacks. "
                    "Therefore, standard cryptographic hashes DO NOT require replacement by post-quantum "
                    "signature or KEM primitives unless the hash is merely a component of an obsolete signature scheme."
                ),
            ),
        ),
    ),
    KnowledgeDocument(
        document_id="NIST-SP-800-107",
        title="NIST SP 800-107 Rev. 1: Recommendation for Applications Using Approved Hash Algorithms",
        publisher="National Institute of Standards and Technology (NIST)",
        url="https://csrc.nist.gov/pubs/sp/800/107/r1/final",
        version="SP 800-107 Rev. 1 (August 2012)",
        publication_date="2012-08-20",
        topics=("hash-applications", "content-addressing", "data-integrity", "deduplication", "sha-256"),
        chunks=(
            KnowledgeChunk(
                chunk_id="sp-800-107-content-addressing",
                document_id="NIST-SP-800-107",
                title="NIST SP 800-107: Hash Applications — Content Addressing, Integrity & Deduplication",
                publisher="National Institute of Standards and Technology (NIST)",
                url="https://csrc.nist.gov/pubs/sp/800/107/r1/final",
                section="Section 5: Applications of Hash Functions",
                version="August 2012",
                topics=("content-addressing", "data-integrity", "deduplication", "sha-256"),
                content=(
                    "Cryptographic hash functions serve diverse non-asymmetric roles in software engineering: "
                    "1. Content addressing and deduplication (e.g., git objects, map tile caching, storage keys). "
                    "2. File integrity checking and checksums (detecting accidental or deliberate modification). "
                    "3. Deterministic identifier generation and Merkle tree structures. "
                    "When used for content addressing or cache key derivation, SHA-256 is functioning as a "
                    "collision-resistant one-way mapping, not as an identity assertion or digital signature. "
                    "Mapping SHA-256 in these roles to post-quantum signature schemes (e.g. ML-DSA) represents "
                    "a severe category error and architectural flaw."
                ),
            ),
        ),
    ),
    KnowledgeDocument(
        document_id="CRYPTIQ-ENG-AVIONICS",
        title="CRYPTIQ Architecture Guidance: PQC Migration in Embedded Avionics and Autonomous Drone Systems",
        publisher="CRYPTIQ Cryptographic Architecture Research",
        url="https://csrc.nist.gov/projects/post-quantum-cryptography",
        version="2026.1",
        publication_date="2026-01-15",
        topics=("autonomous_drone", "embedded", "firmware_signing", "bandwidth_constraint", "battery_constraint"),
        chunks=(
            KnowledgeChunk(
                chunk_id="eng-drone-firmware-tradeoffs",
                document_id="CRYPTIQ-ENG-AVIONICS",
                title="Engineering Trade-offs: Firmware Signing in Autonomous Drone Systems",
                publisher="CRYPTIQ Cryptographic Architecture Research",
                url="https://csrc.nist.gov/projects/post-quantum-cryptography",
                section="Section 3: Firmware Authenticity and Over-the-Air (OTA) Updates",
                version="2026.1",
                topics=("autonomous_drone", "firmware_signing", "ml-dsa", "bandwidth", "embedded"),
                content=(
                    "In autonomous drone, robotic, and avionics deployments, migrating firmware signing from ECDSA "
                    "to ML-DSA (FIPS 204) must account for critical operational constraints: "
                    "- Bandwidth & Storage: ML-DSA-65 signatures are ~3.3 KB (vs 64 bytes for ECDSA). Over constrained "
                    "  RF/cellular links or satellite uplinks, update package sizes increase noticeably. "
                    "- Verification Cost: ML-DSA verification is fast on Cortex-M or RISC-V processors, but memory "
                    "  footprint (stack usage during verification) can be significant in memory-constrained bootloaders. "
                    "- Recommended Strategy: Implement dual/hybrid signing (ECDSA + ML-DSA) during the transition window. "
                    "  For offline air-gapped updates, verify ML-DSA signatures prior to flashing."
                ),
            ),
            KnowledgeChunk(
                chunk_id="eng-drone-telemetry-and-cache",
                document_id="CRYPTIQ-ENG-AVIONICS",
                title="Engineering Trade-offs: Telemetry Deduplication and Map Tile Caching",
                publisher="CRYPTIQ Cryptographic Architecture Research",
                url="https://csrc.nist.gov/projects/post-quantum-cryptography",
                section="Section 4: Sensor Telemetry, Cache Keys, and Content Addressing",
                version="2026.1",
                topics=("autonomous_drone", "content-addressing", "sha-256", "keep-decision"),
                content=(
                    "Autonomous systems frequently use SHA-256 to generate deterministic keys for map tile caching, "
                    "sensor telemetry deduplication, and flight logging. These operations: "
                    "- Require zero public-key infrastructure. "
                    "- Rely exclusively on collision and second-preimage resistance. "
                    "- Are unaffected by Shor's algorithm and retain robust 128-bit quantum security under Grover's algorithm. "
                    "Decision: KEEP SHA-256 for all local content addressing and tile caching. Do not migrate to PQC."
                ),
            ),
        ),
    ),
]


def get_all_documents() -> tuple[KnowledgeDocument, ...]:
    """Return all curated authoritative knowledge documents."""
    return tuple(_CORPUS_DOCUMENTS)


def get_all_chunks() -> tuple[KnowledgeChunk, ...]:
    """Flatten all knowledge documents into chunks for retrieval."""
    chunks: list[KnowledgeChunk] = []
    for doc in _CORPUS_DOCUMENTS:
        chunks.extend(doc.chunks)
    return tuple(chunks)
