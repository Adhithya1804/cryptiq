"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    Evidence,
    Finding,
    Repository,
    Scan,
)
from app.db.models.enums import Confidence, CryptographicRole, ReviewPriority
from app.engine.fingerprints import fingerprint
from app.main import create_app


@pytest.fixture(autouse=True)
def _relax_rate_limit(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the per-client rate limiter out of the way of the general suite.

    The limiter ships enabled with production limits; a test that legitimately
    makes dozens of calls from the one ``testclient`` identity would otherwise
    hit ``429``. Tests that exercise the limiter itself construct their own
    app with explicit low limits. ``app.rate_limit`` has its own unit tests.
    """
    from app.config import get_settings

    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Return a test client bound to a fresh application instance."""
    return TestClient(create_app())


@pytest.fixture
def engine() -> Iterator[Engine]:
    """Return an in-memory SQLite engine with the full schema and FKs enforced."""
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless the pragma is set per connection, so
    # ON DELETE behaviour would be untestable without this.
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Return a session bound to the in-memory schema."""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def repository(session: Session) -> Repository:
    """Return a persisted repository."""
    repository = Repository(
        provider="github",
        owner="pyca",
        name="cryptography",
        canonical_url="https://github.com/pyca/cryptography",
    )
    session.add(repository)
    session.commit()
    return repository


@pytest.fixture
def scan(session: Session, repository: Repository) -> Scan:
    """Return a persisted scan of the repository fixture."""
    scan = Scan(repository_id=repository.id, commit_sha="a" * 40)
    session.add(scan)
    session.commit()
    return scan


def build_finding(scan_id: str, **overrides: object) -> Finding:
    """Return an unsaved finding with its required evidence attached."""
    fields: dict[str, object] = {
        "scan_id": scan_id,
        "fingerprint": fingerprint("github/pyca/cryptography", "src/keys.py", "rsa-generate"),
        "algorithm": "RSA",
        "primitive": "PUBLIC_KEY",
        "library": "cryptography",
        "api": "rsa.generate_private_key",
        "operation": "KEY_GENERATION",
        "file_path": "src/keys.py",
        "start_line": 10,
        "end_line": 12,
        "role": CryptographicRole.DIGITAL_SIGNATURE,
        "confidence": Confidence.HIGH,
        "priority": ReviewPriority.HIGH,
    }
    fields.update(overrides)
    finding = Finding(**fields)
    finding.evidence = Evidence(
        repository_sha="a" * 40,
        file_path=str(fields["file_path"]),
        start_line=int(fields["start_line"]),  # type: ignore[arg-type]
        end_line=int(fields["end_line"]),  # type: ignore[arg-type]
        source_excerpt="rsa.generate_private_key(public_exponent=65537, key_size=2048)",
        rule_id="rsa-key-generation",
        parser_version="python-ast-1",
        ruleset_version="0.3.0",
    )
    return finding


@pytest.fixture
def finding(session: Session, scan: Scan) -> Finding:
    """Return a persisted finding with evidence."""
    finding = build_finding(scan.id)
    session.add(finding)
    session.commit()
    return finding
