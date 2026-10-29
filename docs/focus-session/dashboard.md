# Local-first focus-session dashboard

PR 7 adds an additive same-origin workspace at `GET /focus`. The legacy `/`
prediction demonstration and its six-feature contract remain unchanged.

## Design and architecture

The dashboard serves one person actively working in a programming or study
session. Its hierarchy is current session controls, a selected confirmed
five-minute window and self-report, then a chronological ledger and technical
metadata. A warm neutral palette, restrained teal action color, system fonts,
thin dividers, and an editorial workspace avoid a generic card-grid dashboard.
The timeline is a list rather than a chart because transitions, corrections,
and missing aggregates are discrete events; a chart would imply continuity the
data does not support.

The implementation reuses the repository's FastAPI static-asset convention:
plain HTML, CSS, and ES modules with JSDoc checked by pinned TypeScript. It adds
no UI framework, state library, external font, CDN, analytics, or telemetry.
Node's built-in test runner covers pure state transformations. FastAPI serves
the page and assets from the same origin, so no CORS exception is needed.

`POST /sessions/{id}/windows/refresh` is the only new API. It materializes full
five-minute windows through server time while an active session continues. The
browser never creates a window ID or treats its presentation timer as
authoritative.

## Authentication and privacy

The local API key is entered after every page load and retained in module memory
only. It is sent only as `X-API-Key`; it is never placed in URLs, storage, logs,
or the frontend bundle. `GET /sessions/auth-check` validates it without exposing
the owner hash. The non-secret last session ID may be retained locally for reload
recovery, but it is accepted only after owner-scoped server readback.
Disconnecting aborts the active request and clears owner-scoped UI state.

The dashboard never requests camera permission. Selecting `behavioral_cv`
records only session intent; the separately launched local edge collector owns
camera consent and lifecycle. The UI displays persisted aggregate availability,
distinguishing no aggregate, explicit unavailable measurement, and recorded CV.
It never renders frames, landmarks, embeddings, keyboard content, titles,
filenames, or URLs.

## Session and effort workflow

1. Enter the configured local API key.
2. Start a programming or study session in behavioral or behavioral+CV mode.
3. Pause/resume/complete only when the returned server state permits it.
4. Review server-confirmed five-minute windows and aggregate availability.
5. Select any eligible window and submit an integer 1–7 self-reported effort
   rating. A correction appends a new label that supersedes the latest label.
6. Load the bounded timeline in pages of at most 50 events.

Pausing discards a trailing partial window. The UI confirms this before the
request and announces it only after the server accepts the transition. Ratings
are never presented as saved until the API confirms them.

There is no approved focus-session model. The normal dashboard does not call
`/v1/focus/predict` and states: “Model-based estimates are not available yet.”
User reports, behavioral observations, CV availability, and model state remain
separate.

## Local startup

```fish
cd /home/pnmynh/code/cogniflow-pr7
uv sync --frozen --all-extras
set -x COGNIFLOW_API_KEY (read -s -P 'Local API key: ')
set -x FOCUS_SESSION_STORE_PATH /home/pnmynh/code/cogniflow-pr7-sessions.sqlite3
uv run uvicorn --app-dir src preprocessing_api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/focus`. Refreshing the page requires re-entering
the key. Stop with `Ctrl+C` and remove only the disposable database you created.

## Tests

```fish
cd frontend/focus-dashboard
npm ci
npm run typecheck
npm run lint
npm test
npm run build

cd ../..
uv run pytest src/tests/test_focus_dashboard.py src/tests/test_focus_sessions_api.py
uv run ruff check src scripts
```

## Limitations and later milestones

- Browser automation and screenshot review require a locally available browser;
  static and API integration tests do not substitute for rendered inspection.
- The dashboard does not start the edge collector, infer missing aggregates, or
  display synthetic predictions.
- PR 8/9 must separately address any notification integration, genuine-model
  empirical validation, trusted approval verification, and cloud qualification.
- Compatibility, production focus-model approval, and GKE qualification remain
  blocked.
