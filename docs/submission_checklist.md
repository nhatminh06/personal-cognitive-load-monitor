# FSDS Submission Checklist

See [`requirement-matrix.md`](requirement-matrix.md) for the full,
evidence-backed status of every grading criterion. This file is the
process checklist for submitting the assignment.

## Required code artifacts

- [x] Python FastAPI pre/post-processing API
- [x] Pytest tests (70 passed, 99.22% coverage — measured this pass)
- [x] Coverage gate above 80%
- [x] Dockerfile
- [x] GitHub Actions CI/CD with test, build, and manual deploy (job-scoped
      least-privilege permissions)
- [x] Helm chart (`helm lint` / `helm template` verified)
- [x] Kubernetes Deployment, Service, HPA, Ingress
- [x] NGINX basic authentication annotations
- [x] KServe InferenceService with min scale 0 (annotation present; not
      execution-verified — see requirement matrix item 14)
- [x] Prometheus metrics endpoint
- [x] Grafana dashboard configuration
- [x] Loki logging configuration
- [x] Tempo tracing configuration
- [x] Evidently drift report script (verified to produce real Evidently
      output, not a silent fallback table)
- [x] MLflow training/registration script (verified: model genuinely pulled
      from MLflow in CI before the Docker build)
- [x] DVC pipeline (verified reproducible: two `dvc repro` runs, second
      reports no changes)
- [x] Terraform GKE infrastructure (`fmt`/`init`/`validate` pass; never
      applied — no cloud credentials in this environment)
- [x] Four required notebooks (valid JSON/nbformat, contain real executed
      output; not re-executed top-to-bottom this pass)
- [x] LICENSE (MIT)
- [x] Model card, data card, responsible-use notice

## Things that still require your own action

- [ ] Replace `OWNER/REPO` image placeholders in Helm values or pass values
      from CI (the default already points at
      `ghcr.io/OWNER/REPO/cognitive-load-api` — set to your real repo).
- [ ] Replace `cognitive-load.example.com` with your real domain or demo
      host (or use nip.io — see `docs/cloud-deployment.md`).
- [ ] Replace `gs://CHANGE_ME_BUCKET/...` with your actual model bucket path
      (only needed if you enable KServe).
- [ ] Replace `.dvc/config`'s placeholder remote with your real DVC remote
      before running `dvc push`.
- [ ] Add GitHub secrets for GKE, KServe storage URI, host, and MLflow if you
      want the `workflow_dispatch` deploy job to work.
- [ ] Replace the demo basic-auth password with a new generated `htpasswd`
      value before any real deployment.
- [ ] Actually run `docs/cloud-deployment.md` against a real GCP project if
      you want the cloud-only requirement-matrix items to move from
      "statically validated" / "blocked by environment" to "verified."
- [ ] Record a demo video (optional) using `docs/demo-script.md` and link it
      in the README once it exists.

## PR link

```text
PR: https://github.com/nhatminh06/personal-cognitive-load-monitor/pull/3
```

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

Docker (not verified this pass — no Docker daemon available):

```bash
docker build -t cognitive-load-api:local .
docker run --rm -p 8000:8000 cognitive-load-api:local
```

Helm render check:

```bash
helm template cognitive-load-monitor ./helm/cognitive-load-monitor --namespace cognitive-load
```
