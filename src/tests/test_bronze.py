"""Bronze partitioning, idempotency and failure tests."""

from io import BytesIO

import pytest

from cogniflow_data.bronze import BronzeRecord, BronzeStore, BronzeUnavailable, KafkaPosition
from cogniflow_data.events import SessionEvent
from tests.test_events import event_body


class ClientError(Exception):
    def __init__(self, status=404):
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status}}


class FakeS3:
    class exceptions:
        ClientError = ClientError

    def __init__(self, fail=False):
        self.objects = {}
        self.fail = fail

    def head_object(self, Bucket, Key):
        if self.fail:
            raise RuntimeError("offline")
        if Key not in self.objects:
            raise ClientError()
        return {"Metadata": self.objects[Key][1]}

    def put_object(self, Bucket, Key, Body, ContentType, Metadata):
        if self.fail:
            raise RuntimeError("offline")
        self.objects[Key] = (Body, Metadata)

    def get_object(self, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key][0])}


def record(event_time="2026-10-23T20:00:00Z"):
    event = SessionEvent.model_validate(event_body(event_time=event_time))
    return BronzeRecord(event, KafkaPosition("session-events", 0, 1))


def test_bronze_round_trip_partition_and_duplicate_safe_write():
    client = FakeS3()
    store = BronzeStore(client, "bronze")
    item = record()
    key = store.write_batch([item])
    assert "schema_version=1.0/event_date=2026-10-23" in key
    assert store.write_batch([item]) == key
    assert store.read_batch(key) == [item]
    assert len(client.objects) == 1


def test_bronze_rejects_mixed_dates_and_empty_batches():
    store = BronzeStore(FakeS3(), "bronze")
    with pytest.raises(ValueError, match="empty"):
        store.write_batch([])
    with pytest.raises(ValueError, match="UTC event date"):
        store.write_batch([record(), record("2026-10-24T00:00:00Z")])


def test_bronze_unavailable_is_explicit():
    with pytest.raises(BronzeUnavailable, match="unavailable"):
        BronzeStore(FakeS3(fail=True), "bronze").write_batch([record()])
