"""Error responses never leak internal detail."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import NotFoundError, register_error_handlers


@pytest.fixture
def failing_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("connection string postgres://user:hunter2@db/prod")

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("Scan not found.")

    return TestClient(app, raise_server_exceptions=False)


def test_unexpected_error_hides_the_exception_text(failing_client: TestClient) -> None:
    response = failing_client.get("/boom")
    body = response.text

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error."}
    }
    assert "hunter2" not in body
    assert "Traceback" not in body


def test_application_error_reports_its_own_code(failing_client: TestClient) -> None:
    response = failing_client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Scan not found."}
    }


def test_unknown_route_returns_a_structured_error(failing_client: TestClient) -> None:
    response = failing_client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_missing_evidence_uses_the_error_contract() -> None:
    from app.db.integrity import MissingEvidenceError

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/finding")
    async def bare_finding() -> None:
        raise MissingEvidenceError("Finding 'abc' cannot be persisted without evidence.")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/finding")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "missing_evidence"
    assert "Traceback" not in response.text
