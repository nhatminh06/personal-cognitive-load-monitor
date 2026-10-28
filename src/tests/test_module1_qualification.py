from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.module1_compatibility import REQUIRED_CONTROLLERS, REQUIRED_CRDS
from scripts.module1_qualification_preflight import GIB, validate_resources
from scripts.prepare_module1_manifests import FILES, IMAGE_DIGESTS, prepare
from scripts.render_module1_inventory import build_inventory
from scripts import verify_module1_upstream_inventory as upstream_inventory

ROOT = Path(__file__).parents[2]
QUALIFICATION = ROOT / "qualification/module1"


@pytest.mark.parametrize("becomes_ready,expected_code", [(True, 0), (False, 1)])
def test_cold_readiness_poll_shares_original_deadline(tmp_path, becomes_ready, expected_code):
    script = (QUALIFICATION / "qualify.sh").read_text()
    block = "wait_ready() {" + script.split("wait_ready() {", 1)[1].split('\norigin=', 1)[0]
    block += "\nwait_ready cold\n"
    # A simulated clock and API avoid cluster access and real sleeps.
    harness = r'''
set -euo pipefail
evidence=$1
becomes_ready=$2
start=100
deadline=35
now=130
namespace=test
selector=test
k=(fake_kubectl)
date() { printf '%s\n' "$now"; }
sleep() { now=$((now + 1)); }
abort() { exit 1; }
timeout() { shift; "$@"; }
fake_kubectl() {
  if [[ "$becomes_ready" == true && "$now" -ge 132 ]]; then
    printf '%s\n' '{"items":[{"status":{"readyReplicas":2}}]}'
  else
    printf '%s\n' '{"items":[{"status":{"readyReplicas":0}}]}'
  fi
}
'''
    result = subprocess.run(
        ["bash", "-c", harness + block, "test", str(tmp_path), str(becomes_ready).lower()],
        capture_output=True, text=True,
    )
    assert result.returncode == expected_code, result.stderr
    observations = [json.loads(line) for line in
                    (tmp_path / "cold-readiness-observations.jsonl").read_text().splitlines()]
    assert observations[0] == {"elapsed_seconds": 30, "ready_replicas": 0}
    assert max(row["elapsed_seconds"] for row in observations) <= 35
    assert observations[-1]["ready_replicas"] == (2 if becomes_ready else 0)


def test_idle_retry_activates_before_readiness_and_uses_current_revision():
    script = (QUALIFICATION / "qualify.sh").read_text()
    assert script.index("response=$(predict)") < script.index("wait_ready initial")
    assert script.index("wait_ready initial") < script.index('record READY "$ready"')
    assert 'selector="serving.knative.dev/revision=$revision"' in script
    assert script.index("wait_ready cold") < script.index('post-activation-prediction.json')
    assert 'failure-resources.json' in script and 'failure-events.json' in script


def test_runtime_capture_uses_api_group_in_resource_identity():
    capture = (ROOT / "scripts/capture_module1_runtime.sh").read_text()
    assert 'resource="$kind.${api_version%/*}"' in capture
    assert 'resource="$kind.${api_version#*/}"' not in capture
    assert "while IFS='|' read -r api_version kind resource_namespace name" in capture
    assert 'join("|")' in capture
    assert 'controller-gen\\.kubebuilder\\.io/version' in capture
    assert 'app\\.kubernetes\\.io/version' in capture
    assert 'operator\\.istio\\.io/version' not in capture
    assert '"$kserve" == 0.21.0' in capture


def test_qualification_rejects_unsupported_kubectl_skew():
    qualify = (QUALIFICATION / "qualify.sh").read_text()
    assert 'kubectl-version.json' in qualify
    assert 'kubectl client/server minor skew exceeds one version' in qualify


@pytest.mark.parametrize("desired,actual,observed,expected", [
    (0, 0, 2, True), (1, 1, 2, False), (0, 1, 2, False), (0, 0, 1, False),
])
def test_zero_requires_converged_deployment(desired, actual, observed, expected):
    script = (QUALIFICATION / "qualify.sh").read_text()
    expression = script.split("if jq -e '", 1)[1].split("' \\", 1)[0]
    deployment = {"items": [{"metadata": {"generation": 2},
                            "spec": {"replicas": desired},
                            "status": {"replicas": actual, "readyReplicas": 0,
                                       "observedGeneration": observed}}]}
    result = subprocess.run(["jq", "-e", expression], input=json.dumps(deployment),
                            text=True, capture_output=True)
    assert (result.returncode == 0) == expected
    assert '(.items | length) == 0' in script


