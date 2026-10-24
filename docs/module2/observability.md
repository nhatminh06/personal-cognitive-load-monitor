# Observability

`POST /events` exports bounded `cogniflow_events_total{outcome}` metrics and all API routes use Module I structured request logs and trace middleware. Flink exposes its actual job state and counters through port 8082 during the streaming profile; Airflow records per-task state in its metadata database.

The existing Module I Prometheus/Grafana/Loki/Tempo stack was not rerun during this Module II pass, and no Module II Grafana dashboard was runtime-verified. Spark/dbt metrics are currently captured as structured job output, not Prometheus series. These are explicit remaining observability gaps.
