from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from kfp import compiler

from pipelines.cogniflow_training_pipeline import build_pipeline

IMAGE = "localhost/cogniflow-kfp@sha256:" + "a" * 64


def compiled(tmp_path: Path) -> tuple[str, dict]:
    output = tmp_path / "pipeline.yaml"
    compiler.Compiler().compile(build_pipeline(IMAGE), package_path=str(output))
    text = output.read_text()
    specification = list(yaml.safe_load_all(text))[0]
    return text, specification


def test_kfp_v2_pipeline_compiles_with_immutable_bounded_components(tmp_path: Path) -> None:
    text, specification = compiled(tmp_path)
    assert specification["pipelineInfo"]["name"] == "cogniflow-kubeflow-training"
    executors = specification["deploymentSpec"]["executors"]
    images = [executor["container"]["image"] for executor in executors.values() if "container" in executor]
    assert len(images) == 6 and set(images) == {IMAGE}
    assert "latest" not in text
    assert "cpuLimit: 1" in text
    assert "memoryLimit: 2.147483648" in text
    assert "runAsUser: '10001'" in text
    assert "activeDeadlineSeconds: '600'" in text


def test_kfp_graph_has_real_artifact_dependencies_and_failure_order(tmp_path: Path) -> None:
    _, specification = compiled(tmp_path)
    tasks = specification["root"]["dag"]["tasks"]
    assert set(tasks) == {
        "importer", "importer-2", "importer-3", "validate-inputs-component",
        "prepare-dataset-component", "train-candidates-component",
        "evaluate-select-component", "register-candidate-component",
        "record-provenance-component",
    }
    assert "validate-inputs-component" in tasks["prepare-dataset-component"]["dependentTasks"]
    assert tasks["train-candidates-component"]["dependentTasks"] == ["prepare-dataset-component"]
    assert "train-candidates-component" in tasks["evaluate-select-component"]["dependentTasks"]
    assert "evaluate-select-component" in tasks["register-candidate-component"]["dependentTasks"]
    assert "register-candidate-component" in tasks["record-provenance-component"]["dependentTasks"]


@pytest.mark.parametrize(
    "image",
    ["cogniflow-kfp:latest", "cogniflow-kfp@sha256:bad", "sha256:" + "a" * 64],
)
def test_pipeline_rejects_mutable_or_invalid_component_images(image: str) -> None:
    with pytest.raises(ValueError, match="immutable OCI repository digest"):
        build_pipeline(image)
