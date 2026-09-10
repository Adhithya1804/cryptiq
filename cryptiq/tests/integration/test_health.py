"""The application starts and serves the health endpoint on both paths."""

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_application_starts() -> None:
    app = create_app()

    assert app.title == "Cryptiq"


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_returns_ok(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cryptiq",
        "version": __version__,
    }


@pytest.mark.parametrize("path", ["/health/ready", "/api/v1/health/ready"])
def test_readiness_reports_database_reachable(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "cryptiq",
        "version": __version__,
        "database": "ok",
    }
