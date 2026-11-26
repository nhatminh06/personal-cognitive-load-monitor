"""Private single-owner focus MVP. No model, telemetry or pipeline imports."""

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from cogniflow_contracts import BehavioralActivityEvent, EffortLabelEvent, SessionLifecycleEvent
from preprocessing_api.schemas import PredictionRequest
from preprocessing_api.service import calculate_cognitive_load
from store import Store

COOKIE = "__Host-cogniflow"
TTL = 8 * 60 * 60
SID = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def store(request):
    return Store(request.scope["env"].DB)


def configured(request):
    env = request.scope["env"]
    credential_hash = getattr(env, "OWNER_CREDENTIAL_SHA256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", credential_hash) or not getattr(env, "OWNER_ID", ""):
        raise HTTPException(503, "Browser authentication is not configured")
    return env


async def limit(binding, key):
    result = await binding.limit({"key": key})
    if not result["success"]:
        raise HTTPException(429, "Too many requests; retry shortly", headers={"Retry-After": "60"})


async def owner(request: Request):
    env = configured(request)
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(401, "Authentication required")
    rows = await store(request).query(
        "SELECT owner_id FROM browser_sessions WHERE token_hash=? AND expires_at>? AND owner_id=?",
        digest(token), int(time.time()), env.OWNER_ID,
    )
    if not rows:
        raise HTTPException(401, "Authentication required")
    await limit(env.API_LIMIT, f"owner:{env.OWNER_ID}")
    return env.OWNER_ID


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=43, max_length=128)


@app.post("/auth/login")
async def login(body: Login, request: Request):
    env = configured(request)
    # Both limits precede any credential comparison or D1 access.
    await limit(env.LOGIN_LIMIT, "login-global")
    await limit(env.LOGIN_LIMIT, "login:" + request.headers.get("cf-connecting-ip", "local"))
    if not hmac.compare_digest(digest(body.credential), env.OWNER_CREDENTIAL_SHA256):
        raise HTTPException(401, "Invalid credential")
    token = secrets.token_urlsafe(32)
    db = store(request)
    statements = [db.statement("DELETE FROM browser_sessions WHERE expires_at<=?", int(time.time()))]
    old = request.cookies.get(COOKIE)
    if old:
        statements.append(db.statement("DELETE FROM browser_sessions WHERE token_hash=?", digest(old)))
    statements.append(db.statement("INSERT INTO browser_sessions VALUES (?,?,?)",
                                   digest(token), env.OWNER_ID, int(time.time()) + TTL))
    await db.batch(statements)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(COOKIE, token, max_age=TTL, secure=True, httponly=True, samesite="strict", path="/")
    return response


@app.post("/auth/logout")
async def logout(request: Request, identity=Depends(owner)):
    await store(request).query("DELETE FROM browser_sessions WHERE token_hash=?", digest(request.cookies[COOKIE]))
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return response


@app.get("/sessions/auth-check")
async def auth_check(identity=Depends(owner)):
    return {"authenticated": True}


async def mutation(operation, event, request, identity, sid=None):
    if sid is not None and sid != event.session_id:
        raise HTTPException(422, "Path and event session IDs must match")
    now = datetime.now(UTC)
    if event.event_time > now:
        raise HTTPException(422, "event_time cannot be in the future")
    event = event.model_copy(update={"ingested_at": now})
    result, created = await store(request).mutate(operation, event, identity)
    code = 201 if created and operation != "transitions" else 200
    return JSONResponse(result, status_code=code)


@app.post("/sessions")
async def create(event: SessionLifecycleEvent, request: Request, identity=Depends(owner)):
    return await mutation("create", event, request, identity)


@app.post("/sessions/{sid}/transitions")
async def transition(sid: SID, event: SessionLifecycleEvent, request: Request, identity=Depends(owner)):
    return await mutation("transitions", event, request, identity, sid)


@app.post("/sessions/{sid}/labels")
async def label(sid: SID, event: EffortLabelEvent, request: Request, identity=Depends(owner)):
    return await mutation("labels", event, request, identity, sid)


@app.post("/sessions/{sid}/activity-windows")
async def activity(sid: SID, event: BehavioralActivityEvent, request: Request, identity=Depends(owner)):
    return await mutation("activity", event, request, identity, sid)


@app.get("/sessions/{sid}")
async def session(sid: SID, request: Request, identity=Depends(owner)):
    return await store(request).session(sid, identity)


