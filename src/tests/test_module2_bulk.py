from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from cogniflow_data.bronze import BronzeStore
from cogniflow_data.bulk import BulkConfig, ingest, reconcile_reports, validate_resources
from cogniflow_data.events import SessionEvent
from cogniflow_data.kafka import KafkaAcknowledgment, KafkaPublisher, PublishError
from scripts.generate_module2_benchmark import Config, generate


class ClientError(Exception):
    def __init__(self, status: int = 404):
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status}}


class S3:
    class exceptions:
        ClientError = ClientError

    def __init__(self, *, fail_put: bool = False, corrupt_read: bool = False):
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.fail_put = fail_put
        self.corrupt_read = corrupt_read

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError()
        body, metadata = self.objects[Key]
        return {"Metadata": metadata, "ContentLength": len(body)}

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
        if self.fail_put:
            raise RuntimeError("storage unavailable")
        self.objects[Key] = (Body, Metadata)

    def get_object(self, *, Bucket, Key):
        body = self.objects[Key][0]
        if self.corrupt_read:
            body += b"tampered"
        return {"Body": BytesIO(body)}


class Publisher:
    def __init__(self, *, fail_calls: int = 0):
        self.calls = 0
        self.events: list[str] = []
        self.next_offset = 0
        self.fail_calls = fail_calls

    def publish_batch(self, events: list[SessionEvent], topic: str = "cogniflow.session-events.v1"):
        self.calls += 1
        self.events.extend(str(event.event_id) for event in events)
        if self.calls <= self.fail_calls:
            raise PublishError("injected outage")
        positions = [
            KafkaAcknowledgment(topic, index % 3, self.next_offset + index)
            for index in range(len(events))
        ]
        self.next_offset += len(events)
        return positions


class Crash(RuntimeError):
    pass


def dataset(path: Path) -> Path:
    source = path / "source"
    generate(
        source,
        Config(12_345, 20_000, 5_000, 0, 42, "2026-01-01T00:00:00+00:00"),
        execute=True,
        allow_over_100gb=False,
        resume=False,
    )
    return source


def run(
    root: Path,
    publisher: Publisher,
    storage: S3,
    *,
    resume: bool = False,
    fault=None,
):
    return ingest(
        root / "source",
        root / "checkpoint.json",
        root / "ingestion.json",
        publisher,
        BronzeStore(storage, "bronze"),
        BulkConfig(batch_records=4, max_source_bytes=20_000, min_free_bytes=0),
        resume=resume,
        allow_over_100gb=False,
        fault=fault,
    )


def test_bulk_ingestion_accounts_for_distinct_stage_bytes_and_offsets(tmp_path: Path) -> None:
    dataset(tmp_path)
    result = run(tmp_path, Publisher(), S3())
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    manifest = json.loads((tmp_path / "source/manifest.json").read_text())

    assert result["status"] == "ingestion_complete"
    assert result["source"] == {"bytes": 12_345, "records": manifest["committed_rows"]}
    assert result["kafka"]["acknowledged_records"] == manifest["committed_rows"]
    assert result["bronze"]["records"] == manifest["committed_rows"]
    assert result["source"]["bytes"] != result["kafka"]["payload_bytes"]
    assert result["bronze"]["bytes"] != result["source"]["bytes"]
    assert checkpoint["stage"] == "complete"
    assert sum(item["count"] for item in result["kafka"]["offset_ranges"].values()) == manifest["committed_rows"]


def test_restart_after_kafka_checkpoint_does_not_republish(tmp_path: Path) -> None:
    dataset(tmp_path)
    publisher = Publisher()

    def crash(stage: str) -> None:
        if stage == "after_kafka_checkpoint":
            raise Crash(stage)

    with pytest.raises(Crash):
        run(tmp_path, publisher, S3(), fault=crash)
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["stage"] == "kafka_acked"
    calls = publisher.calls

    result = run(tmp_path, publisher, S3(), resume=True)
    assert publisher.calls > calls  # later batches publish
    assert result["kafka"]["publish_attempts"] == result["source"]["records"]
    assert publisher.events[:4] == checkpoint["pending"]["event_ids"]
    assert publisher.events.count(checkpoint["pending"]["event_ids"][0]) == 1


def test_publish_and_storage_failures_never_advance_source(tmp_path: Path) -> None:
    dataset(tmp_path)
    publisher = Publisher(fail_calls=1)
    with pytest.raises(PublishError):
        run(tmp_path, publisher, S3())
    failed = json.loads((tmp_path / "checkpoint.json").read_text())
    assert failed["stage"] == "publishing"
    assert failed["byte_offset"] == 0
    assert failed["retry_history"][-1]["error_type"] == "PublishError"

    storage = S3(fail_put=True)
    with pytest.raises(RuntimeError):
        run(tmp_path, publisher, storage, resume=True)
    failed = json.loads((tmp_path / "checkpoint.json").read_text())
    assert failed["stage"] == "kafka_acked"
    assert failed["byte_offset"] == 0

    storage.fail_put = False
    result = run(tmp_path, publisher, storage, resume=True)
    assert result["source"]["records"] == json.loads((tmp_path / "source/manifest.json").read_text())["committed_rows"]
    assert result["kafka"]["publish_attempts"] > result["kafka"]["acknowledged_records"]


