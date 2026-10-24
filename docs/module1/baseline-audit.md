# Module I baseline audit

Baseline captured 2026-10-23 on `feature/cogniflow-module1-foundation`, before source changes. The worktree was clean at commit `0658ce2`.

| Requirement | Existing evidence | Defect found | Implemented fix | Verification |
|---|---|---|---|---|
| Tests | 36 tests collected | Suite stalled in the first API test; coverage unavailable | Compatible FastAPI pin, non-threaded ASGI test transport, preloaded demo HTML | 42 passed, 88.41% |
| Lint/type safety | Ruff and mypy configured | Ruff: 2 errors; mypy: 14 errors | Import cleanup and shared typed feature contract | Ruff passes; mypy remains advisory |
| Data lineage | DVC stages existed | S3 `CHANGE_ME`, no parameter dependencies, time-varying data | Local remote, wired params, seeded fixed dates | Two `dvc repro` runs; second fully cached |
| Modeling | Random Forest + MLflow | random split, only accuracy, synthetic rule labels presented too strongly | chronological split, dummy/logistic/RF comparison, macro-F1/recall/confusion matrix, provenance/hash | MLflow run and registered version recorded |
| Serving | FastAPI and three implicit fallbacks | KServe outage silently changed predictor | explicit `demo_rule`, `local_model`, `kserve`; fail closed; provenance | negative-path tests pass |
| Drift | Evidently with plausible HTML fallback | fallback could appear successful | real Evidently output or nonzero failure | DVC drift stage passed |
| Helm | lint/template passed | committed demo credential and mutable defaults | external Secret reference, local/GKE overrides | lint/template checks |
| Terraform | GKE source present | two fmt failures; provider download blocked in sandbox | formatting corrected when safe | validation deferred pending provider access |

The smallest coherent path was to centralize the six-feature contract, make inference selection explicit, reuse the existing FastAPI/DVC/MLflow/Helm structure, and add no frontend framework.