@app.post("/sessions/{sid}/windows/refresh")
async def refresh(sid: SID, request: Request, identity=Depends(owner)):
    return await store(request).refresh(sid, identity)


@app.get("/sessions/{sid}/timeline")
async def timeline(sid: SID, request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                   offset: Annotated[int, Query(ge=0)] = 0, identity=Depends(owner)):
    return await store(request).timeline(sid, identity, limit, offset)


@app.post("/predict")
async def predict(body: PredictionRequest, request: Request, identity=Depends(owner)):
    result = {"cognitive_load_level": calculate_cognitive_load(body).value,
              "inference_source": "demo_rule", "model_version": None,
              "feature_as_of": body.feature_as_of.isoformat() if body.feature_as_of else None,
              "is_fallback": False}
    await store(request).query("INSERT INTO estimates VALUES (?,?,?,?)", str(uuid4()), identity,
                               datetime.now(UTC).isoformat(), JSONResponse(result).body.decode())
    return result


@app.get("/estimates")
async def estimates(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                    identity=Depends(owner)):
    import json
    rows = await store(request).query(
        "SELECT estimate_id,created_at,result_json FROM estimates WHERE owner_id=? "
        "ORDER BY created_at DESC LIMIT ?", identity, limit,
    )
    return {"items": [{"estimate_id": r["estimate_id"], "created_at": r["created_at"],
                       **json.loads(r["result_json"])} for r in rows]}


@app.get("/model-info")
async def model_info(identity=Depends(owner)):
    return {"inference_mode": "demo_rule", "model_version": None, "label_provenance": "synthetic_proxy"}


@app.get("/")
async def root():
    return RedirectResponse("/focus", status_code=307)


@app.get("/{path:path}")
async def assets(path: str, request: Request):
    # Explicit allowlist prevents Static Assets fallthrough from masking unknown API routes.
    allowed = {"focus": "index.html", "focus-assets/dashboard.css": "focus-assets/dashboard.css",
               "focus-assets/dashboard.js": "focus-assets/dashboard.js",
               "focus-assets/dashboard-state.js": "focus-assets/dashboard-state.js"}
    if path not in allowed:
        raise HTTPException(404, "Not found")
    response = await request.scope["env"].ASSETS.fetch("https://assets.local/" + allowed[path])
    body = await response.bytes()
    return Response(body, status_code=response.status,
                    media_type=response.headers.get("content-type"))


class Boundary:
    """Bound request bodies, enforce same-origin mutations, sanitize infrastructure failures."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.application(scope, receive, send)
        headers = dict(scope["headers"])
        env = scope["env"]
        security = {
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
            "Strict-Transport-Security": "max-age=31536000",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        }

        async def secure_send(message):
            if message["type"] == "http.response.start":
                current = message.setdefault("headers", [])
                current.extend((k.lower().encode(), v.encode()) for k, v in security.items())
            await send(message)

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secure_send)

        if scope["method"] not in {"GET", "HEAD"}:
            origin = getattr(env, "PUBLIC_ORIGIN", "")
            if (not origin or headers.get(b"origin", b"").decode() != origin
                    or headers.get(b"x-cogniflow-csrf") != b"1"
                    or headers.get(b"sec-fetch-site", b"same-origin") != b"same-origin"):
                return await reject(403, "Same-origin request required")
            if headers.get(b"content-type", b"").split(b";")[0].strip() != b"application/json":
                return await reject(415, "application/json required")
        messages = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 16_384:
                return await reject(413, "Request body is too large")
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def buffered_receive():
            return messages.pop(0) if messages else await receive()

        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await secure_send(message)

        try:
            await self.application(scope, buffered_receive, tracked_send)
        except Exception:
            # Starlette re-raises handled failures after sending the sanitized 503.
            if not started:
                await reject(503, "Service unavailable; retry shortly")


@app.exception_handler(Exception)
async def unavailable(request, exc):
    print("Infrastructure failure:", type(exc).__name__)
    return JSONResponse({"detail": "Focus-session store or service is unavailable; retry shortly"},
                        status_code=503, headers={"Retry-After": "60"})


@app.exception_handler(RequestValidationError)
async def invalid(request, exc):
    return JSONResponse({"detail": "Request does not match the contract"}, status_code=422)


application = Boundary(app)
