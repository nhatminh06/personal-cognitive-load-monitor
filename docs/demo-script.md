# Local synthetic demo

This demo exercises the authenticated API with synthetic values. It does not require Kubernetes, containers, a model registry, or cloud access.

1. Install locked dependencies: `uv sync --frozen --all-extras`.
2. Set `COGNIFLOW_API_KEY` to a local nonsecret fixture value and `INFERENCE_MODE=demo_rule`.
3. Start `uv run uvicorn --app-dir src preprocessing_api.main:app --host 127.0.0.1 --port 8000`.
4. Confirm `/health` and `/ready` return successful responses.
5. Send one authenticated `/predict` request using the synthetic payload in the repository README.
6. Show that a missing or incorrect API key returns HTTP 401.
7. Run the focused API, anomaly, and secret-scanner tests; report the observed output rather than a remembered count.

The response label demonstrates deterministic synthetic-rule behavior. It is not a clinical or real-world cognitive-load measurement. Event delivery, when enabled, is best effort and must not be described as exactly once.

Generated notebooks, reports, and screenshots are intentionally absent from the publication candidate. Do not demonstrate GKE, KServe, registry publication, or hosted CI unless those operations are separately authorized and actually performed on the exact candidate revision.
