"""Unit tests for the in-process rate limiter (app.rate_limit).

Tests:
- RateLimiter counter store:
  - default, write, expensive bucket budgets
  - window reset with simulated clock progression
  - LRU memory capping and eviction past max_tracked_clients
  - retry_after calculation
- RateLimitMiddleware:
  - normal requests pass through
  - blocked requests receive 429 with Retry-After header and standard envelope
  - health probe exemption (/health, /healthz, /api/v1/health)
  - CORS preflight OPTIONS exemption
  - client IP resolution (socket vs right-most X-Forwarded-For when trust_proxy_headers=True/False)
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

from app.rate_limit import RateLimiter, RateLimitMiddleware, _bucket_for, _client_ip


class _Clock:
    def __init__(self, initial: float = 1000.0) -> None:
        self.time = initial

    def __call__(self) -> float:
        return self.time

    def advance(self, seconds: float) -> None:
        self.time += seconds


# ----------------------------------------------------------- RateLimiter tests ---


def test_rate_limiter_buckets_and_limits():
    limiter = RateLimiter(
        window_seconds=60,
        default_max=10,
        write_max=5,
        expensive_max=2,
    )
    assert limiter.limit_for("default") == 10
    assert limiter.limit_for("write") == 5
    assert limiter.limit_for("expensive") == 2
    assert limiter.limit_for("other") == 10


def test_rate_limiter_allows_under_budget():
    clock = _Clock(100.0)
    limiter = RateLimiter(
        window_seconds=60,
        default_max=5,
        write_max=3,
        expensive_max=2,
        clock=clock,
    )

    allowed, retry_after = limiter.check("1.2.3.4", "expensive")
    assert allowed is True
    assert retry_after == 0

    allowed, retry_after = limiter.check("1.2.3.4", "expensive")
    assert allowed is True
    assert retry_after == 0

    # 3rd expensive request exceeds limit of 2
    allowed, retry_after = limiter.check("1.2.3.4", "expensive")
    assert allowed is False
    assert retry_after == 60


def test_rate_limiter_window_resets_after_elapsed():
    clock = _Clock(100.0)
    limiter = RateLimiter(
        window_seconds=30,
        default_max=2,
        write_max=2,
        expensive_max=1,
        clock=clock,
    )

    # First hit allowed
    allowed, _ = limiter.check("10.0.0.1", "expensive")
    assert allowed is True

    # Second hit blocked (limit is 1)
    allowed, retry_after = limiter.check("10.0.0.1", "expensive")
    assert allowed is False
    assert retry_after == 30

    # Advance clock past window
    clock.advance(31.0)

    # New window: allowed again
    allowed, retry_after = limiter.check("10.0.0.1", "expensive")
    assert allowed is True
    assert retry_after == 0


def test_rate_limiter_evicts_oldest_when_cap_exceeded():
    clock = _Clock(50.0)
    limiter = RateLimiter(
        window_seconds=60,
        default_max=1,
        write_max=1,
        expensive_max=1,
        max_tracked_clients=2,
        clock=clock,
    )

    # Add client 1 and client 2
    limiter.check("client-1", "default")
    limiter.check("client-2", "default")

    # Both are at limit
    assert limiter.check("client-1", "default")[0] is False
    assert limiter.check("client-2", "default")[0] is False

    # Add client 3 -> should evict client-1 (least recently updated)
    limiter.check("client-3", "default")

    # Client-1 was evicted, so its next request is treated as a new client (allowed)
    allowed, _ = limiter.check("client-1", "default")
    assert allowed is True


def test_rate_limiter_bucket_matching():
    assert _bucket_for("GET", "/api/v1/scans") == "expensive"
    assert _bucket_for("POST", "/api/v1/inspections") == "expensive"
    assert _bucket_for("GET", "/api/v1/findings/123/explanation") == "expensive"
    assert _bucket_for("POST", "/api/v1/findings/123/migration-assessment") == "expensive"
    assert _bucket_for("POST", "/api/v1/projects") == "write"
    assert _bucket_for("PATCH", "/api/v1/review/items/456") == "write"
    assert _bucket_for("DELETE", "/api/v1/items/456") == "write"
    assert _bucket_for("GET", "/api/v1/projects") == "default"
    assert _bucket_for("GET", "/api/v1/findings") == "default"


# ----------------------------------------------------- RateLimitMiddleware tests ---


@pytest.mark.asyncio
async def test_middleware_allows_and_blocks():
    clock = _Clock(10.0)
    limiter = RateLimiter(
        window_seconds=60,
        default_max=2,
        write_max=2,
        expensive_max=1,
        clock=clock,
    )

    async def simple_app(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"status": "ok"})
        await response(scope, receive, send)

    middleware = RateLimitMiddleware(simple_app, limiter=limiter, trust_proxy_headers=False)

    async def call_app(path: str, method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None):
        messages = []

        async def fake_send(message: dict[str, Any]) -> None:
            messages.append(message)

        async def fake_receive() -> dict[str, Any]:
            return {"type": "http.request"}

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "client": ("192.168.1.10", 12345),
        }
        await middleware(scope, fake_receive, fake_send)
        return messages

    # First request: 200 OK
    msgs1 = await call_app("/api/v1/projects")
    start1 = next(m for m in msgs1 if m["type"] == "http.response.start")
    assert start1["status"] == 200

    # Second request: 200 OK
    msgs2 = await call_app("/api/v1/projects")
    start2 = next(m for m in msgs2 if m["type"] == "http.response.start")
    assert start2["status"] == 200

    # Third request: 429 Too Many Requests
    msgs3 = await call_app("/api/v1/projects")
    start3 = next(m for m in msgs3 if m["type"] == "http.response.start")
    assert start3["status"] == 429

    # Check headers and envelope
    headers_dict = dict(start3["headers"])
    assert b"retry-after" in headers_dict
    assert headers_dict[b"content-type"] == b"application/json"

    body3 = next(m for m in msgs3 if m["type"] == "http.response.body")
    payload = json.loads(body3["body"])
    assert payload["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_middleware_exemptions():
    limiter = RateLimiter(
        window_seconds=60,
        default_max=1,
        write_max=1,
        expensive_max=1,
    )

    async def simple_app(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"status": "healthy"})
        await response(scope, receive, send)

    middleware = RateLimitMiddleware(simple_app, limiter=limiter, trust_proxy_headers=False)

    async def fake_receive() -> dict[str, Any]:
        return {"type": "http.request"}

    for path in ("/health", "/healthz", "/api/v1/health", "/api/v1/health/ready"):
        for _ in range(5):  # Multiple hits well beyond limit of 1
            messages: list[dict[str, Any]] = []

            async def fake_send(m: dict[str, Any], target_list=messages) -> None:
                target_list.append(m)

            scope = {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [],
                "client": ("127.0.0.1", 1234),
            }
            await middleware(scope, fake_receive, fake_send)
            start = next(m for m in messages if m["type"] == "http.response.start")
            assert start["status"] == 200


@pytest.mark.asyncio
async def test_middleware_options_cors_preflight_exempt():
    limiter = RateLimiter(
        window_seconds=60,
        default_max=1,
        write_max=1,
        expensive_max=1,
    )

    async def simple_app(scope: Scope, receive: Receive, send: Send) -> None:
        response = Response(status_code=204)
        await response(scope, receive, send)

    middleware = RateLimitMiddleware(simple_app, limiter=limiter, trust_proxy_headers=False)

    async def fake_receive() -> dict[str, Any]:
        return {"type": "http.request"}

    for _ in range(5):
        messages: list[dict[str, Any]] = []

        async def fake_send(m: dict[str, Any], target_list=messages) -> None:
            target_list.append(m)

        scope = {
            "type": "http",
            "method": "OPTIONS",
            "path": "/api/v1/scans",
            "headers": [],
            "client": ("192.168.1.50", 1234),
        }
        await middleware(scope, fake_receive, fake_send)
        start = next(m for m in messages if m["type"] == "http.response.start")
        assert start["status"] == 204


def test_client_ip_resolution():
    # When trust_proxy_headers is False, socket peer address is used
    scope_direct = {
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18")],
        "client": ("10.0.0.1", 5000),
    }
    assert _client_ip(scope_direct, trust_proxy_headers=False) == "10.0.0.1"

    # When trust_proxy_headers is True, right-most X-Forwarded-For entry is used
    assert _client_ip(scope_direct, trust_proxy_headers=True) == "70.41.3.18"

    # Missing client info falls back to "unknown"
    scope_empty = {"headers": []}
    assert _client_ip(scope_empty, trust_proxy_headers=False) == "unknown"
    assert _client_ip(scope_empty, trust_proxy_headers=True) == "unknown"
