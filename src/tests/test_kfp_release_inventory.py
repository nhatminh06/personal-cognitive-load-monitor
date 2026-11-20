import json
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_kfp_release_inventory_has_all_local_roles_without_fake_remote_identity() -> None:
    inventory = json.loads((ROOT / "deploy/releases/kfp-local-images.json").read_text())
    assert len(inventory["images"]) == 15
    assert all(value.startswith("sha256:") and len(value) == 71 for value in inventory["images"].values())
    assert inventory["mlflow_gcs"]["published_reference"] is None
    assert inventory["mlflow_gcs"]["trivy_high"] == 0
    assert inventory["mlflow_gcs"]["trivy_critical"] == 0
