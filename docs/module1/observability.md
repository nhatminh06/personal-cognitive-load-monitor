# Observability

The API exports bounded-label request latency/count and prediction count metrics. OpenTelemetry activates only when an OTLP endpoint is explicitly configured; JSON request logs contain method, route, status and latency, never raw payloads. Compose runs the API on port 8001 alongside Prometheus, Grafana, Loki/Promtail and Tempo. The Grafana dashboard includes metric, structured-log and trace panels.

Runtime verification confirmed an `up` Prometheus target with LOW/HIGH prediction series, JSON `/predict` records in Loki, and Tempo trace IDs for `cognitive-load-api`. Grafana health and dashboard provisioning were checked by API. Services were then stopped. Evidently runs as a DVC stage and deletes a partial output before propagating rendering errors; its verified report is `reports/evidently/data_drift.html`.
