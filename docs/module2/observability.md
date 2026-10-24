# Observability

`POST /events` exports bounded `cogniflow_events_total{outcome}` metrics and all API routes use Module I structured request logs and trace middleware. Flink exposes Prometheus metrics from its JobManager and TaskManager on port 9249 inside the stable `cogniflow-module2` network. The provisioned `CogniFlow Module II — Streaming and Ingestion` dashboard uses actual ingestion, record-flow, duplicate, stale-write and checkpoint series plus Loki logs.

Runtime verification on 2026-10-24 showed Prometheus `up=1` for API, Flink JobManager and Flink TaskManager, and Grafana returned the provisioned Module II dashboard through its API. The API initially failed because its bind-mounted log directory was root-owned; a one-shot ownership initializer fixed the real defect. Kafka client/operator and Flink flow metrics are genuine exported series.

Bronze, Spark/Delta, dbt/Gold freshness and Airflow remain structured job/task evidence rather than Prometheus series. They are intentionally not represented by invented dashboard data. Adding bounded Pushgateway/OpenTelemetry exporters is a remaining local gap.
