"""Focus dashboard asset, accessibility, privacy, and API-boundary tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from preprocessing_api.main import app

STATIC = Path(__file__).parents[1] / "preprocessing_api" / "static" / "focus"


def request(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path, headers=headers)

    return asyncio.run(send())


def test_focus_dashboard_is_additive_same_origin_and_security_header_is_preserved():
    legacy = request("/")
    dashboard = request("/focus")
    css = request("/focus-assets/dashboard.css")
    script = request("/focus-assets/dashboard.js")
    assert legacy.status_code == dashboard.status_code == css.status_code == script.status_code == 200
    assert "CogniFlow prediction demo" in legacy.text
    assert "CogniFlow focus workspace" in dashboard.text
    assert dashboard.headers["x-frame-options"] == "DENY"
    assert "connect-src 'self'" in dashboard.headers["content-security-policy"]


def test_dashboard_auth_check_validates_key_without_exposing_identity(monkeypatch):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "dashboard-secret")
    assert request("/sessions/auth-check").status_code == 401
    response = request("/sessions/auth-check", {"X-API-Key": "dashboard-secret"})
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_dashboard_has_accessible_structure_and_honest_states():
    html = (STATIC / "index.html").read_text()
    assert '<a class="skip-link" href="#workspace">' in html
    assert html.count("<h1") == 2  # one per mutually exclusive credential/app view
    assert 'role="status" aria-live="polite"' in html
    assert 'role="alert" tabindex="-1"' in html
    assert '<fieldset aria-describedby="rating-help"><legend>How much mental effort' in html
    assert html.count('name="effort"') == 7
    assert 'id="effort-window"' in html
    assert 'aria-labelledby="window-label"' in html
    assert 'id="credential-error" class="field-error" role="alert" tabindex="-1"' in html
    assert 'id="session-controls" class="session-controls" role="group"' in html
    assert 'id="confirm-dialog"' in html
    assert "Model-based estimates are not available yet" in html
    assert "This dashboard never requests camera access" in html


def test_dashboard_does_not_request_camera_predict_or_persist_credentials():
    script = (STATIC / "dashboard.js").read_text()
    assert "getUserMedia" not in script
    assert "/v1/focus/predict" not in script
    assert "sessionStorage" not in script and "indexedDB" not in script
    assert "localStorage.setItem(SESSION_STORAGE_KEY" in script
    assert "localStorage.setItem" not in script.replace(
        "localStorage.setItem(SESSION_STORAGE_KEY, sessionId)", ""
    )
    assert "console." not in script
    assert "'X-API-Key': apiKey" in script
    assert "elements.dialog.returnValue = ''" in script
    assert "elements.dialog.addEventListener('keydown'" in script
    assert "Refresh failed—showing the last server-confirmed state." in script


def test_responsive_tokens_touch_targets_and_reduced_motion_are_present():
    css = (STATIC / "dashboard.css").read_text()
    for width in ("899px", "599px", "359px"):
        assert f"max-width: {width}" in css
    assert "min-width: 320px" in css
    assert "min-height: 44px" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "prefers-contrast: more" in css
    assert "overflow-wrap: anywhere" in css
