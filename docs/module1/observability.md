# Observability

The API exports bounded-label request latency/count and prediction count metrics. OpenTelemetry activates only when an OTLP endpoint is explicitly configured; JSON request logs contain method, route, status and latency, never raw payloads. Compose runs the API on port 8001 alongside Prometheus, Grafana, Loki/Promtail and Tempo. The Grafana dashboard includes metric, structured-log and trace panels.

Earlier runtime verification confirmed an `up` Prometheus target with LOW/HIGH prediction series, JSON `/predict` records in Loki, and Tempo trace IDs for `cognitive-load-api`. Grafana health and dashboard provisioning were checked by API. These are historical results, not fresh acceptance for a new run. The current HTTP client is not instrumented, so API-to-KServe trace propagation is not established. Evidently runs as a DVC stage and deletes a partial output before propagating rendering errors; its tracked report is `reports/evidently/data_drift.html`.

For final acceptance, record only bounded, non-secret query responses:

```bash
kubectl -n monitoring get pods,svc
kubectl -n monitoring get --raw '/api/v1/namespaces/monitoring/services/http:prometheus:9090/proxy/api/v1/targets'
kubectl -n monitoring get --raw '/api/v1/namespaces/monitoring/services/http:tempo:3200/proxy/api/search?service.name=cognitive-load-api'
kubectl -n monitoring get --raw '/api/v1/namespaces/monitoring/services/http:loki:3100/proxy/loki/api/v1/query_range?query={app="cognitive-load-api"}'
```

Capture the Prometheus target, bounded request/prediction series, Grafana
dashboard UID, API trace ID and matching Tempo trace, one sanitized structured
log and matching Loki result. Reject evidence containing request bodies,
authorization headers, API keys or cookies. Record the DVC stage status,
Evidently report SHA-256, reference/current dataset digests and report path.
