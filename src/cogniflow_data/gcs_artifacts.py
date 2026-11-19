"""Immutable GCS model-artifact publication and independent verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re
import tempfile
from typing import Any


SHA256_RE = re.compile(r"[0-9a-f]{64}")
NAME_RE = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?")
RUN_RE = re.compile(r"[0-9a-f]{32}")
VERSION_RE = re.compile(r"[1-9][0-9]*")


@dataclass(frozen=True)
class GCSArtifactIdentity:
    bucket: str
    object_name: str
    generation: int
    size: int
    sha256: str
    crc32c: str
    model_name: str
    model_version: str
    mlflow_run_id: str
    source_revision: str
    approval_status: str = "candidate"

    @property
    def uri(self) -> str:
        return f"gs://{self.bucket}/{self.object_name}#{self.generation}"

    def to_dict(self) -> dict[str, str | int]:
        return {**asdict(self), "uri": self.uri}


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def immutable_object_name(
    model_name: str, model_version: str, mlflow_run_id: str, digest: str
) -> str:
    if not NAME_RE.fullmatch(model_name):
        raise ValueError("model_name must be a safe lowercase artifact path segment")
    if not VERSION_RE.fullmatch(model_version):
        raise ValueError("model_version must be a positive integer")
    if not RUN_RE.fullmatch(mlflow_run_id):
        raise ValueError("mlflow_run_id must be 32 lowercase hexadecimal characters")
    if not SHA256_RE.fullmatch(digest):
        raise ValueError("artifact digest must be a lowercase SHA-256")
    return f"candidates/{model_name}/{model_version}/{mlflow_run_id}/{digest}/model.skops"


def publish_candidate(
    client: Any,
    *,
    bucket_name: str,
    artifact: Path,
    model_name: str,
    model_version: str,
    mlflow_run_id: str,
    source_revision: str,
) -> GCSArtifactIdentity:
    """Create an immutable candidate object and verify it through an exact generation."""
    if not artifact.is_file() or artifact.is_symlink() or artifact.suffix != ".skops":
        raise ValueError("artifact must be a regular .skops file")
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("source_revision must be a full Git SHA")
    digest = file_sha256(artifact)
    object_name = immutable_object_name(model_name, model_version, mlflow_run_id, digest)
    blob = client.bucket(bucket_name).blob(object_name)
    blob.metadata = {
        "sha256": digest,
        "approval_status": "candidate",
        "model_name": model_name,
        "model_version": model_version,
        "mlflow_run_id": mlflow_run_id,
        "source_revision": source_revision,
    }
    blob.upload_from_filename(str(artifact), if_generation_match=0, checksum="auto")
    blob.reload()
    if blob.generation is None or blob.size is None or not blob.crc32c:
        raise RuntimeError("GCS did not return a complete immutable object identity")
    identity = GCSArtifactIdentity(
        bucket=bucket_name,
        object_name=object_name,
        generation=int(blob.generation),
        size=int(blob.size),
        sha256=digest,
        crc32c=str(blob.crc32c),
        model_name=model_name,
        model_version=model_version,
        mlflow_run_id=mlflow_run_id,
        source_revision=source_revision,
    )
    verify_candidate(client, identity)
    return identity


def verify_candidate(client: Any, identity: GCSArtifactIdentity) -> None:
    """Download the recorded object generation and reject any identity or byte drift."""
    blob = client.bucket(identity.bucket).blob(
        identity.object_name, generation=identity.generation
    )
    blob.reload()
    expected_metadata = {
        "sha256": identity.sha256,
        "approval_status": "candidate",
        "model_name": identity.model_name,
        "model_version": identity.model_version,
        "mlflow_run_id": identity.mlflow_run_id,
        "source_revision": identity.source_revision,
    }
    if (
        int(blob.generation or 0) != identity.generation
        or int(blob.size or -1) != identity.size
        or str(blob.crc32c or "") != identity.crc32c
        or blob.metadata != expected_metadata
    ):
        raise RuntimeError("GCS candidate object identity changed or is incomplete")
    with tempfile.TemporaryDirectory(prefix="cogniflow-gcs-verify-") as directory:
        destination = Path(directory) / "model.skops"
        blob.download_to_filename(
            str(destination), if_generation_match=identity.generation, checksum="auto"
        )
        if destination.stat().st_size != identity.size or file_sha256(destination) != identity.sha256:
            raise RuntimeError("GCS candidate artifact checksum verification failed")


def validate_mlflow_candidate(
    client: Any, model_name: str, model_version: str, mlflow_run_id: str
) -> None:
    version = client.get_model_version(model_name, model_version)
    if version.run_id != mlflow_run_id:
        raise ValueError("MLflow model version does not belong to the recorded run")
    if version.tags.get("approval_status") != "candidate":
        raise ValueError("only an existing candidate model version may be bound")


def bind_mlflow_candidate(client: Any, identity: GCSArtifactIdentity) -> None:
    """Bind a verified GCS generation to its existing candidate run and model version."""
    validate_mlflow_candidate(
        client, identity.model_name, identity.model_version, identity.mlflow_run_id
    )
    tags = {
        "gcs_artifact_uri": identity.uri,
        "gcs_artifact_generation": str(identity.generation),
        "gcs_artifact_sha256": identity.sha256,
        "gcs_artifact_crc32c": identity.crc32c,
    }
    for key, value in tags.items():
        client.set_model_version_tag(identity.model_name, identity.model_version, key, value)
        client.set_tag(identity.mlflow_run_id, key, value)
    observed = client.get_model_version(identity.model_name, identity.model_version)
    if any(observed.tags.get(key) != value for key, value in tags.items()):
        raise RuntimeError("MLflow did not preserve the exact GCS candidate identity")