def test_resource_preflight_accepts_budget_and_rejects_each_shortage() -> None:
    valid = {"memory": 10 * GIB, "cpus": 4, "disk": 30 * GIB, "docker_memory": 10 * GIB,
             "docker_cpus": 4, "docker_disk": 30 * GIB}
    validate_resources(**valid)
    for values, message in (
        ({**valid, "memory": 10 * GIB - 1}, "memory"),
        ({**valid, "cpus": 3}, "CPUs"),
        ({**valid, "docker_cpus": 3}, "CPUs"),
        ({**valid, "disk": 30 * GIB - 1}, "disk"),
        ({**valid, "docker_disk": 30 * GIB - 1}, "disk"),
        ({**valid, "docker_memory": 10 * GIB - 1}, "memory"),
    ):
        with pytest.raises(RuntimeError, match=message):
            validate_resources(**values)


def test_rendered_inventory_hashes_resources_and_records_kustomize(tmp_path: Path) -> None:
    manifest = tmp_path / "component.yaml"
    manifest.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: exact\n  namespace: test\n")
    inventory = build_inventory("a" * 40, {"component": manifest})
    assert inventory["method"] == "kustomize"
    assert inventory["source_commit"] == "a" * 40
    assert inventory["rendered_manifests"]["component"]
    assert inventory["resource_identities"] == [
        {"apiVersion": "v1", "kind": "ConfigMap", "namespace": "test", "name": "exact"}
    ]


def test_manifest_preparation_pins_images_and_omits_only_kernel_agent(tmp_path: Path) -> None:
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    images = list(IMAGE_DIGESTS)
    documents = [
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": f"workload-{index}"},
         "spec": {"template": {"spec": {"containers": [{"name": "main", "image": image}]}}}}
        for index, image in enumerate(images)
    ]
    documents.append({"apiVersion": "apps/v1", "kind": "DaemonSet",
                      "metadata": {"name": "kserve-kernelcachenode-agent", "namespace": "kserve"}})
    for index, name in enumerate(FILES):
        (source / name).write_text(yaml.safe_dump_all(documents if index == 0 else []))
    evidence = prepare(source, output)
    rendered = "".join(path.read_text() for path in output.glob("*.yaml"))
    assert all(f"@{digest}" in rendered for digest in IMAGE_DIGESTS.values())
    assert "kserve-kernelcachenode-agent" not in rendered
    assert evidence["excluded_resources"] == [
        {"kind": "DaemonSet", "namespace": "kserve", "name": "kserve-kernelcachenode-agent"}
    ]
    first = next(iter(IMAGE_DIGESTS))
    first_manifest = source / FILES[0]
    first_manifest.write_text(first_manifest.read_text().replace(first, "missing:tag"))
    with pytest.raises(ValueError, match="preparation mismatch"):
        prepare(source, tmp_path / "invalid-output")


def test_upstream_inventory_rejects_permissive_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upstream_inventory, "REQUIRED_CONTROLLERS", set())
    monkeypatch.setattr(upstream_inventory, "REQUIRED_CRDS", set())
    with pytest.raises(ValueError, match="allow-all"):
        upstream_inventory.verify(
            [{"kind": "AuthorizationPolicy", "metadata": {"name": "unsafe", "namespace": "user"}, "spec": {"rules": [{}]}}]
        )


def test_upstream_inventory_rejects_missing_namespace_prerequisite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upstream_inventory, "REQUIRED_CONTROLLERS", set())
    monkeypatch.setattr(upstream_inventory, "REQUIRED_CRDS", set())
    with pytest.raises(ValueError, match="namespace prerequisites.*kubeflow"):
        upstream_inventory.verify(
            [{"kind": "Sidecar", "metadata": {"name": "ml-pipeline-ui-exception", "namespace": "kubeflow"}}]
        )


