"""A completed scan answers for an identical later request."""

from app.db.models import Repository, Scan
from app.db.models.enums import ScanStatus, SourceState
from app.engine.fingerprints import ScanIdentity
from app.services import find_completed_scan, identity_of, mark_served_from_cache


def _identity(**overrides) -> ScanIdentity:
    fields = {
        "provider": "github",
        "owner": "pyca",
        "name": "cryptography",
        "commit_sha": "a" * 40,
        "parser_version": "python-ast-1",
        "ruleset_version": "0.3.0",
        "pqc_ruleset_version": "0.2.0",
    }
    fields.update(overrides)
    return ScanIdentity(**fields)


def _complete(session, scan: Scan) -> Scan:
    scan.status = ScanStatus.COMPLETED
    scan.source_state = SourceState.LIVE
    session.commit()
    return scan


def test_a_scan_identity_is_read_off_the_stored_rows(scan: Scan, repository: Repository) -> None:
    assert identity_of(scan, repository) == _identity()


def test_a_completed_scan_is_found(session, scan: Scan) -> None:
    _complete(session, scan)

    found = find_completed_scan(session, _identity())

    assert found is not None
    assert found.id == scan.id


def test_a_scan_that_has_not_completed_is_not_a_cache_hit(session, scan: Scan) -> None:
    assert scan.status is ScanStatus.QUEUED
    assert find_completed_scan(session, _identity()) is None

    scan.status = ScanStatus.FAILED
    session.commit()
    assert find_completed_scan(session, _identity()) is None


def test_every_part_of_the_identity_must_match(session, scan: Scan) -> None:
    _complete(session, scan)

    for field in (
        "provider",
        "owner",
        "name",
        "commit_sha",
        "parser_version",
        "ruleset_version",
        "pqc_ruleset_version",
    ):
        identity = _identity(**{field: "different"})
        assert find_completed_scan(session, identity) is None, field


def test_a_different_commit_is_not_a_cache_hit(session, scan: Scan) -> None:
    _complete(session, scan)

    assert find_completed_scan(session, _identity(commit_sha="b" * 40)) is None


def test_the_requesting_scan_can_be_excluded(session, scan: Scan) -> None:
    _complete(session, scan)

    assert find_completed_scan(session, _identity(), exclude_scan_id=scan.id) is None


def test_the_oldest_completed_scan_is_returned(session, repository: Repository, scan: Scan) -> None:
    _complete(session, scan)
    later = Scan(repository_id=repository.id, commit_sha="a" * 40, status=ScanStatus.COMPLETED)
    session.add(later)
    session.commit()

    assert find_completed_scan(session, _identity()).id == scan.id


def test_a_reused_scan_is_marked_as_cached(session, scan: Scan) -> None:
    _complete(session, scan)

    mark_served_from_cache(scan)
    session.commit()

    assert session.get(Scan, scan.id).source_state is SourceState.CACHED_REAL
