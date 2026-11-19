# C20 MLflow runtime

Build the tracking server from the pinned inputs:

```sh
docker build -t cogniflow-mlflow:c20 deploy/c20/mlflow
```

The qualified local OCI identity is
`sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5`.
Rebuilding may produce another identity; scan and test that exact result before
changing the deployment manifest. The server requires
`MLFLOW_BACKEND_STORE_URI` and `MLFLOW_ARTIFACTS_DESTINATION`, runs as UID/GID
65532, and contains no remote signature or attestation.