def test_qualification_client_is_restricted_digest_pinned_and_unprivileged() -> None:
    service_account = yaml.safe_load((QUALIFICATION / "qualification-client-serviceaccount.yaml").read_text())
    pod = yaml.safe_load((QUALIFICATION / "qualification-client.yaml").read_text())
    client_manifests = "".join(
        path.read_text() for path in QUALIFICATION.glob("qualification-client*.yaml")
    )
    assert service_account["kind"] == "ServiceAccount" and pod["kind"] == "Pod"
    assert "RoleBinding" not in client_manifests and "ClusterRoleBinding" not in client_manifests
    assert service_account["metadata"]["namespace"] == "cogniflow-qualification"
    assert service_account["automountServiceAccountToken"] is False
    assert pod["spec"]["serviceAccountName"] == "qualification-client"
    assert pod["spec"]["automountServiceAccountToken"] is False
    assert pod["spec"]["securityContext"] == {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    container = pod["spec"]["containers"][0]
    assert "@sha256:" in container["image"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert container["resources"]["requests"] and container["resources"]["limits"]


def test_qualification_gateway_policy_allows_only_the_restricted_client() -> None:
    policy = yaml.safe_load((QUALIFICATION / "qualification-client-gateway-policy.yaml").read_text())
    assert policy["metadata"] == {
        "name": "allow-qualification-client-to-cluster-local-gateway",
        "namespace": "istio-system",
    }
    assert policy["spec"] == {
        "podSelector": {"matchLabels": {
            "app": "cluster-local-gateway", "istio": "cluster-local-gateway",
        }},
        "policyTypes": ["Ingress"],
        "ingress": [{
            "from": [{
                "namespaceSelector": {"matchLabels": {
                    "kubernetes.io/metadata.name": "cogniflow-qualification",
                }},
                "podSelector": {"matchLabels": {
                    "app.kubernetes.io/name": "qualification-client",
                }},
            }],
            "ports": [{"protocol": "TCP", "port": 8081}],
        }],
    }


def test_scripts_require_authorization_context_and_bounded_cold_start() -> None:
    install = (QUALIFICATION / "install.sh").read_text()
    qualify = (QUALIFICATION / "qualify.sh").read_text()
    recover = (QUALIFICATION / "recover-istio.sh").read_text()
    capture = (ROOT / "scripts/capture_module1_runtime.sh").read_text()
    assert "--execute" in install and "kind get clusters" not in install
    assert "module1_qualification_preflight.py --execute" in install
    assert "prepare_module1_manifests.py" in install
    assert "python -m scripts.verify_module1_upstream_inventory" in install
    assert install.count("kubectl kustomize ") == 8
    assert "kustomize build" not in install
    assert "common/kubeflow-namespace/base" in install
    assert install.index('apply -f "$evidence/rendered/kubeflow-namespace.yaml"') < install.index(
        'apply -f "$evidence/rendered/$manifest.yaml"'
    )
    assert 'export KUBECONFIG="$evidence/kubeconfig"' in install + qualify
    assert 'chmod 0600 "$KUBECONFIG"' in install
    assert 'dedicated qualification kubeconfig is missing' in qualify
    assert "kind delete" not in install + qualify
    assert 'kubectl --context "$context"' in install
    assert 'k=(kubectl --context "$context")' in qualify + capture
    assert "--retry" not in qualify
    assert "--connect-timeout 3" in qualify and '--max-time "$deadline"' in qualify
    assert "COLD_ACTIVATION_READY" in qualify and "POST_ACTIVATION_INFERENCE" in qualify
    manifest = re.search(r'cat <<EOF >"\$evidence/inferenceservice.yaml"\n(.*?)\nEOF', qualify, re.S)
    assert manifest
    rendered_isvc = re.sub(r"\$model(?!_)", "qualification-model", manifest.group(1))
    rendered_isvc = rendered_isvc.replace("$namespace", "cogniflow-qualification").replace(
        "$image", "example.invalid/model@sha256:" + "a" * 64
    )
    isvc = yaml.safe_load(rendered_isvc)
    predictor = isvc["spec"]["predictor"]
    assert {key: predictor[key] for key in ("minReplicas", "maxReplicas", "scaleTarget")} == {
        "minReplicas": 0, "maxReplicas": 3, "scaleTarget": 1,
    }
    assert isvc["metadata"]["labels"] == {
        "networking.kserve.io/visibility": "cluster-local",
        "networking.knative.dev/visibility": "cluster-local",
    }
    assert not any("visibility" in key for key in isvc["metadata"]["annotations"])
    assert isvc["metadata"]["annotations"] | {
        "autoscaling.knative.dev/class": "kpa.autoscaling.knative.dev",
        "autoscaling.knative.dev/min-scale": "0",
        "autoscaling.knative.dev/max-scale": "3",
        "autoscaling.knative.dev/target": "1",
    } == isvc["metadata"]["annotations"]
    runtime_env = {item["name"]: item["value"] for item in isvc["spec"]["predictor"]["containers"][0]["env"]}
    assert runtime_env == {
        "MODEL_NAME": "qualification-model",
        "MODEL_VERSION": "1",
        "MODEL_ARTIFACT_SHA256": "$artifact_sha",
        "MODEL_DATASET_SHA256": "$dataset_sha",
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
        "MODEL_SHA256": "$model_sha",
    }
    assert "apply --dry-run=server -f \"$evidence/inferenceservice.yaml\"" in qualify
    assert '.status.url | endswith(".svc.cluster.local")' in qualify
    assert "Knative Service is not strictly cluster-local" in qualify
    assert "AuthorizationPolicy" not in qualify
    assert "--installation-evidence" in qualify and "--qualification-evidence" in qualify
    assert 'export KUBECONFIG="$installation/kubeconfig"' in qualify
    assert "kind-cogniflow-module1-qualification" in qualify
    assert qualify.index("current-context") < qualify.index("module1_qualification_client.py --execute")
    assert 'crictl inspecti "$image"' in qualify
    assert "uv run --offline --frozen python scripts/module1_qualification_model.py" in qualify
    assert "PYTHONPATH=src" in qualify
    assert "--ignore-not-found --wait=true --timeout=60s" in qualify
    assert "qualification-client-gateway-policy.yaml" in qualify
    assert all(controller in capture for controller in REQUIRED_CONTROLLERS)
    assert "--original-evidence" in recover and "--recovery-evidence" in recover
    assert "original-evidence.sha256" in recover and "pre-recovery-resources.json" in recover
    assert "kind delete" not in recover
    assert 'apply -f "$recovery/rendered/kubeflow-namespace.yaml"' in recover
    assert install.count("module1_crd_order.py --execute") == 2
    assert recover.count("module1_crd_order.py --execute") == 2
    assert '--component knative' in install + recover and '--component kserve' in install + recover
    assert "trap failed ERR" in recover


@pytest.mark.parametrize("field,value", [
    (None, None), ("min-scale", "1"), ("max-scale", None),
    ("target", "2"), ("class", "hpa.autoscaling.knative.dev"),
])
def test_effective_autoscaling_gate_rejects_controller_drift(field, value) -> None:
    script = (QUALIFICATION / "qualify.sh").read_text()
    expression = re.search(r"jq -e '(\n  \.spec.template.metadata.annotations as \$a .*?)'", script, re.S)
    assert expression
    annotations = {
        "autoscaling.knative.dev/class": "kpa.autoscaling.knative.dev",
        "autoscaling.knative.dev/min-scale": "0",
        "autoscaling.knative.dev/max-scale": "3",
        "autoscaling.knative.dev/target": "1",
    }
    if field:
        key = f"autoscaling.knative.dev/{field}"
        if value is None:
            del annotations[key]
        else:
            annotations[key] = value
    result = subprocess.run(
        ["jq", "-e", expression.group(1)],
        input=json.dumps({"spec": {"template": {"metadata": {"annotations": annotations}}}}),
        text=True, capture_output=True,
    )
    assert (result.returncode == 0) == (field is None)


def test_pinned_inventory_matches_required_workloads_and_crd_count() -> None:
    inventory = json.loads((ROOT / "docs/module1/upstream-source-inventory.json").read_text())
    assert inventory["source_commit"] == "f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0"
    assert inventory["installation_method"] == "kustomize"
    assert set(inventory["rendered_controllers"]) == REQUIRED_CONTROLLERS
    assert inventory["required_crd_count"] == len(REQUIRED_CRDS) == 38
    assert inventory["required_namespaces"] == ["kubeflow", "kubeflow-system"]
    assert "kserve/kserve-localmodelnode-agent" in inventory["disabled_or_omitted_workloads"]
    assert "kserve/kserve-kernelcachenode-agent" in inventory["disabled_or_omitted_workloads"]


def test_workflow_and_matrix_remain_parseable_blocked_and_standard_safe() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy-module1.yaml").read_text())
    matrix = json.loads((ROOT / "docs/module1/compatibility-matrix.json").read_text())
    standard = yaml.safe_load((ROOT / "helm/cognitive-load-monitor/values.yaml").read_text())
    assert workflow["jobs"]["deploy"]
    assert matrix["qualification_status"] == "BLOCKED"
    assert matrix["selected_candidate"] is None
    assert standard["kserve"]["deploymentMode"] == "Standard"
