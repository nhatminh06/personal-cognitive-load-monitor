from pathlib import Path
import json
from types import SimpleNamespace

import pytest

from scripts import gke_release_preflight as preflight


@pytest.mark.parametrize("cluster,context", [
    ("cogniflow-local", "kind-cogniflow-local"),
    ("cognitive-load-gke", "kind-cogniflow-module1-qualification"),
])
def test_preflight_rejects_protected_kind_targets_before_network(
    tmp_path: Path, monkeypatch, cluster: str, context: str,
) -> None:
    monkeypatch.setattr(preflight.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("network called"))
    with pytest.raises(ValueError, match="protected or invalid"):
        preflight.assess(
            project="pnm-cognitive-load", region="us-central1", cluster=cluster,
            context=context, kubeconfig=tmp_path / "config",
            controller_matrix=tmp_path / "matrix", image_ledger=tmp_path / "ledger",
        )


def test_preflight_rejects_unqualified_matrix_before_network(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    config.write_text("fixture")
    monkeypatch.setattr(preflight.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("network called"))
    with pytest.raises(ValueError, match="matrix is not qualified"):
        preflight.assess(
            project="pnm-cognitive-load", region="us-central1", cluster="cognitive-load-gke",
            context="gke_pnm-cognitive-load_us-central1_cognitive-load-gke",
            kubeconfig=config, controller_matrix=tmp_path / "matrix",
            image_ledger=tmp_path / "ledger",
        )


def test_preflight_binds_cluster_endpoint_and_checks_ready_nodes(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    config.write_text("fixture")
    monkeypatch.setattr(preflight, "controller_matrix_qualified", lambda _path: True)
    monkeypatch.setattr(preflight, "validate_image_ledger", lambda _path: None)
    context = "gke_pnm-cognitive-load_us-central1_cognitive-load-gke"
    replies = [
        {"name": "cognitive-load-gke", "location": "us-central1", "status": "RUNNING",
         "currentMasterVersion": "1.35.1-gke.100",
         "endpoint": "192.0.2.10", "workloadIdentityConfig": {"workloadPool": "pnm-cognitive-load.svc.id.goog"}},
        {"current-context": context, "clusters": [{"cluster": {"server": "https://192.0.2.10"}}]},
        {"items": [{"status": {"allocatable": {"cpu": "2", "memory": "8Gi"},
                     "conditions": [{"type": "Ready", "status": "True"}]}}] * 2},
    ]
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=json.dumps(replies.pop(0)))

    monkeypatch.setattr(preflight.subprocess, "run", run)
    result = preflight.assess(
        project="pnm-cognitive-load", region="us-central1", cluster="cognitive-load-gke",
        context=context, kubeconfig=config, controller_matrix=tmp_path / "matrix",
        image_ledger=tmp_path / "ledger",
    )
    assert result["status"] == "PASS_TARGET_IDENTITY_ONLY"
    assert len(result["node_allocatable"]) == 2
    assert commands[0][:4] == ("gcloud", "container", "clusters", "describe")
    assert all("apply" not in command and "delete" not in command for command in commands)
