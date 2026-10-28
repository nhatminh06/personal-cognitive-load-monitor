"""Immutable, replayable Bronze event batches on S3-compatible storage."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC
from typing import Any

from cogniflow_data.events import SessionEvent
from cogniflow_contracts import BehavioralActivityEvent


class BronzeUnavailable(RuntimeError):
    """Bronze storage could not confirm a durable write."""


@dataclass(frozen=True)
class KafkaPosition:
    topic: str
    partition: int
    offset: int


@dataclass(frozen=True)
class BronzeRecord:
    event: SessionEvent | BehavioralActivityEvent
    kafka: KafkaPosition

    def as_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.model_dump(mode="json"),
            "kafka": {
                "topic": self.kafka.topic,
                "partition": self.kafka.partition,
                "offset": self.kafka.offset,
            },
        }


class BronzeStore:
    """Write deterministic JSONL batches and verify persisted metadata."""

    def __init__(self, client: Any | None = None, bucket: str | None = None) -> None:
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:9000"),
                aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
                aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
                region_name="us-east-1",
                config=Config(retries={"max_attempts": 3, "mode": "standard"}, s3={"addressing_style": "path"}),
            )
        self._client = client
        self.bucket = bucket or os.getenv("MINIO_BRONZE_BUCKET", "cogniflow-bronze")

    @staticmethod
    def object_key(records: list[BronzeRecord]) -> str:
        if not records:
            raise ValueError("Bronze batch cannot be empty")
        versions = {record.event.schema_version for record in records}
        dates = {record.event.event_time.astimezone(UTC).date().isoformat() for record in records}
        if len(versions) != 1 or len(dates) != 1:
            raise ValueError("Bronze batches must share schema version and UTC event date")
        identity = "\n".join(sorted(str(record.event.event_id) for record in records)).encode()
        digest = hashlib.sha256(identity).hexdigest()
        prefix = (
            "behavioral_activity"
            if isinstance(records[0].event, BehavioralActivityEvent)
            else "session_events"
        )
        if any(isinstance(record.event, BehavioralActivityEvent) != (prefix == "behavioral_activity")
               for record in records):
            raise ValueError("Bronze batches cannot mix event contracts")
        return (
            f"{prefix}/schema_version={versions.pop()}/event_date={dates.pop()}/"
            f"batch={digest}.jsonl"
        )

    def write_batch(self, records: list[BronzeRecord]) -> str:
        key = self.object_key(records)
        body = b"".join(
            json.dumps(record.as_dict(), separators=(",", ":"), sort_keys=True).encode() + b"\n"
            for record in records
        )
        checksum = hashlib.sha256(body).hexdigest()
        try:
            try:
                existing = self._client.head_object(Bucket=self.bucket, Key=key)
                if existing.get("Metadata", {}).get("sha256") != checksum:
                    raise BronzeUnavailable("Existing Bronze key has a different checksum")
                return key
            except self._client.exceptions.ClientError as exc:
                if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                    raise
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="application/x-ndjson",
                Metadata={"sha256": checksum, "record-count": str(len(records))},
            )
            persisted = self._client.head_object(Bucket=self.bucket, Key=key)
            if persisted.get("Metadata", {}).get("sha256") != checksum:
                raise BronzeUnavailable("Bronze checksum metadata verification failed")
        except BronzeUnavailable:
            raise
        except Exception as exc:
            raise BronzeUnavailable("Bronze storage is unavailable") from exc
        return key

    def read_batch(self, key: str) -> list[BronzeRecord]:
        try:
            body = self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            rows = [json.loads(line) for line in body.splitlines() if line]
            return [
                BronzeRecord(
                    event=(
                        BehavioralActivityEvent.model_validate(row["event"])
                        if row["event"].get("event_type") == "behavioral.window"
                        else SessionEvent.model_validate(row["event"])
                    ),
                    kafka=KafkaPosition(**row["kafka"]),
                )
                for row in rows
            ]
        except Exception as exc:
            raise BronzeUnavailable("Bronze object could not be read") from exc
