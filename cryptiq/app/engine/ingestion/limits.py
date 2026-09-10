"""Resource limits applied while acquiring a source snapshot.

The values live in application settings. This module is the single place that
reads them, so no limit is duplicated in the ingestion code.
"""

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.errors import ArchiveTooLargeError


@dataclass(frozen=True)
class IngestionLimits:
    """Ceilings for one ingestion, in bytes and file counts.

    max_file_bytes is a limit on what is analysed, not on what is extracted:
    real repositories ship large non-source files such as test vectors, and
    refusing the whole snapshot over one of them would make ingestion useless.
    Discovery marks those files TOO_LARGE. Disk use stays bounded by
    max_extracted_bytes, which is enforced as the archive is written.
    """

    max_archive_bytes: int
    max_extracted_bytes: int
    max_files: int
    max_file_bytes: int

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "IngestionLimits":
        """Build the limits from application settings."""
        settings = settings or get_settings()
        return cls(
            max_archive_bytes=settings.max_archive_bytes,
            max_extracted_bytes=settings.max_extracted_bytes,
            max_files=settings.max_files,
            max_file_bytes=settings.max_file_bytes,
        )

    def check_archive_bytes(self, downloaded: int) -> None:
        """Reject a downloaded archive larger than the configured ceiling."""
        if downloaded > self.max_archive_bytes:
            raise ArchiveTooLargeError(
                f"Archive exceeds the {self.max_archive_bytes} byte limit."
            )

    def check_extracted_bytes(self, extracted: int) -> None:
        """Reject an extraction whose running total exceeds the ceiling."""
        if extracted > self.max_extracted_bytes:
            raise ArchiveTooLargeError(
                f"Extracted content exceeds the {self.max_extracted_bytes} byte limit."
            )

    def check_file_count(self, count: int) -> None:
        """Reject an archive holding more entries than the ceiling."""
        if count > self.max_files:
            raise ArchiveTooLargeError(
                f"Archive holds more than the {self.max_files} permitted files."
            )