def test_corrupt_source_and_bronze_readback_fail_closed(tmp_path: Path) -> None:
    source = dataset(tmp_path)
    first = source / "part-000000.jsonl"
    first.write_bytes(first.read_bytes()[:-1] + b"x")
    with pytest.raises(ValueError, match="integrity"):
        run(tmp_path, Publisher(), S3())

    other = tmp_path / "other"
    dataset(other)
    with pytest.raises(RuntimeError, match="checksum"):
        run(other, Publisher(), S3(corrupt_read=True))
    checkpoint = json.loads((other / "checkpoint.json").read_text())
    assert checkpoint["byte_offset"] == 0


def test_inconsistent_manifest_is_rejected_before_publish(tmp_path: Path) -> None:
    source = dataset(tmp_path)
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["committed_rows"] += 1
    manifest_path.write_text(json.dumps(manifest))
    publisher = Publisher()
    with pytest.raises(ValueError, match="totals"):
        run(tmp_path, publisher, S3())
    assert publisher.calls == 0


def test_interrupted_checkpoint_replace_is_recovered(tmp_path: Path) -> None:
    dataset(tmp_path)
    storage = S3()
    run(tmp_path, Publisher(), storage)
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.replace(tmp_path / "checkpoint.json.tmp")

    result = run(tmp_path, Publisher(), storage, resume=True)
    assert result["status"] == "ingestion_complete"
    assert checkpoint.exists()


def evidence_reports():
    ingestion = {
        "status": "ingestion_complete",
        "source": {"bytes": 100, "records": 4},
        "kafka": {"payload_bytes": 80, "acknowledged_records": 4},
        "bronze": {"bytes": 140, "records": 4},
    }
    spark = {
        "status": "spark_complete",
        "spark_input_bytes": 140,
        "bronze_rows_read": 4,
        "valid_rows": 4,
        "rejected_rows": 0,
        "duplicates_excluded": 1,
        "silver_batch_rows": 3,
        "silver_total_rows": 3,
        "delta_physical_bytes": 200,
    }
    gold = {"status": "gold_complete", "accepted_rows": 3, "gold_physical_bytes": 120}
    return ingestion, spark, gold


def test_reconciliation_preserves_byte_units_and_fails_on_missing_evidence() -> None:
    ingestion, spark, gold = evidence_reports()
    result = reconcile_reports(ingestion, spark, gold)
    assert result["status"] == "reconciled"
    assert len(set(result["bytes_by_stage"].values())) > 1

    with pytest.raises(ValueError, match="missing"):
        reconcile_reports(ingestion, {**spark, "status": "NOT_RUN"}, gold)
    with pytest.raises(ValueError, match="Bronze/Spark"):
        reconcile_reports(ingestion, {**spark, "bronze_rows_read": 3}, gold)
    with pytest.raises(ValueError, match="Silver/Gold"):
        reconcile_reports(ingestion, spark, {**gold, "accepted_rows": 2})


def test_resource_and_kafka_batch_guards() -> None:
    with pytest.raises(RuntimeError, match="6 GiB"):
        validate_resources(Path("."), 1, BulkConfig(min_free_bytes=0), 1)
    with pytest.raises(ValueError, match="empty"):
        KafkaPublisher(object()).publish_batch([])

    class Producer:
        def __init__(self):
            self.pending = []

        def produce(self, topic, key, value, on_delivery):
            index = len(self.pending)
            message = type(
                "Message",
                (),
                {"topic": lambda self: topic, "partition": lambda self: index % 2, "offset": lambda self: index},
            )()
            self.pending.append((on_delivery, message))

        def poll(self, timeout):
            return 0

        def flush(self, timeout):
            for callback, message in self.pending:
                callback(None, message)
            return 0

    source = SessionEvent.model_validate_json(
        b'{"event_id":"00000000-0000-0000-0000-000000000001","schema_version":"1.0",'
        b'"event_type":"session.snapshot","session_id":"s","event_time":"2026-01-01T00:00:00Z",'
        b'"ingested_at":"2026-01-01T00:00:00Z","source":"test","payload":{"focus_minutes":1,'
        b'"distraction_minutes":1,"tasks_due":1,"hours_to_deadline":1,"feature_as_of":null},'
        b'"provenance":{"producer":"test","producer_version":"1.0","label_provenance":"synthetic_proxy"}}'
    )
    positions = KafkaPublisher(Producer()).publish_batch([source, source])
    assert [(position.partition, position.offset) for position in positions] == [(0, 0), (1, 1)]
