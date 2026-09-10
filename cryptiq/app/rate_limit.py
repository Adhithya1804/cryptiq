"""An in-process, per-client rate limiter.

Cryptiq's demo API is unauthenticated and runs on a single instance, so the
realistic abuse is volume: scan flooding, Gemini-call amplification through the
explanation / migration-assessment routes, and cheap-GET floods. This module is
the ceiling on all three. It keeps fixed-window counters in a bounded
``OrderedDict`` -- no Redis, no external store -- which is the right shape for
one backend process behind one nginx.

Design notes
------------
* **Fixed window.** Counts reset every ``window`` seconds. A caller can burst
  up to ~2x the limit across a window boundary; that is an accepted, well
  understood trade for a small, test-deterministic implementation.
* **Client identity.** The socket peer address by default. ``X-Forwarded-For``
  is honoured *only* when ``trust_proxy_headers`` is set, and then the
  right-most entry is used -- that is the address the trusted proxy actually
  saw, so a client that pre-seeds the header cannot dodge the limiter.
* **Bounded memory.** At most ``max_tracked_clients`` (client, bucket) keys are
  retained; the least-recently-seen key is evicted past that.
* **Safe response.** ``429`` with the app's standard error envelope and a
  ``Retry-After`` header. No counts or internal state are disclosed.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

# Request classes, roughly by cost. The path check is a prefix/suffix match on
# the ASGI path so it does not depend on FastAPI's route table.
_EXPENSIVE_EXACT = frozenset({"/api/v1/scans", "/api/v1/inspections"})
_EXPENSIVE_SUFFIXES = ("/explanation", "/migration-assessment")
# Health probes must never be rate limited -- a load balancer or the Docker
# healthcheck hits them continuously.
_EXEMPT_PREFIXES = ("/health", "/healthz", "/api/v1/health")


def _client_ip(scope: Scope, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        for key, value in scope.get("headers", []):
            if key == b"x-forwarded-for":
                parts = [p.strip() for p in value.decode("latin-1").split(",") if p.strip()]
                if parts:
                    # Right-most = the peer the trusted proxy connected from.
                    return parts[-1]
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


def _is_exempt(path: str) -> bool:
    return path.startswith(_EXEMPT_PREFIXES)


def _bucket_for(method: str, path: str) -> str:
    if path in _EXPENSIVE_EXACT or path.endswith(_EXPENSIVE_SUFFIXES):
        return "expensive"
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return "write"
    return "default"


class _Window:
    __slots__ = ("count", "start")

    def __init__(self, start: float) -> None:
        self.start = start
        self.count = 0


class RateLimiter:
    """The counter store. Separated from the middleware so tests can drive it."""

    def __init__(
        self,
        *,
        window_seconds: int,
        default_max: int,
        write_max: int,
        expensive_max: int,
        max_tracked_clients: int = 20_000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._window = max(1, int(window_seconds))
        self._limits = {
            "default": max(1, int(default_max)),
            "write": max(1, int(write_max)),
            "expensive": max(1, int(expensive_max)),
        }
        self._max_clients = max(1, int(max_tracked_clients))
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._windows: OrderedDict[tuple[str, str], _Window] = OrderedDict()

    def limit_for(self, bucket: str) -> int:
        return self._limits.get(bucket, self._limits["default"])

    def check(self, client_ip: str, bucket: str) -> tuple[bool, int]:
        """Register one hit. Return ``(allowed, retry_after_seconds)``.

        Every request is also counted against the client's ``default`` bucket,
        so a flood of cheap GETs is bounded even though each one is cheap.
        """
        now = self._clock()
        with self._lock:
            allowed = True
            retry_after = 0
            for name in {bucket, "default"}:
                key = (client_ip, name)
                win = self._windows.get(key)
                if win is None or (now - win.start) >= self._window:
                    win = _Window(now)
                    self._windows[key] = win
                else:
                    self._windows.move_to_end(key)
                win.count += 1
                if win.count > self._limits[name]:
                    allowed = False
                    retry_after = max(
                        retry_after, math.ceil(self._window - (now - win.start))
                    )
            # Evict least-recently-seen keys past the cap.
            while len(self._windows) > self._max_clients:
                self._windows.popitem(last=False)
            return allowed, max(retry_after, 1) if not allowed else 0


class RateLimitMiddleware:
    """Reject a client that exceeds its window budget with ``429``."""

    def __init__(self, app: ASGIApp, *, limiter: RateLimiter, trust_proxy_headers: bool) -> None:
        self.app = app
        self.limiter = limiter
        self.trust_proxy_headers = trust_proxy_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        # OPTIONS (CORS preflight) and health probes are never limited.
        if method == "OPTIONS" or _is_exempt(path):
            await self.app(scope, receive, send)
            return

        client_ip = _client_ip(scope, trust_proxy_headers=self.trust_proxy_headers)
        bucket = _bucket_for(method, path)
        allowed, retry_after = self.limiter.check(client_ip, bucket)
        if allowed:
            await self.app(scope, receive, send)
            return
        await _send_429(send, retry_after)


_ENVELOPE = json.dumps(
    {
        "error": {
            "code": "RATE_LIMITED",
            "message": "Too many requests. Retry after a short wait.",
        }
    }
).encode("utf-8")


async def _send_429(send: Send, retry_after: int) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_ENVELOPE)).encode("latin-1")),
                (b"retry-after", str(max(1, int(retry_after))).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _ENVELOPE})
