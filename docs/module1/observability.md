# Observability

The API exports bounded-label request latency/count and prediction count metrics. OpenTelemetry activates only when an OTLP endpoint is explicitly configured; JSON request logs contain method, route, status and latency, never raw payloads. Compose runs the API on port 8001 alongside Prometheus, Grafana, Loki/Promtail and Tempo. The Grafana dashboard includes metric, structured-log and trace panels.

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, the API instruments inbound FastAPI requests and outbound HTTPX calls. The KServe entry points use the same setup with service name `cognitive-load-kserve` and add a `cogniflow.model.predict` span. W3C trace context therefore follows this path:

```text
cognitive-load-api server
  -> HTTPX client
    -> cognitive-load-kserve server
      -> cogniflow.model.predict
```

Propagation and backend ingestion are separate gates. A matching trace ID in API and KServe logs proves propagation; a Tempo query returning the complete parent-child span tree proves ingestion. A successful inference while Tempo is unavailable proves telemetry failure isolation. Concurrent requests must retain distinct trace IDs.

Prometheus scraping, Loki ingestion and Grafana datasource access are also separate runtime gates. Verify the API target is `up`, query bounded request/prediction series, query both JSON log streams in Loki, and issue representative Prometheus, Loki and Tempo queries through Grafana. Tempo's Grafana datasource does not implement the generic health endpoint in the pinned version, so use a successful trace query for its health evidence. Evidently runs as a DVC stage and deletes a partial output before propagating rendering errors; its tracked report is `reports/evidently/data_drift.html`.

For final acceptance, record only bounded, non-secret query responses:

```bash
set -lx OTEL_EXPORTER_OTLP_ENDPOINT http://tempo:4317
set -lx OTEL_SERVICE_NAME cognitive-load-api

curl -fsS http://localhost:9090/api/v1/targets
curl -fsS --get --data-urlencode 'query=sum(cognitive_load_api_requests_total)' \
  http://localhost:9090/api/v1/query
curl -fsS --get --data-urlencode 'query={job="cognitive-load-api"}' \
  http://localhost:3100/loki/api/v1/query_range
curl -fsS http://localhost:3200/api/traces/TRACE_ID
```

Capture the Prometheus target, bounded request/prediction series, Grafana
dashboard UID, API trace ID and matching Tempo trace, one sanitized structured
log and matching Loki result. Reject evidence containing request bodies,
authorization headers, API keys or cookies. Record the DVC stage status,
Evidently report SHA-256, reference/current dataset digests and report path.

For local Docker acceptance, keep every component on one isolated network and
give the containers the repository-configured aliases `api`, `kserve`,
`prometheus`, `loki`, and `tempo`. Missing aliases appear as exporter or
datasource DNS failures, not application failures. Loki, Tempo and Prometheus
need writable temporary storage when run with their non-root image users. Do
not weaken those users to solve a local permission error; mount or configure a
bounded writable temporary path instead.

After capturing logs and resource usage, remove only the named acceptance
containers and isolated network created for the run. Never use a system-wide
Docker prune or remove shared observability volumes.

```fish
docker rm -f cogniflow-module1-2f-api cogniflow-module1-2f-kserve cogniflow-module1-2f-prometheus cogniflow-module1-2f-grafana cogniflow-module1-2f-loki cogniflow-module1-2f-promtail cogniflow-module1-2f-tempo
docker network rm cogniflow-module1-2f
docker image rm cogniflow-module1-2f-api:6003162 cogniflow-module1-2f-kserve:6003162
```
