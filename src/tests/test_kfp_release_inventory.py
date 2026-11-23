import json
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_kfp_release_inventory_has_all_local_roles_without_fake_remote_identity() -> None:
    inventory = json.loads((ROOT / "deploy/releases/kfp-local-images.json").read_text())
    assert len(inventory["images"]) == 16
    assert all(value.startswith("sha256:") and len(value) == 71 for value in inventory["images"].values())
    assert inventory["images"]["mlflow-s3"] == (
        "sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5"
    )
    assert inventory["images"]["mlflow-gcs"] == (
        "sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5"
    )
    assert inventory["mlflow_s3"]["published_reference"] is None
    assert inventory["mlflow_s3"]["trivy_high"] == 0
    assert inventory["mlflow_s3"]["trivy_critical"] == 0
    assert inventory["mlflow_gcs"]["published_reference"] is None
    assert inventory["mlflow_gcs"]["trivy_high"] == 0
    assert inventory["mlflow_gcs"]["trivy_critical"] == 0


def test_local_mlflow_role_matches_overlay_without_relabeling_gcs() -> None:
    inventory = json.loads((ROOT / "deploy/releases/kfp-local-images.json").read_text())
    overlay = list(yaml.safe_load_all((ROOT / "infra/kfp-local/mlflow.yaml").read_text()))[0]
    image = overlay["spec"]["template"]["spec"]["containers"][0]["image"]

    assert image == f'cogniflow-mlflow@{inventory["images"]["mlflow-s3"]}'
    assert inventory["images"]["mlflow-s3"] != inventory["images"]["mlflow-gcs"]


def test_kfp_local_resource_patches_have_bounded_cpu_and_memory() -> None:
    expected = {
        "kfp-api.yaml": ("250m", "500Mi", "1", "1Gi"),
        "persistence-agent.yaml": ("120m", "500Mi", "500m", "1Gi"),
        "workflow-controller.yaml": ("100m", "500Mi", "500m", "1Gi"),
        "seaweedfs.yaml": ("64m", "256Mi", "1", "768Mi"),
    }

    for filename, values in expected.items():
        patch = yaml.safe_load((ROOT / "infra/kfp-local" / filename).read_text())
        resources = patch["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert (
            resources["requests"]["cpu"],
            resources["requests"]["memory"],
            resources["limits"]["cpu"],
            resources["limits"]["memory"],
        ) == values
