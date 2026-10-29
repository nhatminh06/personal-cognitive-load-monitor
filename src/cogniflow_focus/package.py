"""Immutable, skops-only focus-model package contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

import skops.io
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cogniflow_data.multimodal import (
    BEHAVIORAL_FEATURES,
    CV_FEATURES,
    MULTIMODAL_FEATURES,
    TARGET_VERSION,
    sha256_file,
)

PACKAGE_FORMAT = "cogniflow-focus-skops"
PACKAGE_VERSION = "1.0"
REVIEWED_SKOPS_TYPES = frozenset({"numpy.dtype", "sklearn.tree._tree.Tree"})
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1_000
FEATURE_CONTRACT = {
    "active_seconds": {"type": "float", "minimum": 0, "maximum": 300, "nullable": False},
    "idle_seconds": {"type": "float", "minimum": 0, "maximum": 300, "nullable": False},
    "keyboard_event_count": {"type": "integer", "minimum": 0, "maximum": 1_000_000, "nullable": False},
    "pointer_event_count": {"type": "integer", "minimum": 0, "maximum": 1_000_000, "nullable": False},
    "application_switch_count": {"type": "integer", "minimum": 0, "maximum": 100_000, "nullable": False},
    "build_count": {"type": "integer", "minimum": 0, "maximum": 100_000, "nullable": True},
    "test_count": {"type": "integer", "minimum": 0, "maximum": 100_000, "nullable": True},
    "face_presence_ratio": {"type": "float", "minimum": 0, "maximum": 1, "nullable": True},
    "gaze_away_ratio": {"type": "float", "minimum": 0, "maximum": 1, "nullable": True},
    "blink_rate_per_minute": {"type": "float", "minimum": 0, "maximum": 300, "nullable": True},
    "head_pose_variance": {"type": "float", "minimum": 0, "maximum": 10_000, "nullable": True},
    "frame_drop_ratio": {"type": "float", "minimum": 0, "maximum": 1, "nullable": True},
    "cv_available": {"type": "integer", "minimum": 0, "maximum": 1, "nullable": False},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovalRecord(StrictModel):
    approved_by: str = Field(min_length=1, max_length=128)
    approved_at: str = Field(min_length=1, max_length=64)
    approval_reference: str = Field(min_length=1, max_length=256)


class FocusModelManifest(StrictModel):
    package_format: Literal["cogniflow-focus-skops"] = "cogniflow-focus-skops"
    package_version: Literal["1.0"] = "1.0"
    model_name: str = Field(pattern=r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
    model_version: str = Field(pattern=r"^[1-9][0-9]*$")
    modality: Literal["A", "B", "C"]
    target_name: Literal["self_reported_effort"] = "self_reported_effort"
    target_version: Literal["self_reported_effort.v1"] = "self_reported_effort.v1"
    feature_schema_version: Literal["1.0"] = "1.0"
    behavioral_contract_version: Literal["1.0"] = "1.0"
    cv_contract_version: Literal["1.0"] | None
    feature_names: tuple[str, ...]
    feature_contract: dict[str, dict[str, Any]]
    cv_missing_policy: Literal["not_used", "required", "null_with_availability_indicator"]
    preprocessing_policy: Literal["packaged_train_fitted_pipeline"]
    model_family: Literal["dummy_median", "ridge", "random_forest"]
    model_configuration: dict[str, Any]
    dataset_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    dvc_stage: Literal["multimodal_experiments"]
    dvc_params: dict[str, int]
    mlflow_run_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    runtime_versions: dict[str, str]
    skops_trusted_types: tuple[str, ...]
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_joblib_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provenance_classification: Literal[
        "synthetic_fixture", "experimental_candidate", "approved_candidate"
    ]
    approval_status: Literal["TEST_FIXTURE_ONLY", "candidate", "approved"]
    approval_record: ApprovalRecord | None = None
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def coherent_contract(self) -> Self:
        expected_features = {
            "A": BEHAVIORAL_FEATURES, "B": CV_FEATURES, "C": MULTIMODAL_FEATURES,
        }[self.modality]
        expected_cv = {"A": None, "B": "1.0", "C": "1.0"}[self.modality]
        expected_policy = {
            "A": "not_used", "B": "required", "C": "null_with_availability_indicator",
        }[self.modality]
        if self.feature_names != expected_features or self.cv_contract_version != expected_cv:
            raise ValueError("feature names or contract versions do not match modality")
        if self.cv_missing_policy != expected_policy:
            raise ValueError("CV missingness policy does not match modality")
        expected_contract = {name: FEATURE_CONTRACT[name] for name in expected_features}
        if self.feature_contract != expected_contract:
            raise ValueError("feature contract does not match ordered features")
        governance = {
            "synthetic_fixture": "TEST_FIXTURE_ONLY",
            "experimental_candidate": "candidate",
            "approved_candidate": "approved",
        }
        if self.approval_status != governance[self.provenance_classification]:
            raise ValueError("provenance classification cannot change approval status")
        if (self.approval_record is not None) != (self.approval_status == "approved"):
            raise ValueError("approved candidates require a separate approval record")
        if set(self.skops_trusted_types) - REVIEWED_SKOPS_TYPES:
            raise ValueError("package requests an unreviewed skops type")
        return self


def enforce_local_fixture_governance(manifest: FocusModelManifest) -> None:
    """Permit only synthetic packages while no approval trust verifier exists."""

    if (
        manifest.provenance_classification != "synthetic_fixture"
        or manifest.approval_status != "TEST_FIXTURE_ONLY"
        or manifest.approval_record is not None
    ):
        raise ValueError("focus model approval cannot be authenticated")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _package_digest(model_bytes: bytes, manifest_without_digest: dict[str, Any]) -> str:
    return hashlib.sha256(model_bytes + b"\0" + canonical_json(manifest_without_digest)).hexdigest()


def _validate_archive(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.suffix != ".skops":
        raise ValueError("model must be a regular .skops file")
    if path.stat().st_size > MAX_MODEL_BYTES:
        raise ValueError("model package exceeds the size limit")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("skops archive member count is invalid")
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise ValueError("skops archive contains duplicate members")
            if sum(member.file_size for member in members) > MAX_ARCHIVE_BYTES:
                raise ValueError("skops archive expands beyond the size limit")
            for member in members:
                parts = PurePosixPath(member.filename).parts
                if member.flag_bits & 1 or not parts or "/" in parts[0] or ".." in parts:
                    raise ValueError("skops archive contains an unsafe member")
    except zipfile.BadZipFile as exc:
        raise ValueError("model is not a valid skops archive") from exc


def validate_focus_package(package_dir: Path) -> tuple[FocusModelManifest, Path]:
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise ValueError("focus model package directory is unavailable")
    if {path.name for path in package_dir.iterdir()} != {"model.skops", "model-package.json"}:
        raise ValueError("focus model package layout is unsupported")
    model_path, manifest_path = package_dir / "model.skops", package_dir / "model-package.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("focus model manifest is unavailable")
    _validate_archive(model_path)
    manifest = FocusModelManifest.model_validate_json(manifest_path.read_text())
    model_bytes = model_path.read_bytes()
    if not hashlib.sha256(model_bytes).hexdigest() == manifest.model_sha256:
        raise ValueError("focus model digest mismatch")
    actual_types = tuple(sorted(skops.io.get_untrusted_types(file=model_path)))
    if actual_types != manifest.skops_trusted_types:
        raise ValueError("skops serialized types do not match the reviewed allowlist")
    payload = manifest.model_dump(mode="json")
    package_digest = payload.pop("package_sha256")
    if _package_digest(model_bytes, payload) != package_digest:
        raise ValueError("focus package digest mismatch")
    return manifest, model_path


def package_focus_fixture(
    model_path: Path, report_path: Path, dataset_manifest_path: Path,
    output_dir: Path, *, modality: Literal["A", "B", "C"],
    model_name: str, model_version: str,
) -> FocusModelManifest:
    """Package one trusted PR 5 skops output without deserializing it."""

    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    _validate_archive(model_path)
    report = json.loads(report_path.read_text())
    dataset = json.loads(dataset_manifest_path.read_text())
    experiment = report.get("experiments", {}).get(modality, {})
    if report.get("validation_scope") != "engineering_validation":
        raise ValueError("this command packages synthetic engineering fixtures only")
    if dataset.get("data_provenance") != "synthetic_pipeline_fixture":
        raise ValueError("fixture packaging requires synthetic dataset provenance")
    if experiment.get("model_skops_sha256") != sha256_file(model_path):
        raise ValueError("PR 5 report and skops model digest disagree")
    if report.get("dataset_sha256") != dataset.get("dataset_sha256"):
        raise ValueError("dataset lineage does not match the experiment report")
    trusted = tuple(sorted(skops.io.get_untrusted_types(file=model_path)))
    if set(trusted) - REVIEWED_SKOPS_TYPES:
        raise ValueError("model contains unreviewed serialized types")
    features = tuple(experiment.get("feature_names", ()))
    cv_version = None if modality == "A" else "1.0"
    policy = {"A": "not_used", "B": "required", "C": "null_with_availability_indicator"}[modality]
    mlflow = report.get("mlflow", {}).get(modality, {})
    base = {
        "package_format": PACKAGE_FORMAT, "package_version": PACKAGE_VERSION,
        "model_name": model_name, "model_version": model_version, "modality": modality,
        "target_name": "self_reported_effort", "target_version": TARGET_VERSION,
        "feature_schema_version": "1.0", "behavioral_contract_version": "1.0",
        "cv_contract_version": cv_version, "feature_names": features,
        "feature_contract": {name: FEATURE_CONTRACT[name] for name in features},
        "cv_missing_policy": policy,
        "preprocessing_policy": "packaged_train_fitted_pipeline",
        "model_family": experiment.get("selected_model"),
        "model_configuration": experiment.get("model_config"),
        "dataset_manifest_sha256": sha256_file(dataset_manifest_path),
        "dataset_sha256": dataset["dataset_sha256"],
        "split_manifest_sha256": dataset["split_manifest_sha256"],
        "git_revision": dataset["git_revision"], "dvc_stage": "multimodal_experiments",
        "dvc_params": {"samples": 90, "seed": 42},
        "mlflow_run_id": mlflow.get("mlflow_run_id"),
        "runtime_versions": report.get("runtime_versions"),
        "skops_trusted_types": trusted, "model_sha256": sha256_file(model_path),
        "source_joblib_sha256": experiment.get("model_sha256"),
        "provenance_classification": "synthetic_fixture",
        "approval_status": "TEST_FIXTURE_ONLY", "approval_record": None,
    }
    model_bytes = model_path.read_bytes()
    base["package_sha256"] = _package_digest(model_bytes, base)
    manifest = FocusModelManifest.model_validate(base)
    enforce_local_fixture_governance(manifest)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir.parent) as temporary:
        package = Path(temporary) / output_dir.name
        package.mkdir()
        shutil.copyfile(model_path, package / "model.skops")
        (package / "model-package.json").write_bytes(
            canonical_json(manifest.model_dump(mode="json")) + b"\n"
        )
        package.rename(output_dir)
    validate_focus_package(output_dir)
    return manifest
