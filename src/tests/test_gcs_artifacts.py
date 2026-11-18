from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cogniflow_data.gcs_artifacts import (
    bind_mlflow_candidate,
    publish_candidate,
    validate_mlflow_candidate,
    verify_candidate,
)


RUN_ID = "a" * 32
REVISION = "b" * 40


class FakeBlob:
    def __init__(self, name: str, store: dict, generation: int | None = None):
        self.name = name
        self.store = store
        self.requested_generation = generation
        self.metadata = None
        self.generation = None
        self.size = None
        self.crc32c = None

    def upload_from_filename(self, filename, *, if_generation_match, checksum):
        assert if_generation_match == 0 and checksum == "auto"
        if self.name in self.store:
            raise RuntimeError("precondition failed")
        data = Path(filename).read_bytes()
        self.store[self.name] = {
            "data": data, "generation": 7, "crc32c": "fixture-crc", "metadata": self.metadata,
        }

    def reload(self):
        item = self.store[self.name]
        if self.requested_generation is not None and item["generation"] != self.requested_generation:
            raise RuntimeError("generation missing")
        self.generation = item["generation"]
        self.size = len(item["data"])
        self.crc32c = item["crc32c"]
        self.metadata = item["metadata"]

    def download_to_filename(self, filename, *, if_generation_match, checksum):
        assert if_generation_match == self.store[self.name]["generation"] and checksum == "auto"
        Path(filename).write_bytes(self.store[self.name]["data"])


class FakeStorage:
    def __init__(self):
        self.store = {}

    def bucket(self, _name):
        return SimpleNamespace(
            blob=lambda name, generation=None: FakeBlob(name, self.store, generation)
        )


class FakeMlflow:
    def __init__(self):
        self.tags = {"approval_status": "candidate"}
        self.run_tags = {}

    def get_model_version(self, _name, _version):
        return SimpleNamespace(run_id=RUN_ID, tags=self.tags.copy())

    def set_model_version_tag(self, _name, _version, key, value):
        self.tags[key] = value

    def set_tag(self, run_id, key, value):
        assert run_id == RUN_ID
        self.run_tags[key] = value


def test_candidate_round_trip_records_generation_and_binds_mlflow(tmp_path: Path) -> None:
    artifact = tmp_path / "model.skops"
    artifact.write_bytes(b"exact model package")
    storage = FakeStorage()

    identity = publish_candidate(
        storage,
        bucket_name="cogniflow-models",
        artifact=artifact,
        model_name="cognitive-load-classifier",
        model_version="2",
        mlflow_run_id=RUN_ID,
        source_revision=REVISION,
    )
    assert identity.generation == 7
    assert identity.uri.endswith("#7")
    assert identity.object_name.startswith("candidates/cognitive-load-classifier/2/")
    client = FakeMlflow()
    bind_mlflow_candidate(client, identity)
    assert client.tags["gcs_artifact_sha256"] == identity.sha256
    assert client.run_tags["gcs_artifact_generation"] == "7"


def test_candidate_verification_rejects_corruption_and_identity_drift(tmp_path: Path) -> None:
    artifact = tmp_path / "model.skops"
    artifact.write_bytes(b"original")
    storage = FakeStorage()
    identity = publish_candidate(
        storage, bucket_name="bucket", artifact=artifact, model_name="model", model_version="1",
        mlflow_run_id=RUN_ID, source_revision=REVISION,
    )

    storage.store[identity.object_name]["data"] = b"corrupt!"
    with pytest.raises(RuntimeError, match="checksum"):
        verify_candidate(storage, identity)
    with pytest.raises(RuntimeError, match="generation"):
        verify_candidate(storage, replace(identity, generation=8))


def test_candidate_publication_is_create_only_and_candidate_only(tmp_path: Path) -> None:
    artifact = tmp_path / "model.skops"
    artifact.write_bytes(b"same")
    storage = FakeStorage()
    arguments = dict(
        bucket_name="bucket", artifact=artifact, model_name="model", model_version="1",
        mlflow_run_id=RUN_ID, source_revision=REVISION,
    )
    publish_candidate(storage, **arguments)
    with pytest.raises(RuntimeError, match="precondition"):
        publish_candidate(storage, **arguments)

    client = FakeMlflow()
    client.tags["approval_status"] = "approved"
    identity = publish_candidate(FakeStorage(), **arguments)
    with pytest.raises(ValueError, match="candidate"):
        bind_mlflow_candidate(client, identity)
    with pytest.raises(ValueError, match="candidate"):
        validate_mlflow_candidate(client, "model", "1", RUN_ID)
