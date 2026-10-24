"""Small fail-closed HTTP security controls shared by public API routes."""

from __future__ import annotations

import hmac
import os
from collections.abc import Awaitable, Callable

from fastapi import Header, HTTPException, status

MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", "1048576"))


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Require the single-tenant API key in production; local demos stay frictionless."""

    expected = os.getenv("COGNIFLOW_API_KEY") or os.getenv("EVENT_API_KEY")
    if expected is None:
        if is_production():
            raise HTTPException(status_code=503, detail="API authentication is not configured")
        return
    if not expected.strip():
        raise HTTPException(status_code=503, detail="API authentication is not configured")
    supplied = x_api_key or ""
    if not supplied.strip() or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


class SecurityMiddleware:
    """Enforce bounded HTTP bodies and browser security headers at the ASGI boundary."""

    def __init__(self, app, max_request_bytes: int = MAX_REQUEST_BYTES):
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers", [])).get(b"content-length")
        if length:
            try:
                if int(length) > self.max_request_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send, status.HTTP_400_BAD_REQUEST, b'{"detail":"Invalid Content-Length"}')
                return
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_request_bytes:
                    raise HTTPException(status_code=413, detail="Request body is too large")
            return message

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend([
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"content-security-policy", b"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"),
                ])
            await send(message)

        try:
            await self.app(scope, bounded_receive, secure_send)
        except HTTPException as exc:
            if exc.status_code != 413:
                raise
            await self._reject(secure_send)

    @staticmethod
    async def _reject(
        send: Callable[[dict], Awaitable[None]],
        code: int = status.HTTP_413_CONTENT_TOO_LARGE,
        body: bytes = b'{"detail":"Request body is too large"}',
    ) -> None:
        await send({"type": "http.response.start", "status": code,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
