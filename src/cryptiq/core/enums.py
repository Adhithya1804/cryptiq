"""Core enumerations for Cryptiq static analysis engine."""

from enum import Enum


class ImpactNodeType(str, Enum):
    """Types of nodes represented in the bounded impact graph."""
    ALGORITHM = "ALGORITHM"
    API = "API"
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    MODULE = "MODULE"
    FILE = "FILE"


class ImpactRelationship(str, Enum):
    """Deterministic relationship types between impact nodes."""
    USES = "USES"
    CALLS = "CALLS"
    DEFINED_IN = "DEFINED_IN"
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"


class ImpactScope(str, Enum):
    """Scope of established reachability for an impact graph."""
    STATICALLY_OBSERVED = "STATICALLY_OBSERVED"
    SCANNED_REPOSITORY = "SCANNED_REPOSITORY"


class PriorityLevel(str, Enum):
    """Migration Review Priority levels (strictly NOT vulnerability severity)."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ConfidenceLevel(str, Enum):
    """Confidence level of static observation."""
    CONFIRMED = "CONFIRMED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class CryptoRole(str, Enum):
    """Cryptographic purpose/role of observed primitive."""
    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"
    KEY_ESTABLISHMENT = "KEY_ESTABLISHMENT"
    ENCRYPTION = "ENCRYPTION"
    SYMMETRIC_ENCRYPTION = "SYMMETRIC_ENCRYPTION"
    HASH = "HASH"
    TLS_CERTIFICATE = "CERTIFICATE / TLS"
    UNKNOWN = "UNKNOWN"


class ScanStatus(str, Enum):
    """Lifecycle status of a repository scan."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStatus(str, Enum):
    """Lifecycle status of a scan job in the database queue."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RetrievalMode(str, Enum):
    """Source retrieval origin state."""
    LIVE = "LIVE"
    CACHED_REAL = "CACHED_REAL"
    UNAVAILABLE = "UNAVAILABLE"


class ErrorCode(str, Enum):
    """Sanitized system and worker error codes."""
    REPOSITORY_NOT_FOUND = "REPOSITORY_NOT_FOUND"
    COMMIT_NOT_FOUND = "COMMIT_NOT_FOUND"
    REPOSITORY_UNAVAILABLE = "REPOSITORY_UNAVAILABLE"
    PARSER_ERROR = "PARSER_ERROR"
    ANALYSIS_ERROR = "ANALYSIS_ERROR"
    SCAN_TIMEOUT = "SCAN_TIMEOUT"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
