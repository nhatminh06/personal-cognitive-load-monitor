import asyncio
import hashlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app import COOKIE, application  # noqa: E402
from test_store import DB  # noqa: E402


class Limiter:
    def __init__(self, success=True):
        self.success = success

    async def limit(self, options):
        return {"success": self.success}


def client(db=None):
    credential = "a" * 43
    env = SimpleNamespace(DB=db or DB(), PUBLIC_ORIGIN="https://testserver", OWNER_ID="owner",
                          OWNER_CREDENTIAL_SHA256=hashlib.sha256(credential.encode()).hexdigest(),
                          API_LIMIT=Limiter(), LOGIN_LIMIT=Limiter())

    async def bound(scope, receive, send):
        scope["env"] = env
        await application(scope, receive, send)

    instance = TestClient(bound, base_url="https://testserver")
    instance.headers.update({"Origin": env.PUBLIC_ORIGIN, "X-CogniFlow-CSRF": "1"})
    return instance, env, credential


def test_cookie_expiry_revocation_owner_and_csrf():
    browser, env, credential = client()
    assert browser.get("/sessions/auth-check").status_code == 401
    assert browser.post("/auth/login", json={"credential": "wrong" * 9}).status_code == 401
    response = browser.post("/auth/login", json={"credential": credential})
    assert response.status_code == 200
    token = browser.cookies[COOKIE]
    assert browser.get("/sessions/auth-check").status_code == 200
    for headers in ({"Origin": "https://evil.invalid"}, {"X-CogniFlow-CSRF": ""}, {"Sec-Fetch-Site": "cross-site"}):
        assert browser.post("/auth/logout", json={}, headers=headers).status_code == 403
    assert browser.get("/sessions/auth-check").status_code == 200
    env.OWNER_ID = "other"
    assert browser.get("/sessions/auth-check").status_code == 401
    env.OWNER_ID = "owner"
    env.DB.conn.execute("UPDATE browser_sessions SET expires_at=?", (int(time.time()) - 1,))
    env.DB.conn.commit()
    assert browser.get("/sessions/auth-check").status_code == 401
    assert browser.post("/auth/login", json={"credential": credential}).status_code == 200
    assert browser.post("/auth/logout", json={}).status_code == 200
    browser.headers["Cookie"] = f"{COOKIE}={token}"
    assert browser.get("/sessions/auth-check").status_code == 401


def test_fail_closed_rate_limits_and_database_errors():
    browser, env, credential = client()
    env.OWNER_CREDENTIAL_SHA256 = ""
    assert browser.post("/auth/login", json={"credential": credential}).status_code == 503
    env.OWNER_CREDENTIAL_SHA256 = hashlib.sha256(credential.encode()).hexdigest()
    env.LOGIN_LIMIT.success = False
    response = browser.post("/auth/login", json={"credential": credential})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    env.LOGIN_LIMIT.success = True

    async def unavailable(statements):
        raise RuntimeError("D1 daily row quota exceeded; sensitive infrastructure details")

    env.DB.batch = unavailable
    response = browser.post("/auth/login", json={"credential": credential})
    assert response.status_code == 503
    assert "quota" not in response.text and "sensitive" not in response.text
    assert response.headers["cache-control"] == "no-store"
    response = browser.post("/auth/login", json={"credential": "private-too-short"})
    assert response.status_code == 422 and "private-too-short" not in response.text


def test_d1_failure_rolls_back_entire_mutation():
    db = DB()
    from store import Store
    repo = Store(db)

    async def check():
        try:
            await repo.batch([repo.statement("INSERT INTO browser_sessions VALUES ('test','owner',1)"),
                              repo.statement("INSERT INTO cas_guard VALUES (0)")])
        except Exception:
            pass
        else:
            raise AssertionError("Expected failed D1 batch")
        assert await repo.query("SELECT * FROM browser_sessions") == []
    asyncio.run(check())
