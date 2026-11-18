from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/deploy.sh"
DIGEST = "a" * 64
COMMIT = "b" * 40
CLUSTER_UID = "11111111-1111-4111-8111-111111111111"
API_SERVER = "https://authorized.example:443"


def environment(action: str = "plan") -> dict[str, str]:
    context, namespace, release = "gke_project_us-central1_cogniflow", "cogniflow", "cogniflow"
    return {
        **os.environ,
        "KUBE_CONTEXT": context,
        "KUBECONFIG": "/nonexistent/offline-test",
        "KUBECONFIG_SHA256": DIGEST,
        "TARGET_API_SERVER": API_SERVER,
        "TARGET_CLUSTER_UID": CLUSTER_UID,
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
        "OWNER_AUTHORIZATION": (
            f"DEPLOY:{COMMIT}:{DIGEST}:{context}:{DIGEST}:{API_SERVER}:{CLUSTER_UID}:"
            f"{namespace}:{release}:{action}"
        ),
    }


def run(action: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([SCRIPT, action], cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def execution_environment(tmp_path: Path) -> dict[str, str]:
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text("trusted kubeconfig")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    kubectl = binary_dir / "kubectl"
    kubectl.write_text(
        "#!/usr/bin/env bash\n"
        "case \"$*\" in\n"
        "  *'config view'*) printf '%s' \"$FAKE_API_SERVER\" ;;\n"
        "  *'get namespace kube-system'*) printf '%s' \"$FAKE_CLUSTER_UID\" ;;\n"
        "  *) exit 99 ;;\n"
        "esac\n"
    )
    kubectl.chmod(0o700)
    value = environment("deploy")
    value.update({
        "KUBECONFIG": str(kubeconfig),
        "KUBECONFIG_SHA256": hashlib.sha256(kubeconfig.read_bytes()).hexdigest(),
        "EXECUTE": "authorized",
        "EVIDENCE_DIR": str(tmp_path),
        "FAKE_API_SERVER": API_SERVER,
        "FAKE_CLUSTER_UID": CLUSTER_UID,
        "PATH": f"{binary_dir}:{value['PATH']}",
    })
    value["OWNER_AUTHORIZATION"] = (
        f"DEPLOY:{COMMIT}:{DIGEST}:{value['KUBE_CONTEXT']}:{value['KUBECONFIG_SHA256']}:"
        f"{API_SERVER}:{CLUSTER_UID}:{value['NAMESPACE']}:{value['RELEASE']}:deploy"
    )
    return value


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


def test_context_alias_cannot_hide_a_different_cluster(tmp_path: Path) -> None:
    value = execution_environment(tmp_path)
    value["KUBE_CONTEXT"] = "production-alias"
    value["FAKE_CLUSTER_UID"] = "22222222-2222-4222-8222-222222222222"
    value["OWNER_AUTHORIZATION"] = value["OWNER_AUTHORIZATION"].replace(
        "gke_project_us-central1_cogniflow", "production-alias"
    )
    result = run("deploy", value)
    assert result.returncode == 2
    assert "cluster UID identity mismatch" in result.stderr


def test_wrong_cluster_api_is_rejected_before_mutation(tmp_path: Path) -> None:
    value = execution_environment(tmp_path)
    value["FAKE_API_SERVER"] = "https://wrong.example:443"
    result = run("deploy", value)
    assert result.returncode == 2
    assert "cluster API identity mismatch" in result.stderr


def test_altered_kubeconfig_is_rejected_before_cluster_access(tmp_path: Path) -> None:
    value = execution_environment(tmp_path)
    Path(value["KUBECONFIG"]).write_text("altered kubeconfig")
    result = run("deploy", value)
    assert result.returncode == 2
    assert "kubeconfig identity mismatch" in result.stderr
