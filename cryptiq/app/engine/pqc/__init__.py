"""PQC: map a cryptographic role to its post-quantum review path.

A review path names the guidance to read, never a replacement to apply.
"""

from app.engine.pqc.mapper import PqcAssessment, PqcReviewPath, map_review_path

__all__ = ["PqcAssessment", "PqcReviewPath", "map_review_path"]
