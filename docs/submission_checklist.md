# FSDS Submission Checklist

Use this checklist before sending the GitHub Pull Request link.

## Required code artifacts

- [x] Python FastAPI pre/post-processing API
- [x] Pytest tests
- [x] Coverage gate above 80%
- [x] Dockerfile
- [x] GitHub Actions CI/CD with test, build, and manual deploy
- [x] Helm chart
- [x] Kubernetes Deployment, Service, HPA, Ingress
- [x] NGINX basic authentication annotations
- [x] KServe InferenceService with min scale 0
- [x] Prometheus metrics endpoint
- [x] Grafana dashboard configuration
- [x] Loki logging configuration
- [x] Tempo tracing configuration
- [x] Evidently drift report script
- [x] MLflow training/registration script
- [x] DVC pipeline
- [x] Terraform GKE infrastructure
- [x] Four required notebooks

## Things you must customize after pushing to GitHub

- [ ] Replace `OWNER/REPO` image placeholders in Helm values or pass values from CI.
- [ ] Replace `cognitive-load.example.com` with your real domain or demo host.
- [ ] Replace `gs://CHANGE_ME_BUCKET/...` with your actual model bucket path.
- [ ] Replace `.dvc/config` remote with your real DVC remote.
- [ ] Add GitHub secrets for GKE, KServe storage URI, host, and MLflow.
- [ ] Replace demo basic-auth password with a new generated `htpasswd` value.
- [ ] Create a feature branch and PR into `main`.
- [ ] Paste the real PR link into the README.

## Minimal demo commands

```bash
make install
make test
make run
```

In another terminal:

```bash
bash scripts/local_smoke_test.sh
```

Docker:

```bash
docker build -t cognitive-load-api:local .
docker run --rm -p 8000:8000 cognitive-load-api:local
```

Helm render check:

```bash
helm template cognitive-load-monitor ./helm/cognitive-load-monitor --namespace cognitive-load
```
