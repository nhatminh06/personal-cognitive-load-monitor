# Module III Phase 1: historical features

## Implemented scope

Phase 1 connects Delta Silver to the stable Module I six-feature contract. It adds strict temporal contracts, deterministic point-in-time selection, a version-pinned read-only Trino adapter, offline/online parity checks, and a reproducible fixture artifact. It does not add training automation, Kubeflow, KServe, Knative, Argo CD, or a new Spark execution path.

```text
Delta Silver session_features --FOR VERSION AS OF--> validated SilverFeatureEvent
                                                           |
decision_time + availability_time -------------------------+--> HistoricalFeatureRow
separate synthetic labels --label availability cutoff----------> later training join

Flink -> Redis -> OnlineFeatureRecord remains the latest projection, not history.
```

The authoritative source is `s3a://cogniflow-lakehouse/silver/session_features`; dbt Gold is not used for training features.

## Feature and temporal contract

Feature schema `1.0` preserves this exact order and units:

1. `focus_minutes` (minutes)
2. `distraction_minutes` (minutes)
3. `tasks_due` (count)
4. `hours_to_deadline` (hours)
5. `focus_ratio` (ratio)
6. `distraction_ratio` (ratio)

A Silver event is eligible for a decision only when both `event_time <= decision_time` and `ingested_at <= decision_time`. `ingested_at` is the explicit feature availability time. Selection uses the latest event time, then ingestion time, then event ID. Identical deliveries with the same event ID collapse; conflicting duplicates fail closed. All timestamps must be timezone-aware and are normalized to UTC. Schema mismatches, missing values, invalid ranges, nonfinite numbers, and inconsistent ratios are rejected.

Each output records decision/session/event identity, schema and ordered features, event/ingestion/decision/availability timestamps, source and Kafka provenance, the Silver dataset URI, and an explicit Delta version. Labels remain separate. Test labels are marked `synthetic_proxy` and only become joinable at their own availability time; they are not derived from a feature row or presented as independent real-world truth.

## Reproducible fixture pipeline

```fish
uv run dvc repro historical_features
sha256sum data/processed/historical_features.jsonl
cat data/processed/historical_features.manifest.json
```

The manifest records contract/schema versions, feature ordering, source dataset and Delta versions, transformation revision, selection rule, row count, SHA-256, and quality outcome. Generated data and DVC cache stay out of Git.

## Read-only Delta verification

Start only the existing local storage and analytics services; do not start Spark:

```fish
docker compose -f infra/module2/docker-compose.yml --profile lake --profile analytics \
  up -d --wait --no-build seaweedfs minio trino

env PYTHONPATH=src uv run python -c \
  'from cogniflow_data.trino_history import TrinoHistoryReader; r=TrinoHistoryReader(); print(r.snapshot(7))'

docker compose -f infra/module2/docker-compose.yml --profile lake --profile analytics \
  stop trino minio seaweedfs
```

The adapter accepts only `http://127.0.0.1:8081`, reads the Delta `$history` metadata table, and issues `FOR VERSION AS OF <version>`. Trino documents version-based Delta time travel and history metadata in its [Delta Lake connector documentation](https://trino.io/docs/current/connector/delta-lake.html#time-travel-queries).

Verified locally on October 25, 2026: the preserved table exposed Delta versions 0 through 7. A read pinned to version 7 returned one real Silver row, recorded the version 7 `MERGE` metadata at `2026-10-25T04:54:33.693Z`, and passed the strict contract with ordered values `[90, 30, 2, 36.0, 0.75, 0.25]`. This test was read-only; Spark was not started and named volumes were retained.

## Verification

```fish
uv run pytest src/tests/test_historical_features.py src/tests/test_trino_history.py
uv run pytest src/tests --cov=src/preprocessing_api --cov=src/cogniflow_data --cov-fail-under=81
uv run ruff check src scripts jobs dags
uv run mypy --explicit-package-bases --ignore-missing-imports src/preprocessing_api src/cogniflow_data
```

Focused tests cover out-of-order input, identical and conflicting duplicates, equal timestamps, late ingestion, future leakage, UTC normalization, invalid schema/nonfinite values, feature order and precision, deterministic replay, label availability, and the distinction between versioned history and Redis's latest projection. Existing API tests retain missing/stale Redis coverage.

The completed local run passed 11 focused tests and 89 total tests with 88.13% combined coverage. Ruff, MyPy, and DVC status passed; a second DVC reproduction detected no changes.

## Limitations and Phase 2

- The deterministic DVC artifact uses trusted synthetic fixtures; it is not a clinical dataset and cannot establish cognitive-load accuracy.
- Trino is unauthenticated local development infrastructure and must remain loopback-only.
- Delta retention can remove files required by old versions; production retention and immutable training-snapshot policy remain Phase 2 work.
- Current Silver is event history, not an authoritative label store. Phase 2 should perform explicit feature/label joins, train from a pinned manifest, and log dataset checksum, Delta version, code revision, feature schema, and model artifact digest in MLflow.
- SEC-022 remains limited to the existing audited fixed-command Spark development workflow. Phase 1 neither expands that exception nor runs Spark.
