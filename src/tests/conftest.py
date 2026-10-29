"""Pytest configuration and fixtures."""

from pathlib import Path
import asyncio
import sys

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from preprocessing_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_api_key_environment(monkeypatch):
    """Keep developer-shell credentials from changing test route semantics."""

    monkeypatch.delenv("COGNIFLOW_API_KEY", raising=False)
    monkeypatch.delenv("EVENT_API_KEY", raising=False)


@pytest.fixture
def client():
    """Use HTTPX's ASGI transport without TestClient's host-thread portal."""

    class Client:
        def request(self, method, path, **kwargs):
            async def send():
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as session:
                    return await session.request(method, path, **kwargs)

            return asyncio.run(send())

        def get(self, path, **kwargs):
            return self.request("GET", path, **kwargs)

        def post(self, path, **kwargs):
            return self.request("POST", path, **kwargs)

    return Client()

