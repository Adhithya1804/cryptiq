"""ASGI middleware kept deliberately small.

:class:`BodySizeLimitMiddleware` caps the request body an unauthenticated
caller can push at the demo endpoint. nginx enforces the same ceiling at the
edge (``client_max_body_size``); this in-process copy means the limit holds
even when the app is reached directly (CLI, a curl against the published port,
a future front door).
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ENVELOPE = {
    "error": {
        "code": "REQUEST_TOO_LARGE",
        "message": "Request body exceeds the maximum allowed size.",
    }
}
_BODY = json.dumps(_ENVELOPE).encode("utf-8")


class BodySizeLimitMiddleware:
    """Reject an HTTP request whose body exceeds ``max_bytes`` with ``413``.

    A declared ``Content-Length`` over the limit is refused before the body is
    read. A chunked or understated body is refused as soon as the running byte
    total crosses the limit: the wrapped app is handed an ``http.disconnect``
    so it stops, and the middleware writes the ``413`` itself.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await _send_413(send)
            return

        state = {"received": 0, "over": False, "started": False}
        limit = self.max_bytes

        async def limited_receive() -> Message:
            if state["over"]:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                state["received"] += len(message.get("body", b""))
                if state["received"] > limit:
                    state["over"] = True
                    message["more_body"] = False
                    message["body"] = b""
            return message

        async def guarded_send(message: Message) -> None:
            if state["over"]:
                # The body overran; suppress whatever the app tries to emit and
                # let the middleware send the 413 once the app returns.
                return
            if message["type"] == "http.response.start":
                state["started"] = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)

        if state["over"] and not state["started"]:
            await _send_413(send)


def _declared_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key == b"content-length":
            try:
                return int(value.decode("latin-1"))
            except ValueError:
                return None
    return None


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_BODY)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _BODY})
