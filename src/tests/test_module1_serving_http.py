"""Bounded loopback acceptance for KServe ModelServer and FastAPI."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from cogniflow_kserve.engineering import package_engineering_model
from preprocessing_api.features import FEATURE_NAMES, feature_vector


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(url: str, process: subprocess.Popen, *, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"local server exited with {process.returncode}")
        try:
            if httpx.get(url, timeout=0.5, trust_env=False).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"local server was not ready: {url}")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _package(tmp_path: Path) -> tuple[Path, dict]:
    frame = pd.DataFrame(
        [
            [0, 0, 0, 87600, 0, 0],
            [1440, 0, 0, 0, 1, 0],
            [0, 1440, 1000, 0, 0, 1],
            [120, 30, 3, 24, 0.8, 0.2],
            [30, 120, 8, 4, 0.2, 0.8],
            [60, 60, 2, 48, 0.5, 0.5],
        ],
        columns=FEATURE_NAMES,
    )
    labels = ["LOW", "LOW", "HIGH", "MEDIUM", "HIGH", "MEDIUM"]
    source = tmp_path / "model.joblib"
    joblib.dump(RandomForestClassifier(n_estimators=8, random_state=42).fit(frame, labels), source)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    validation = tmp_path / "validation.csv"
    frame.assign(cognitive_load_level=labels).to_csv(validation, index=False)
    report = tmp_path / "metrics.json"
    report.write_text(json.dumps({
        "contract_version": "2.0",
        "selected_model": "random_forest",
        "validation_scope": "synthetic_proxy_engineering_only",
        "exported_joblib_sha256": source_digest,
        "mlflow": {
            "experiment": "cogniflow-module1-engineering-candidates",
            "candidate_run_ids": {
                "dummy_majority": "b" * 32,
                "logistic_regression": "c" * 32,
                "random_forest": "a" * 32,
            },
            "selected_run_id": "a" * 32,
        },
        "lineage": {
            "dataset_sha256": "a" * 64,
            "git_revision": "b" * 40,
            "feature_schema_version": "1.0",
            "feature_names": list(FEATURE_NAMES),
            "label_provenance": "synthetic_proxy",
        },
    }))
    package = tmp_path / "package"
    manifest = package_engineering_model(
        source, report, validation, package, expected_source_sha256=source_digest
    )
    return package, manifest


def test_real_kserve_and_fastapi_loopback(tmp_path):
    package, manifest = _package(tmp_path)
    kserve_port, grpc_port, api_port = _port(), _port(), _port()
    root = Path(__file__).resolve().parents[2]
    base_env = {
        **os.environ,
        "APP_ENV": "development",
        "PYTHONPATH": str(root / "src"),
        "MODEL_PATH": str(package / "cognitive_load_model.skops"),
        "MODEL_PACKAGE_PATH": str(package / "model-package.json"),
        "MODEL_NAME": str(manifest["model_name"]),
        "MODEL_VERSION": str(manifest["model_version"]),
        "MODEL_ARTIFACT_SHA256": str(manifest["registered_artifact_sha256"]),
        "MODEL_SHA256": str(manifest["packaged_model_sha256"]),
        "MODEL_DATASET_SHA256": str(manifest["dataset_sha256"]),
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
    }
    kserve = subprocess.Popen(
        [
            sys.executable,
            "scripts/serve_engineering_model.py",
            "--model_name", str(manifest["model_name"]),
            "--http_port", str(kserve_port),
            "--grpc_port", str(grpc_port),
            "--allow-synthetic-engineering",
        ],
        cwd=root,
        env=base_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    api = None
    try:
        model_url = f"http://127.0.0.1:{kserve_port}"
        _wait(f"{model_url}/v1/models/{manifest['model_name']}", kserve)
        api_env = {
            **base_env,
            "INFERENCE_MODE": "kserve",
            "ALLOW_SYNTHETIC_ENGINEERING_MODEL": "true",
            "KSERVE_ALLOWED_ORIGIN": model_url,
            "KSERVE_PREDICT_URL": f"{model_url}/v1/models/{manifest['model_name']}:predict",
            "KSERVE_METADATA_URL": f"{model_url}/v1/models/{manifest['model_name']}/metadata",
        }
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "preprocessing_api.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
            cwd=root,
            env=api_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        api_url = f"http://127.0.0.1:{api_port}"
        _wait(f"{api_url}/health", api)
        body = {"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 3, "hours_to_deadline": 24}
        offline_frame = pd.DataFrame([feature_vector(body)], columns=FEATURE_NAMES)
        offline = joblib.load(tmp_path / "model.joblib").predict(offline_frame)[0]
        response = httpx.post(f"{api_url}/predict", json=body, timeout=5, trust_env=False)
        assert response.status_code == 200
        assert response.json()["cognitive_load_level"] == offline
        assert response.json()["inference_source"] == "kserve"
        assert httpx.post(
            f"{api_url}/predict", json={**body, "wrong_feature": 1}, timeout=5, trust_env=False
        ).status_code == 422

        _stop(kserve)
        assert httpx.post(f"{api_url}/predict", json=body, timeout=5, trust_env=False).status_code == 503
    finally:
        _stop(kserve)
        if api is not None:
            _stop(api)
