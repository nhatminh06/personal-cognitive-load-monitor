"""Strict focus-model package and local serving acceptance tests."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import pytest
import skops.io
from pydantic import ValidationError
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from cogniflow_contracts import BehavioralActivityEvent, CvFeatureWindowEvent, SessionLifecycleEvent
from cogniflow_data.multimodal import MULTIMODAL_FEATURES, sha256_file
from cogniflow_focus import (
    FocusModelManifest,
    FocusModelRuntime,
    package_focus_fixture,
    validate_focus_package,
)
from cogniflow_focus.package import _package_digest
from cogniflow_focus.schemas import FocusPredictionRequest
from cogniflow_sessions import FocusSessionRepository
from preprocessing_api.main import app
from preprocessing_api.sessions import get_session_repository


def _trained_model() -> Pipeline:
    frame = pd.DataFrame([
        [200, 100, 20, 10, 1, np.nan, 1, .9, .1, 12, .2, .01, 1],
        [100, 200, 80, 40, 6, 2, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 0],
        [150, 150, 50, 20, 3, 1, 2, .8, .4, 18, .8, .02, 1],
    ], columns=MULTIMODAL_FEATURES)
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("regressor", RandomForestRegressor(
            n_estimators=10, max_depth=3, random_state=42, n_jobs=1,
        )),
    ])
    model.fit(frame, [2, 6, 4])
    return model


def _package(tmp_path: Path) -> tuple[Path, FocusModelRuntime, Pipeline]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    model = _trained_model()
    model_path = tmp_path / "candidate.skops"
    skops.io.dump(model, model_path)
    dataset = {
        "data_provenance": "synthetic_pipeline_fixture",
        "dataset_sha256": "a" * 64, "split_manifest_sha256": "b" * 64,
        "git_revision": "c" * 40,
    }
    dataset_path = tmp_path / "dataset.manifest.json"
    dataset_path.write_text(json.dumps(dataset))
    report = {
        "validation_scope": "engineering_validation", "dataset_sha256": "a" * 64,
        "runtime_versions": {
            "python": ".".join(map(str, sys.version_info[:3])),
            "numpy": importlib.metadata.version("numpy"),
            "pandas": importlib.metadata.version("pandas"),
            "scikit-learn": importlib.metadata.version("scikit-learn"),
            "skops": importlib.metadata.version("skops"),
        },
        "experiments": {"C": {
            "feature_names": list(MULTIMODAL_FEATURES), "selected_model": "random_forest",
            "model_config": {"n_estimators": 10, "max_depth": 3, "random_state": 42,
                             "n_jobs": 1},
            "model_sha256": "d" * 64, "model_skops_sha256": sha256_file(model_path),
        }},
        "mlflow": {"C": {"mlflow_run_id": "fixture-run-1"}},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    package_dir = tmp_path / "package"
    package_focus_fixture(
        model_path, report_path, dataset_path, package_dir, modality="C",
        model_name="focus-fixture", model_version="1",
    )
    runtime = FocusModelRuntime(package_dir, allow_synthetic_fixture=True)
    runtime.load()
    return package_dir, runtime, model


def _rewrite_governance(
    package_dir: Path, *, provenance: str, status: str, approval_record: dict | None,
) -> None:
    manifest_path = package_dir / "model-package.json"
    payload = json.loads(manifest_path.read_text())
    payload.update({
        "provenance_classification": provenance,
        "approval_status": status,
        "approval_record": approval_record,
    })
    model_bytes = (package_dir / "model.skops").read_bytes()
    unsigned = {key: value for key, value in payload.items() if key != "package_sha256"}
    payload["package_sha256"] = _package_digest(model_bytes, unsigned)
    manifest_path.write_text(json.dumps(payload))


def test_package_integrity_governance_and_offline_parity(tmp_path, monkeypatch):
    package_dir, runtime, offline = _package(tmp_path)
    manifest, model_path = validate_focus_package(package_dir)
    features = dict(zip(MULTIMODAL_FEATURES, [
        200, 100, 20, 10, 1, None, 1, .9, .1, 12, .2, .01, 1,
    ]))
    expected = float(offline.predict(pd.DataFrame([features], columns=MULTIMODAL_FEATURES))[0])
    assert runtime.predict(features) == pytest.approx(expected)
    assert manifest.approval_status == "TEST_FIXTURE_ONLY"
    assert manifest.provenance_classification == "synthetic_fixture"
    assert manifest.model_sha256 == hashlib.sha256(model_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="explicit local test mode"):
        FocusModelRuntime(package_dir).load()
    for production in ("production", " Production "):
        monkeypatch.setenv("APP_ENV", production)
        with pytest.raises(ValueError, match="prohibited"):
            FocusModelRuntime(package_dir, allow_synthetic_fixture=True).load()


@pytest.mark.parametrize(
    ("provenance", "status", "approval_record"),
    [
        ("experimental_candidate", "candidate", None),
        ("approved_candidate", "approved", {
            "approved_by": "self-declared",
            "approved_at": "2026-01-01T00:00:00Z",
            "approval_reference": "forged-reference-one",
        }),
        ("approved_candidate", "approved", {
            "approved_by": "different-forger",
            "approved_at": "2026-02-02T00:00:00Z",
            "approval_reference": "forged-reference-two",
        }),
    ],
)
@pytest.mark.parametrize("allow_fixture", [False, True])
def test_non_synthetic_packages_fail_closed_with_matching_digest(
    tmp_path, provenance, status, approval_record, allow_fixture, monkeypatch,
):
    package_dir, _, _ = _package(tmp_path)
    _rewrite_governance(
        package_dir, provenance=provenance, status=status,
        approval_record=approval_record,
    )
    manifest, _ = validate_focus_package(package_dir)
    assert manifest.provenance_classification == provenance
    monkeypatch.setattr("skops.io.load", lambda *a, **k: pytest.fail("must not deserialize"))
    with pytest.raises(ValueError, match="approval cannot be authenticated"):
        FocusModelRuntime(
            package_dir, allow_synthetic_fixture=allow_fixture,
        ).load()

    result = subprocess.run(
        [sys.executable, "scripts/verify_focus_package.py", str(package_dir)],
        cwd=Path(__file__).parents[2], capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "approval cannot be authenticated" in result.stderr


def test_unknown_governance_and_fixture_constructor_fail_closed(tmp_path):
    package_dir, _, _ = _package(tmp_path)
    manifest_path = package_dir / "model-package.json"
    payload = json.loads(manifest_path.read_text())
    payload["provenance_classification"] = "unknown"
    model_bytes = (package_dir / "model.skops").read_bytes()
    unsigned = {key: value for key, value in payload.items() if key != "package_sha256"}
    payload["package_sha256"] = _package_digest(model_bytes, unsigned)
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError, match="provenance_classification"):
        validate_focus_package(package_dir)

    fresh_package, _, _ = _package(tmp_path / "constructor")
    manifest, _ = validate_focus_package(fresh_package)
    assert manifest.provenance_classification == "synthetic_fixture"
    assert manifest.approval_status == "TEST_FIXTURE_ONLY"
    assert manifest.approval_record is None


def test_package_rejects_corruption_digest_types_and_layout_before_load(tmp_path, monkeypatch):
    package_dir, _, _ = _package(tmp_path)
    model_path = package_dir / "model.skops"
    model_path.write_bytes(b"not-a-model")
    monkeypatch.setattr("skops.io.load", lambda *a, **k: pytest.fail("must not deserialize"))
    with pytest.raises(ValueError, match="valid skops"):
        FocusModelRuntime(package_dir, allow_synthetic_fixture=True).load()
    monkeypatch.undo()

    package_dir, _, _ = _package(tmp_path / "digest")
    manifest_path = package_dir / "model-package.json"
    payload = json.loads(manifest_path.read_text())
    payload["model_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="model digest"):
        validate_focus_package(package_dir)

    package_dir, _, _ = _package(tmp_path / "types")
    monkeypatch.setattr("skops.io.get_untrusted_types", lambda **_: ["evil.Type"])
    with pytest.raises(ValueError, match="reviewed allowlist|serialized types"):
        validate_focus_package(package_dir)


def test_manifest_runtime_pipeline_and_output_fail_closed(tmp_path, monkeypatch):
    package_dir, runtime, _ = _package(tmp_path)
    manifest_path = package_dir / "model-package.json"
    payload = json.loads(manifest_path.read_text())
    with pytest.raises(ValidationError, match="feature names"):
        FocusModelManifest.model_validate({
            **payload, "feature_names": list(reversed(payload["feature_names"])),
        })
    with pytest.raises(ValidationError, match="approval status"):
        FocusModelManifest.model_validate({**payload, "approval_status": "approved"})

    payload["runtime_versions"]["scikit-learn"] = "0.0.0"
    model_bytes = (package_dir / "model.skops").read_bytes()
    payload_without_digest = {k: v for k, v in payload.items() if k != "package_sha256"}
    payload["package_sha256"] = _package_digest(model_bytes, payload_without_digest)
    manifest_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unsupported scikit-learn"):
        FocusModelRuntime(package_dir, allow_synthetic_fixture=True).load()

    pandas_package, _, _ = _package(tmp_path / "pandas-version")
    pandas_manifest = pandas_package / "model-package.json"
    pandas_payload = json.loads(pandas_manifest.read_text())
    pandas_payload["runtime_versions"]["pandas"] = "0.0.0"
    pandas_model = (pandas_package / "model.skops").read_bytes()
    pandas_unsigned = {
        key: value for key, value in pandas_payload.items() if key != "package_sha256"
    }
    pandas_payload["package_sha256"] = _package_digest(pandas_model, pandas_unsigned)
    pandas_manifest.write_text(json.dumps(pandas_payload))
    with pytest.raises(ValueError, match="unsupported pandas"):
        FocusModelRuntime(pandas_package, allow_synthetic_fixture=True).load()

    monkeypatch.setattr(runtime.model, "predict", lambda _: [float("nan")])
    with pytest.raises(ValueError, match="nonfinite"):
        runtime.predict(dict.fromkeys(MULTIMODAL_FEATURES, 0))


def test_request_rejects_private_fields_labels_and_invalid_time():
    now = datetime(2026, 1, 1, 12, 5, 0, 123456, tzinfo=UTC)
    valid = {
        "session_id": "session-1", "window_id": str(uuid4()),
        "window_start": (now - timedelta(minutes=5)).isoformat(),
        "window_end": now.isoformat(), "feature_cutoff": now.isoformat(),
        "cv_contract_version": None, "cv_available": False,
    }
    assert FocusPredictionRequest.model_validate(valid).window_end.microsecond == 123456
    with pytest.raises(ValidationError):
        FocusPredictionRequest.model_validate({**valid, "window_title": "secret.py"})
    with pytest.raises(ValidationError, match="label"):
        FocusPredictionRequest.model_validate({**valid, "label_window_ids_used": [str(uuid4())]})
    with pytest.raises(ValidationError, match="feature_cutoff"):
        FocusPredictionRequest.model_validate({
            **valid, "feature_cutoff": (now - timedelta(seconds=1)).isoformat(),
        })


def _stored_window(repository: FocusSessionRepository, owner: str, *, with_cv: bool) -> dict:
    start = datetime(2026, 1, 1, 12, 0, 0, 654321, tzinfo=UTC)
    end = start + timedelta(minutes=5)
    session_id = "serving-session"
    common = dict(source="test", producer_version="1.0.0")
    repository.create(SessionLifecycleEvent(
        session_id=session_id, event_time=start, ingested_at=start,
        idempotency_key="session-start", event_type="session.started", sequence=1,
        session_kind="programming", privacy_mode="behavioral_cv", **common,
    ), owner)
    repository.transition(SessionLifecycleEvent(
        session_id=session_id, event_time=end, ingested_at=end,
        idempotency_key="session-complete", event_type="session.completed", sequence=2,
        session_kind="programming", privacy_mode="behavioral_cv", **common,
    ), owner)
    window = repository.session(session_id, owner)["completed_windows"][0]
    window_id = UUID(window["window_id"])
    repository.add_activity(BehavioralActivityEvent(
        session_id=session_id, event_time=end, ingested_at=end,
        idempotency_key="behavior", window_id=window_id, window_start=start,
        window_end=end, feature_cutoff=end, active_seconds=200, idle_seconds=100,
        keyboard_event_count=20, pointer_event_count=10, application_switch_count=1,
        build_count=None, test_count=1, **common,
    ), owner)
    if with_cv:
        repository.add_cv(CvFeatureWindowEvent(
            session_id=session_id, event_time=end, ingested_at=end,
            idempotency_key="cv", window_id=window_id, window_start=start,
            window_end=end, feature_cutoff=end, camera_available=True,
            face_presence_ratio=.9, gaze_away_ratio=.1, blink_rate_per_minute=12,
            head_pose_variance=.2, frames_sampled=100, frames_processed=99,
            frames_dropped=1, agent_version="1.0.0", asset_name="fixture",
            asset_sha256="e" * 64, cpu_seconds=1, latency_p50_ms=2,
            latency_p95_ms=3, **common,
        ), owner)
    return {"session_id": session_id, "window_id": str(window_id),
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "feature_cutoff": end.isoformat(), "cv_contract_version": "1.0" if with_cv else None,
            "cv_available": with_cv}


def test_authenticated_http_parity_ownership_and_missing_cv(client, monkeypatch, tmp_path):
    _, runtime, _ = _package(tmp_path)
    key = "focus-test-key"
    owner = hashlib.sha256(key.encode()).hexdigest()
    repository = FocusSessionRepository(tmp_path / "sessions.sqlite3")
    request = _stored_window(repository, owner, with_cv=True)
    monkeypatch.setenv("COGNIFLOW_API_KEY", key)
    monkeypatch.setattr("cogniflow_focus.api.get_focus_runtime", lambda: runtime)
    app.dependency_overrides[get_session_repository] = lambda: repository
    try:
        assert client.post("/v1/focus/predict", json=request).status_code == 401
        wrong = client.post("/v1/focus/predict", json=request, headers={"x-api-key": "wrong"})
        assert wrong.status_code == 401
        response = client.post(
            "/v1/focus/predict", json=request, headers={"x-api-key": key}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    stored = repository.feature_window(request["session_id"], UUID(request["window_id"]), owner)
    activity, cv = stored["activity"], stored["cv"]
    features = dict(zip(MULTIMODAL_FEATURES, [
        activity[name] for name in MULTIMODAL_FEATURES[:7]
    ] + [cv[name] for name in MULTIMODAL_FEATURES[7:11]] + [
        cv["frames_dropped"] / cv["frames_sampled"], 1,
    ]))
    assert body["predicted_effort_rating"] == pytest.approx(runtime.predict(features))
    assert body["test_fixture"] is True and body["provenance_classification"] == "synthetic_fixture"
    assert "confidence" not in body and "class_probabilities" not in body


def test_http_rejects_cross_owner_boundary_mismatch_and_cv_claim(client, monkeypatch, tmp_path):
    _, runtime, _ = _package(tmp_path)
    key = "owner-key"
    owner = hashlib.sha256(key.encode()).hexdigest()
    repository = FocusSessionRepository(tmp_path / "sessions.sqlite3")
    request = _stored_window(repository, owner, with_cv=False)
    monkeypatch.setenv("COGNIFLOW_API_KEY", key)
    monkeypatch.setattr("cogniflow_focus.api.get_focus_runtime", lambda: runtime)
    app.dependency_overrides[get_session_repository] = lambda: repository
    try:
        assert client.post(
            "/v1/focus/predict", json=request, headers={"x-api-key": "other"}
        ).status_code == 401
        changed = {
            **request,
            "window_start": "2026-01-01T12:00:01.654321+00:00",
            "window_end": "2026-01-01T12:05:01.654321+00:00",
            "feature_cutoff": "2026-01-01T12:05:01.654321+00:00",
        }
        assert client.post(
            "/v1/focus/predict", json=changed, headers={"x-api-key": key}
        ).status_code == 409
        cv_claim = {**request, "cv_available": True, "cv_contract_version": "1.0"}
        assert client.post(
            "/v1/focus/predict", json=cv_claim, headers={"x-api-key": key}
        ).status_code == 409
    finally:
        app.dependency_overrides.clear()
