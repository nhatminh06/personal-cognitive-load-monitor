"""Offline contracts for the single-service MVP deployment."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from preprocessing_api.main import app
from preprocessing_api.security import configured_api_key


def test_secret_file_authentication(tmp_path, monkeypatch):
    secret = tmp_path / "api-key"
    secret.write_text("mvp-secret\n", encoding="utf-8")
    monkeypatch.setenv("COGNIFLOW_API_KEY_FILE", str(secret))
    assert configured_api_key() == "mvp-secret"

    async def send():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get("/sessions/auth-check")
            allowed = await client.get("/sessions/auth-check", headers={"X-API-Key": "mvp-secret"})
            return denied, allowed

    denied, allowed = asyncio.run(send())
    assert denied.status_code == 401
    assert allowed.json() == {"authenticated": True}


def test_mvp_root_redirects_to_the_authenticated_focus_workspace(monkeypatch):
    monkeypatch.setenv("APP_ENV", "educational_demo")

    async def send():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            return await client.get("/")

    response = asyncio.run(send())
    assert response.status_code == 307
    assert response.headers["location"] == "/focus"


def test_conflicting_secret_sources_fail_closed(tmp_path, monkeypatch):
    secret = tmp_path / "api-key"
    secret.write_text("file-secret", encoding="utf-8")
    monkeypatch.setenv("COGNIFLOW_API_KEY", "environment-secret")
    monkeypatch.setenv("COGNIFLOW_API_KEY_FILE", str(secret))
    with pytest.raises(RuntimeError, match="not both"):
        configured_api_key()


def test_mvp_compose_is_single_service_bounded_and_excludes_deferred_components():
    text = Path("compose.mvp.yml").read_text(encoding="utf-8")
    lowered = text.lower()
    assert text.count("  api:\n") == 1
    assert "127.0.0.1:18000:8000" in text
    assert 'restart: "no"' in text
    assert "mem_limit: 768m" in text and "cpus: 1.0" in text
    assert "read_only: true" in text and "no-new-privileges:true" in text
    assert "COGNIFLOW_API_KEY_FILE" in text and "COGNIFLOW_API_KEY:" not in text
    assert all(token not in lowered for token in ("spark", "kfp", "kserve"))


def test_mvp_fixture_is_synthetic_and_matches_prediction_contract():
    import json

    payload = json.loads(Path("examples/mvp/synthetic-estimate.json").read_text(encoding="utf-8"))
    assert payload == {
        "focus_minutes": 90,
        "distraction_minutes": 30,
        "tasks_due": 3,
        "hours_to_deadline": 24,
    }
