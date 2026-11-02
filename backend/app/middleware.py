"""Small request-body guard for the JSON API."""

import os

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse


class SecurityHeadersMiddleware:
    """Apply conservative response headers to every API response."""

    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _max_request_bytes() -> int:
    try:
        value = int(os.getenv("MAX_REQUEST_BODY_BYTES", "65536"))
    except ValueError:
        return 65_536
    return value if value > 0 else 65_536


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_bytes: int | None = None):
        self.app = app
        self.max_bytes = max_bytes or _max_request_bytes()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                response = JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length"},
                )
                await response(scope, receive, send)
                return
            if declared_length < 0 or declared_length > self.max_bytes:
                await self._too_large(scope, receive, send)
                return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestTooLarge:
            await self._too_large(scope, receive, send)

    async def _too_large(self, scope, receive, send):
        response = JSONResponse(
            status_code=413,
            content={"detail": "Request body is too large"},
        )
        await response(scope, receive, send)


class _RequestTooLarge(Exception):
    pass
