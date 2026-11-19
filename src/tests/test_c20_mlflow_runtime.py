from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
IMAGE = (
    "cogniflow-mlflow@sha256:"
    "de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5"
)


def test_mlflow_manifest_keeps_database_and_artifacts_external() -> None:
    documents = list(yaml.safe_load_all((ROOT / "infra/kfp-local/mlflow.yaml").read_text()))
    deployment = next(item for item in documents if item["kind"] == "Deployment")
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert container["image"] == IMAGE
    assert container["imagePullPolicy"] == "Never"
    assert environment["MLFLOW_BACKEND_STORE_URI"]["valueFrom"]["secretKeyRef"] == {
        "name": "cogniflow-mlflow",
        "key": "backend-store-uri",
    }
    assert environment["MLFLOW_ARTIFACTS_DESTINATION"]["value"].startswith("s3://")
    assert environment["MLFLOW_S3_ENDPOINT_URL"]["value"].startswith("http://seaweedfs.")
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert pod["securityContext"]["runAsUser"] == 65532
    assert all(item["kind"] != "PersistentVolumeClaim" for item in documents)


def test_mlflow_build_inputs_are_immutable_and_non_root() -> None:
    dockerfile = (ROOT / "deploy/c20/mlflow/Dockerfile").read_text()

    assert dockerfile.count("@sha256:") == 3
    assert "python-3.13=3.13.18_git20261115-r1" in dockerfile
    assert "USER 65532:65532" in dockerfile
    assert "COPY requirements.txt" in dockerfile
