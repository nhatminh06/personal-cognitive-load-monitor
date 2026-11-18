from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/deploy.sh"
DIGEST = "a" * 64
COMMIT = "b" * 40


def environment(action: str = "plan") -> dict[str, str]:
    context, namespace, release = "gke_project_us-central1_cogniflow", "cogniflow", "cogniflow"
    return {
        **os.environ,
        "KUBE_CONTEXT": context,
        "KUBECONFIG": "/nonexistent/offline-test",
        "NAMESPACE": namespace,
        "RELEASE": release,
        "API_IMAGE": f"us-central1-docker.pkg.dev/project-1/cogniflow-images/cognitive-load-api@sha256:{DIGEST}",
        "KSERVE_IMAGE": f"us-central1-docker.pkg.dev/project-1/cogniflow-images/cogniflow-kserve@sha256:{DIGEST}",
        "SOURCE_COMMIT": COMMIT,
        "MODEL_NAME": "cognitive-load-classifier",
        "MODEL_VERSION": "1",
        "MODEL_SHA256": DIGEST,
        "MODEL_ARTIFACT_SHA256": DIGEST,
        "MODEL_DATASET_SHA256": DIGEST,
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
        "MODEL_PACKAGE_SHA256": DIGEST,
        "MODEL_APPROVAL_STATUS": "approved",
        "OWNER_AUTHORIZATION": f"DEPLOY:{COMMIT}:{DIGEST}:{context}:{namespace}:{release}:{action}",
    }


def run(action: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([SCRIPT, action], cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def test_offline_plan_accepts_only_exact_immutable_release_identity() -> None:
    result = run("plan", environment())
    assert result.returncode == 0
    assert "@sha256:" in result.stdout


def test_deploy_requires_separate_execution_authorization() -> None:
    result = run("deploy", environment("deploy"))
    assert result.returncode == 2
    assert "EXECUTE=authorized" in result.stderr


def test_mutable_image_and_protected_context_fail_closed() -> None:
    mutable = environment()
    mutable["API_IMAGE"] = "registry.example/cognitive-load-api:latest"
    assert "immutable" in run("plan", mutable).stderr
    protected = environment()
    protected["KUBE_CONTEXT"] = "kind-cogniflow-local"
    assert "protected" in run("plan", protected).stderr

    candidate = environment()
    candidate["MODEL_APPROVAL_STATUS"] = "candidate"
    assert "model approval" in run("plan", candidate).stderr


def test_rollback_is_bound_to_an_exact_revision() -> None:
    result = run("rollback", environment("rollback"))
    assert result.returncode == 2
    assert "ROLLBACK_REVISION" in result.stderr
