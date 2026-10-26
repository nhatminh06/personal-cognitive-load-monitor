"""Kubeflow Pipelines v2 graph for deterministic CogniFlow candidate training."""

import re

from kfp import dsl, kubernetes

PIPELINE_NAME = "cogniflow-kubeflow-training"
IMAGE_PATTERN = re.compile(r"^[a-z0-9./:_-]+@sha256:[0-9a-f]{64}$")


def build_pipeline(component_image: str):
    if not IMAGE_PATTERN.fullmatch(component_image):
        raise ValueError("component image must use an immutable OCI repository digest")

    @dsl.container_component
    def validate_inputs_component(
        features: dsl.Input[dsl.Dataset],
        labels: dsl.Input[dsl.Dataset],
        feature_manifest: dsl.Input[dsl.Artifact],
        git_revision: str,
        validation: dsl.Output[dsl.Artifact],
    ):
        return dsl.ContainerSpec(
            image=component_image,
            command=["python", "-m", "cogniflow_data.kfp_tasks", "validate"],
            args=[
                "--features", features.path,
                "--labels", labels.path,
                "--feature-manifest", feature_manifest.path,
                "--output", validation.path,
                "--git-revision", git_revision,
            ],
        )

    @dsl.container_component
    def prepare_dataset_component(
        features: dsl.Input[dsl.Dataset],
        labels: dsl.Input[dsl.Dataset],
        feature_manifest: dsl.Input[dsl.Artifact],
        validation: dsl.Input[dsl.Artifact],
        training_cutoff: str,
        git_revision: str,
        dataset: dsl.Output[dsl.Dataset],
        dataset_manifest: dsl.Output[dsl.Artifact],
    ):
        return dsl.ContainerSpec(
            image=component_image,
            command=["python", "-m", "cogniflow_data.kfp_tasks", "prepare"],
            args=[
                "--features", features.path,
                "--labels", labels.path,
                "--feature-manifest", feature_manifest.path,
                "--validation", validation.path,
                "--output-dataset", dataset.path,
                "--output-manifest", dataset_manifest.path,
                "--training-cutoff", training_cutoff,
                "--git-revision", git_revision,
            ],
        )

    @dsl.container_component
    def train_candidates_component(
        dataset: dsl.Input[dsl.Dataset],
        dataset_manifest: dsl.Input[dsl.Artifact],
        candidate_models: dsl.Output[dsl.Model],
        validation_metrics: dsl.Output[dsl.Metrics],
    ):
        return dsl.ContainerSpec(
            image=component_image,
            command=["python", "-m", "cogniflow_data.kfp_tasks", "train"],
            args=[
                "--dataset", dataset.path,
                "--manifest", dataset_manifest.path,
                "--output-models", candidate_models.path,
                "--output-validation", validation_metrics.path,
            ],
        )

    @dsl.container_component
    def evaluate_select_component(
        dataset: dsl.Input[dsl.Dataset],
        dataset_manifest: dsl.Input[dsl.Artifact],
        candidate_models: dsl.Input[dsl.Model],
        validation_metrics: dsl.Input[dsl.Metrics],
        selected_model: dsl.Output[dsl.Model],
        evaluation: dsl.Output[dsl.Metrics],
    ):
        return dsl.ContainerSpec(
            image=component_image,
            command=["python", "-m", "cogniflow_data.kfp_tasks", "evaluate"],
            args=[
                "--dataset", dataset.path,
                "--manifest", dataset_manifest.path,
                "--models", candidate_models.path,
                "--validation", validation_metrics.path,
                "--output-model", selected_model.path,
                "--output-evaluation", evaluation.path,
            ],
        )

    @dsl.container_component
    def register_candidate_component(
        dataset_manifest: dsl.Input[dsl.Artifact],
        selected_model: dsl.Input[dsl.Model],
        evaluation: dsl.Input[dsl.Metrics],
        tracking_uri: str,
        experiment: str,
        model_name: str,
        pipeline_run_id: str,
        registration: dsl.Output[dsl.Artifact],
    ):
        return dsl.ContainerSpec(
            image=component_image,
            command=["python", "-m", "cogniflow_data.kfp_tasks", "register"],
            args=[
                "--manifest", dataset_manifest.path,
                "--model", selected_model.path,
                "--evaluation", evaluation.path,
                "--output", registration.path,
                "--tracking-uri", tracking_uri,
                "--experiment", experiment,
                "--model-name", model_name,
                "--pipeline-name", PIPELINE_NAME,
                "--pipeline-run-id", pipeline_run_id,
                "--component-image", component_image,
            ],
        )

    @dsl.container_component
    def record_provenance_component(
        dataset_manifest: dsl.Input[dsl.Artifact],
        evaluation: dsl.Input[dsl.Metrics],
        registration: dsl.Input[dsl.Artifact],
        pipeline_run_id: str,
        provenance: dsl.Output[dsl.Artifact],
    ):
        return dsl.ContainerSpec(
            image=component_image,
            command=["python", "-m", "cogniflow_data.kfp_tasks", "provenance"],
            args=[
                "--manifest", dataset_manifest.path,
                "--evaluation", evaluation.path,
                "--registration", registration.path,
                "--output", provenance.path,
                "--pipeline-name", PIPELINE_NAME,
                "--pipeline-run-id", pipeline_run_id,
                "--component-image", component_image,
            ],
        )

    def secure(task):
        task.set_caching_options(False).set_cpu_limit("1").set_memory_limit("2Gi")
        task.set_cpu_request("250m").set_memory_request("512Mi")
        kubernetes.set_image_pull_policy(task, "IfNotPresent")
        kubernetes.set_security_context(task, run_as_user=10001, run_as_group=10001)
        kubernetes.set_timeout(task, 600)
        return task

    @dsl.pipeline(name=PIPELINE_NAME, description="Validated synthetic-proxy candidate training")
    def pipeline(
        feature_uri: str,
        label_uri: str,
        feature_manifest_uri: str,
        git_revision: str,
        training_cutoff: str,
        mlflow_tracking_uri: str,
        mlflow_experiment: str = "cogniflow-module3-kfp",
        mlflow_model_name: str = "cognitive-load-classifier-kfp",
    ):
        feature_import = dsl.importer(artifact_uri=feature_uri, artifact_class=dsl.Dataset)
        label_import = dsl.importer(artifact_uri=label_uri, artifact_class=dsl.Dataset)
        manifest_import = dsl.importer(artifact_uri=feature_manifest_uri, artifact_class=dsl.Artifact)
        validate = secure(
            validate_inputs_component(
                features=feature_import.output,
                labels=label_import.output,
                feature_manifest=manifest_import.output,
                git_revision=git_revision,
            )
        )
        prepare = secure(
            prepare_dataset_component(
                features=feature_import.output,
                labels=label_import.output,
                feature_manifest=manifest_import.output,
                validation=validate.outputs["validation"],
                training_cutoff=training_cutoff,
                git_revision=git_revision,
            )
        )
        train = secure(
            train_candidates_component(
                dataset=prepare.outputs["dataset"],
                dataset_manifest=prepare.outputs["dataset_manifest"],
            )
        )
        evaluate = secure(
            evaluate_select_component(
                dataset=prepare.outputs["dataset"],
                dataset_manifest=prepare.outputs["dataset_manifest"],
                candidate_models=train.outputs["candidate_models"],
                validation_metrics=train.outputs["validation_metrics"],
            )
        )
        register = secure(
            register_candidate_component(
                dataset_manifest=prepare.outputs["dataset_manifest"],
                selected_model=evaluate.outputs["selected_model"],
                evaluation=evaluate.outputs["evaluation"],
                tracking_uri=mlflow_tracking_uri,
                experiment=mlflow_experiment,
                model_name=mlflow_model_name,
                pipeline_run_id=dsl.PIPELINE_JOB_ID_PLACEHOLDER,
            )
        )
        secure(
            record_provenance_component(
                dataset_manifest=prepare.outputs["dataset_manifest"],
                evaluation=evaluate.outputs["evaluation"],
                registration=register.outputs["registration"],
                pipeline_run_id=dsl.PIPELINE_JOB_ID_PLACEHOLDER,
            )
        )

    return pipeline
