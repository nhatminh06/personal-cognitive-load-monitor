# Module I rubric matrix

Statuses are evidence levels, not implementation guesses. A rendered manifest
is never runtime proof.

| Requirement | Status | Exact evidence | Remaining acceptance |
|---|---|---|---|
| Python, FastAPI preprocessing/postprocessing | Locally runtime verified + CI verified | authenticated six-feature `/predict`, bounded schemas, explicit backend/provenance, fail-closed tests | Repeat through the cloud gateway and approved KServe backend |
| Pytest strictly above 80% | CI verified | repository coverage gate is `--cov-fail-under=81` | Preserve the required check on the merge commit |
| Test-success automatic image build | CI verified | main-push `build` needs `test`; immutable commit tag published to GHCR | Educational image only; not an approved production release |
| Manual deployment | Statically verified | dispatch-only protected `production` and `module1-production` jobs, OIDC, main-only guards | Configure environment reviewers/runner and execute only with authorization |
| Helm on cloud Kubernetes | Statically verified | digest-pinned GKE render, private GKE Terraform and scoped identities | Authorized plan/apply, install, rollback and teardown evidence |
| FastAPI HPA | Statically verified | autoscaling/v2 targets the API Deployment; requests, limits and explicit bounded behavior render | Metrics Server plus observed 2→N→2 scaling under bounded load |
| KServe custom `.skops` runtime | Locally runtime verified + statically verified | KServe 0.20 server contract, six features, immutable image/model lineage and fail-closed loader | Approved model and cloud `InferenceService Ready=True` |
| KServe scale-to-zero | Blocked after compatibility qualification | separate Knative overlay sets KPA concurrency and min-scale 0; Standard remains default; `compatibility-matrix.json` rejects both upstream dependency sets | Qualify the exact supported candidate in isolation, then observe 1→0→1 and cold-start prediction |
| NGINX gateway authentication/TLS | Locally runtime verified + statically verified | local 401/200 proof; production Ingress requires Basic Auth Secret and TLS | Cloud certificate, 401/200 and backend-bypass checks |
| Prometheus/Grafana | Locally runtime verified | live scrape and provisioned dashboard evidence | Hosted target and dashboard capture |
| Loki logging | Locally runtime verified | structured request log queried without payload/credential fields | Hosted request/log correlation and redaction evidence |
| Tempo tracing | Locally runtime verified | API trace IDs returned by Tempo search | Hosted request-to-trace correlation |
| Evidently drift | Locally runtime verified | DVC-produced `reports/evidently/data_drift.html` | Record exact reference/current dataset metadata for final run |
| MLflow + DVC provenance | Locally runtime verified | exact candidate version/tree digest, dataset digest and `.skops` packaging gates | Candidate is still unapproved; GCS/registry round trip is pending |
| Four notebooks | Locally runtime verified | EDA, processing, modeling and deployment-preparation notebooks executed | Clean-environment replay for final submission |
| Detailed README/evidence guide | Implemented | README plus `final-acceptance.md` and evidence schema | Fill only from an authorized cloud run |

Module I is source-ready, not runtime-complete. Cloud Kubernetes, protected
manual deployment, live HPA, Knative scale-to-zero and approved-model serving
remain blocked pending explicit authorization and the compatibility decision in
[`final-acceptance.md`](final-acceptance.md).
