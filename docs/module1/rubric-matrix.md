# Module I grading matrix

| Requirement | Actual evidence | Status |
|---|---|---|
| Reproducible Python/data pipeline | seeded data, locked dependencies, DVC twice cached | verified locally |
| Four executable notebooks | all cells executed, no error outputs | verified locally |
| Honest evaluation | chronological split, dummy/model/rule comparison, synthetic-proxy warning | verified locally |
| MLflow registry | version 4 READY, exact run `f701a0a…`, deployment parity | verified locally |
| Shared feature contract | `FEATURE_NAMES` + `feature_vector` used by training/serving/notebooks | verified locally |
| FastAPI/provenance | bounded schemas, `/model-info`, explicit backend and version | verified locally |
| No silent production fallback | failure tests return 5xx; responses state `is_fallback=false` | verified locally |
| Pytest >80% | 42 passed, 88.41% | verified locally |
| Ruff / type checks | both passed | verified locally |
| Docker | image `39143ed8c76f`, demo and real-model smoke tests | verified locally |
| Prometheus/Grafana | live scrape plus provisioned metric/log/trace dashboard | verified locally |
| Loki structured logging | live JSON `/predict` ingestion query | verified locally |
| Tempo tracing | live service trace search returned trace IDs | verified locally |
| NGINX authentication | local runtime: unauthenticated 401, authenticated 200 | verified locally |
| Evidently drift | genuine DVC-produced HTML report | verified locally |
| Helm/manifests | lint, three renders, YAML parse | static verified |
| Terraform | fmt and validate | static verified; no apply |
| KServe/HPA/scale-to-zero | manifests render; no safe local cluster capacity | runtime unavailable |
| CI test → build → manual deploy | dependency/gate review only | remote deferred |
| GKE/cloud deployment | prohibited for this task | cloud deferred |
| UI accessibility/responsiveness | semantic markup and states reviewed; no browser engine | partial/manual QA pending |
| Graphify | 281 nodes, 419 edges, 24 communities and impact traversal | code graph verified; semantic labels unavailable |
| Credential hygiene | scan clean; auth secret external | verified locally |
