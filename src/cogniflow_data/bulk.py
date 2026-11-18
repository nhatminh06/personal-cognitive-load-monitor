"""Bounded, restart-safe source → Kafka → Bronze ingestion and reconciliation."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC
from pathlib import Path
from typing import Any, Protocol, cast

from cogniflow_data.bronze import BronzeRecord, BronzeStore, KafkaPosition
from cogniflow_data.events import SESSION_TOPIC, SessionEvent
from cogniflow_data.kafka import KafkaAcknowledgment

OVER_100_GB = 100_000_000_000
Fault = Callable[[str], None]


class BatchPublisher(Protocol):
    def publish_batch(
        self, events: list[SessionEvent], topic: str = SESSION_TOPIC
    ) -> list[KafkaAcknowledgment]: ...


@dataclass(frozen=True)
class BulkConfig:
    batch_records: int = 5_000
    max_source_bytes: int = 110_000_000_000
    min_free_bytes: int = 20_000_000_000

    def validate(self) -> None:
        if not 1 <= self.batch_records <= 10_000:
            raise ValueError("batch-records must be between 1 and 10000")
        if self.max_source_bytes <= 0 or self.min_free_bytes < 0:
            raise ValueError("byte limits must be non-negative and max-source-bytes positive")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
        _sync_directory(path.parent)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _sync_directory(path.parent)


@contextmanager
def _lock(path: Path):
    lock = path.with_suffix(path.suffix + ".lock")
    descriptor = lock.open("a+b")
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("another bulk ingestion owns this checkpoint") from error
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        descriptor.close()


def _manifest(dataset: Path, config: BulkConfig, allow_over_100gb: bool) -> tuple[dict[str, Any], str]:
    path = dataset / "manifest.json"
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("source manifest is missing or unreadable") from error
    if manifest.get("schema_version") != "2.0" or not isinstance(manifest.get("partitions"), list):
        raise ValueError("source manifest contract is invalid")
    committed = manifest.get("committed_bytes")
    rows = manifest.get("committed_rows")
    if not isinstance(committed, int) or not isinstance(rows, int) or committed <= 0 or rows <= 0:
        raise ValueError("source manifest counters are invalid")
    if committed > config.max_source_bytes:
        raise ValueError("source exceeds max-source-bytes")
    if committed > OVER_100_GB and not allow_over_100gb:
        raise ValueError("sources over 100 GB require --allow-over-100gb")
    expected_index = 0
    partition_bytes = 0
    partition_rows = 0
    for number, item in enumerate(manifest["partitions"]):
        if (
            not isinstance(item, dict)
            or item.get("file") != f"part-{number:06d}.jsonl"
            or item.get("start_index") != expected_index
            or not isinstance(item.get("bytes"), int)
            or not isinstance(item.get("rows"), int)
            or item["bytes"] <= 0
            or item["rows"] <= 0
            or item.get("next_index") != expected_index + item["rows"]
        ):
            raise ValueError("source manifest partition sequence is invalid")
        expected_index = item["next_index"]
        partition_bytes += item["bytes"]
        partition_rows += item["rows"]
    if partition_bytes != committed or partition_rows != rows or manifest.get("next_index") != rows:
        raise ValueError("source manifest totals are inconsistent")
    return manifest, _sha256(path)


def _verify_partition(dataset: Path, item: dict[str, Any]) -> Path:
    allowed = {"file", "bytes", "rows", "start_index", "next_index", "sha256", "event_ids_sha256"}
    if set(item) != allowed:
        raise ValueError("partition metadata contract is invalid")
    path = dataset / cast(str, item["file"])
    if not path.is_file() or path.stat().st_size != item["bytes"] or _sha256(path) != item["sha256"]:
        raise ValueError(f"source partition integrity failed: {path.name}")
    return path


def _read_batch(
    path: Path, offset: int, row: int, limit: int, end_offset: int | None = None
) -> tuple[list[SessionEvent], int, int, int, str]:
    events: list[SessionEvent] = []
    source_bytes = 0
    digest = hashlib.sha256()
    event_date = None
    with path.open("rb") as stream:
        stream.seek(offset)
        while len(events) < limit and (end_offset is None or stream.tell() < end_offset):
            start = stream.tell()
            line = stream.readline()
            if not line:
                break
            if end_offset is not None and stream.tell() > end_offset:
                raise ValueError("checkpoint batch boundary is invalid")
            try:
                event = SessionEvent.model_validate_json(line)
            except Exception as error:
                raise ValueError(f"invalid source event at {path.name}:{row + len(events)}") from error
            current_date = event.event_time.astimezone(UTC).date()
            if event_date is not None and current_date != event_date:
                stream.seek(start)
                break
            event_date = current_date
            events.append(event)
            source_bytes += len(line)
            digest.update(line)
        next_offset = stream.tell()
    if end_offset is not None and next_offset != end_offset:
        raise ValueError("checkpoint batch could not be reconstructed")
    return events, next_offset, row + len(events), source_bytes, digest.hexdigest()


def _initial_checkpoint(manifest_sha256: str, config: BulkConfig) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "manifest_sha256": manifest_sha256,
        "config": asdict(config),
        "partition_index": 0,
        "byte_offset": 0,
        "row_index": 0,
        "stage": "ready",
        "pending": None,
        "totals": {
            "source_bytes": 0,
            "source_records": 0,
            "kafka_payload_bytes": 0,
            "kafka_acknowledged_records": 0,
            "kafka_publish_attempts": 0,
            "bronze_bytes": 0,
            "bronze_records": 0,
            "bronze_objects": 0,
        },
        "offset_ranges": {},
        "bronze_chain_sha256": "0" * 64,
        "retry_history": [],
    }


def _load_checkpoint(path: Path, manifest_sha256: str, config: BulkConfig, resume: bool) -> dict[str, Any]:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        if path.exists():
            temporary.unlink()
            _sync_directory(path.parent)
        else:
            try:
                json.loads(temporary.read_text())
            except json.JSONDecodeError as error:
                raise ValueError("interrupted checkpoint is unreadable") from error
            os.replace(temporary, path)
            _sync_directory(path.parent)
    if not path.exists():
        if resume:
            raise ValueError("resume requires an existing checkpoint")
        checkpoint = _initial_checkpoint(manifest_sha256, config)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(path, checkpoint)
        return checkpoint
    if not resume:
        raise ValueError("checkpoint already exists; use --resume")
    try:
        checkpoint = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError("checkpoint is unreadable") from error
    if (
        checkpoint.get("schema_version") != "1.0"
        or checkpoint.get("manifest_sha256") != manifest_sha256
        or checkpoint.get("config") != asdict(config)
    ):
        raise ValueError("checkpoint identity does not match source and configuration")
    return checkpoint


def _positions(raw: list[dict[str, Any]]) -> list[KafkaAcknowledgment]:
    return [KafkaAcknowledgment(str(item["topic"]), int(item["partition"]), int(item["offset"])) for item in raw]


def _record_failure(path: Path, checkpoint: dict[str, Any], error: Exception) -> None:
    history = cast(list[dict[str, Any]], checkpoint["retry_history"])
    history.append(
        {
            "partition_index": checkpoint["partition_index"],
            "byte_offset": checkpoint["byte_offset"],
            "stage": checkpoint["stage"],
            "error_type": type(error).__name__,
            "timestamp": time.time(),
        }
    )
    checkpoint["retry_history"] = history[-100:]
    _write_json(path, checkpoint)


def _commit_pending(
    dataset: Path,
    partitions: list[dict[str, Any]],
    checkpoint_path: Path,
    checkpoint: dict[str, Any],
    bronze: BronzeStore,
    fault: Fault | None,
) -> None:
    pending = cast(dict[str, Any], checkpoint["pending"])
    partition = partitions[cast(int, checkpoint["partition_index"])]
    path = dataset / cast(str, partition["file"])
    events, end_offset, end_row, source_bytes, source_sha = _read_batch(
        path,
        cast(int, checkpoint["byte_offset"]),
        cast(int, checkpoint["row_index"]),
        len(cast(list[object], pending["positions"])),
        cast(int, pending["end_offset"]),
    )
    if (
        end_row != pending["end_row"]
        or source_bytes != pending["source_bytes"]
        or source_sha != pending["source_sha256"]
        or [str(event.event_id) for event in events] != pending["event_ids"]
    ):
        raise ValueError("acknowledged source batch no longer matches checkpoint")
    acknowledgments = _positions(cast(list[dict[str, Any]], pending["positions"]))
    records = [
        BronzeRecord(event, KafkaPosition(ack.topic, ack.partition, ack.offset))
        for event, ack in zip(events, acknowledgments, strict=True)
    ]
    evidence = bronze.write_batch_verified(records)
    if fault:
        fault("after_bronze_verified")
    totals = cast(dict[str, int], checkpoint["totals"])
    totals["source_bytes"] += source_bytes
    totals["source_records"] += len(events)
    totals["kafka_payload_bytes"] += cast(int, pending["kafka_payload_bytes"])
    totals["kafka_acknowledged_records"] += len(events)
    totals["bronze_bytes"] += evidence.bytes
    totals["bronze_records"] += evidence.records
    totals["bronze_objects"] += 1
    ranges = cast(dict[str, dict[str, int]], checkpoint["offset_ranges"])
    for ack in acknowledgments:
        key = f"{ack.topic}:{ack.partition}"
        current = ranges.setdefault(key, {"first": ack.offset, "last": ack.offset, "count": 0})
        current["first"] = min(current["first"], ack.offset)
        current["last"] = max(current["last"], ack.offset)
        current["count"] += 1
    chain = hashlib.sha256(
        (cast(str, checkpoint["bronze_chain_sha256"]) + evidence.key + evidence.sha256).encode()
    ).hexdigest()
    checkpoint.update(
        {
            "byte_offset": end_offset,
            "row_index": end_row,
            "stage": "ready",
            "pending": None,
            "bronze_chain_sha256": chain,
        }
    )
    _write_json(checkpoint_path, checkpoint)


def ingest(
    dataset: Path,
    checkpoint_path: Path,
    report_path: Path,
    publisher: BatchPublisher,
    bronze: BronzeStore,
    config: BulkConfig,
    *,
    resume: bool,
    allow_over_100gb: bool,
    fault: Fault | None = None,
) -> dict[str, Any]:
    """Ingest verified partitions without holding more than one batch in memory."""

    config.validate()
    manifest, manifest_sha256 = _manifest(dataset, config, allow_over_100gb)
    partitions = cast(list[dict[str, Any]], manifest["partitions"])
    started = time.monotonic()
    with _lock(checkpoint_path):
        checkpoint = _load_checkpoint(checkpoint_path, manifest_sha256, config, resume)
        try:
            if checkpoint["stage"] == "kafka_acked":
                _commit_pending(dataset, partitions, checkpoint_path, checkpoint, bronze, fault)
            elif checkpoint["stage"] == "publishing":
                checkpoint.update({"stage": "ready", "pending": None})
                _write_json(checkpoint_path, checkpoint)
            while cast(int, checkpoint["partition_index"]) < len(partitions):
                item = partitions[cast(int, checkpoint["partition_index"])]
                path = _verify_partition(dataset, item)
                if cast(int, checkpoint["byte_offset"]) == cast(int, item["bytes"]):
                    if cast(int, checkpoint["row_index"]) != cast(int, item["rows"]):
                        raise ValueError("partition row reconciliation failed")
                    checkpoint.update(
                        {
                            "partition_index": cast(int, checkpoint["partition_index"]) + 1,
                            "byte_offset": 0,
                            "row_index": 0,
                        }
                    )
                    _write_json(checkpoint_path, checkpoint)
                    continue
                events, end_offset, end_row, source_bytes, source_sha = _read_batch(
                    path,
                    cast(int, checkpoint["byte_offset"]),
                    cast(int, checkpoint["row_index"]),
                    config.batch_records,
                )
                if not events:
                    raise ValueError("partition ended before manifest counters")
                totals = cast(dict[str, int], checkpoint["totals"])
                totals["kafka_publish_attempts"] += len(events)
                pending = {
                    "end_offset": end_offset,
                    "end_row": end_row,
                    "source_bytes": source_bytes,
                    "source_sha256": source_sha,
                    "event_ids": [str(event.event_id) for event in events],
                    "kafka_payload_bytes": sum(len(event.wire_bytes()) for event in events),
                }
                checkpoint.update({"stage": "publishing", "pending": pending})
                _write_json(checkpoint_path, checkpoint)
                acknowledgments = publisher.publish_batch(events)
                if len(acknowledgments) != len(events):
                    raise RuntimeError("Kafka acknowledgment count mismatch")
                checkpoint.update(
                    {
                        "stage": "kafka_acked",
                        "pending": {
                            **pending,
                            "positions": [asdict(ack) for ack in acknowledgments],
                        },
                    }
                )
                _write_json(checkpoint_path, checkpoint)
                if fault:
                    fault("after_kafka_checkpoint")
                _commit_pending(dataset, partitions, checkpoint_path, checkpoint, bronze, fault)
            totals = cast(dict[str, int], checkpoint["totals"])
            if totals["source_bytes"] != manifest["committed_bytes"] or totals["source_records"] != manifest["committed_rows"]:
                raise ValueError("final source reconciliation failed")
            if totals["source_records"] != totals["kafka_acknowledged_records"] or totals["source_records"] != totals["bronze_records"]:
                raise ValueError("final ingestion stage reconciliation failed")
            checkpoint["stage"] = "complete"
            _write_json(checkpoint_path, checkpoint)
        except Exception as error:
            _record_failure(checkpoint_path, checkpoint, error)
            raise
    elapsed = time.monotonic() - started
    report = {
        "schema_version": "1.0",
        "status": "ingestion_complete",
        "manifest_sha256": manifest_sha256,
        "source": {"bytes": totals["source_bytes"], "records": totals["source_records"]},
        "kafka": {
            "payload_bytes": totals["kafka_payload_bytes"],
            "acknowledged_records": totals["kafka_acknowledged_records"],
            "publish_attempts": totals["kafka_publish_attempts"],
            "offset_ranges": checkpoint["offset_ranges"],
        },
        "bronze": {
            "bytes": totals["bronze_bytes"],
            "records": totals["bronze_records"],
            "objects": totals["bronze_objects"],
            "chain_sha256": checkpoint["bronze_chain_sha256"],
        },
        "retry_history": checkpoint["retry_history"],
        "elapsed_seconds": elapsed,
        "throughput_source_bytes_per_second": totals["source_bytes"] / elapsed if elapsed else 0,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(report_path, report)
    return report


def validate_resources(dataset: Path, manifest_bytes: int, config: BulkConfig, available_memory: int) -> None:
    if available_memory < 6 * 1024**3:
        raise RuntimeError("at least 6 GiB available RAM is required")
    if shutil.disk_usage(dataset).free < config.min_free_bytes:
        raise RuntimeError("minimum free disk reserve is unavailable")
    if manifest_bytes > config.max_source_bytes:
        raise RuntimeError("source exceeds configured hard ceiling")


def reconcile_reports(
    ingestion: dict[str, Any], spark: dict[str, Any], gold: dict[str, Any]
) -> dict[str, Any]:
    """Validate stage-specific counts without equating unlike byte representations."""

    if ingestion.get("status") != "ingestion_complete" or spark.get("status") != "spark_complete" or gold.get("status") != "gold_complete":
        raise ValueError("required processing evidence is missing")
    source_records = ingestion["source"]["records"]
    if not (
        source_records == ingestion["kafka"]["acknowledged_records"]
        == ingestion["bronze"]["records"]
    ):
        raise ValueError("source/Kafka/Bronze record reconciliation failed")
    if spark["bronze_rows_read"] != ingestion["bronze"]["records"]:
        raise ValueError("Bronze/Spark input reconciliation failed")
    if spark["bronze_rows_read"] != spark["valid_rows"] + spark["rejected_rows"]:
        raise ValueError("Spark validation accounting failed")
    if spark["silver_batch_rows"] != spark["valid_rows"] - spark["duplicates_excluded"]:
        raise ValueError("Silver deduplication accounting failed")
    if gold["accepted_rows"] != spark["silver_total_rows"]:
        raise ValueError("Silver/Gold accepted-row reconciliation failed")
    byte_units = {
        "source_file_bytes": ingestion["source"]["bytes"],
        "kafka_payload_bytes": ingestion["kafka"]["payload_bytes"],
        "bronze_object_bytes": ingestion["bronze"]["bytes"],
        "spark_input_bytes": spark["spark_input_bytes"],
        "delta_physical_bytes": spark["delta_physical_bytes"],
        "gold_physical_bytes": gold["gold_physical_bytes"],
    }
    if any(not isinstance(value, int) or value < 0 for value in byte_units.values()):
        raise ValueError("stage byte accounting is invalid")
    return {
        "schema_version": "1.0",
        "status": "reconciled",
        "records": {
            "source": source_records,
            "kafka_acknowledged": ingestion["kafka"]["acknowledged_records"],
            "bronze": ingestion["bronze"]["records"],
            "spark_read": spark["bronze_rows_read"],
            "spark_rejected": spark["rejected_rows"],
            "duplicates_excluded": spark["duplicates_excluded"],
            "silver_total": spark["silver_total_rows"],
            "gold_accepted": gold["accepted_rows"],
        },
        "bytes_by_stage": byte_units,
        "rules": [
            "source records equal logical Kafka acknowledgments and verified Bronze records",
            "Spark valid plus rejected rows equal Bronze rows read",
            "Silver batch rows equal valid rows minus duplicate event IDs",
            "Gold accepted rows equal the complete Silver snapshot",
            "stage byte units are recorded independently and are not required to be equal",
        ],
    }
