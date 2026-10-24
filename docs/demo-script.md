# Demo Script (5–10 minutes)

No video has been recorded for this submission. This script exists so a demo
can be recorded later without re-deriving the walkthrough; it does not claim
a recording exists. Add the link to `README.md` and
`docs/submission_checklist.md` once one does.

Note: several steps below (HPA scaling, KServe scale-to-zero, live
Grafana/Tempo/Loki panels) require a real GKE deployment following
`docs/cloud-deployment.md` — do not claim these worked on camera unless they
were actually run against a live cluster first.

1. **Introduce the problem and disclaimer** (30s): synthetic cognitive-load
   classifier; explicitly state it is not a medical/psychological/monitoring
   system (see `docs/responsible-use.md`).
2. **Repository structure** (30s): walk `README.md`'s repository-structure
   section.
3. **Four notebooks** (1m): open `notebooks/01_eda.ipynb` →
   `04_prepare_for_deployment.ipynb`, show each one's purpose in ~15s.
4. **EDA highlights** (30s): class distribution, feature correlations.
5. **Data processing** (30s): train/test split, feature engineering.
6. **Model evaluation** (1m): show `reports/metrics.json` — accuracy vs.
   majority-class baseline, confusion matrix. State plainly that the label
   is synthetic-rule-derived (see `docs/model-card.md`), not clinically
   validated.
7. **MLflow** (30s): `mlflow ui` (or the run registered by CI) — experiment,
   run params/metrics, registered model version.
8. **DVC** (30s): `dvc dag`; run `dvc repro` twice to show the second run
   reports no changes (reproducibility).
9. **Pytest + coverage** (30s): `uv run pytest src/tests --cov=... --cov-fail-under=80` — show the passing count and coverage percentage live, don't state a number from memory.
10. **CI test → build structure** (30s): open the GitHub Actions run for the
    latest push; show `test` gating `build`.
11. **Manual deploy control** (15s): show the `deploy` job requires
    `workflow_dispatch`.
12. **Terraform** (30s): `terraform -chdir=infra/terraform/gke validate`.
13. **Helm** (30s): `helm lint` / `helm template` output.
14. **NGINX auth** (30s, cloud only): unauthenticated request → 401;
    authenticated request → 200. Do not show the real password on screen.
15. **FastAPI prediction** (30s): `curl .../predict` and `.../model-info`.
16. **HPA** (cloud only, if actually run): `kubectl get hpa -n cognitive-load`
    before/after generated load.
17. **KServe** (cloud only, if actually installed and run): a prediction via
    the `InferenceService`, then scale-to-zero behavior if genuinely
    observed — do not claim this without having watched pod count reach 0
    and a subsequent cold-start request succeed.
18. **Prometheus/Grafana** (cloud/local-compose only, if actually started):
    show the dashboard with live traffic.
19. **Evidently** (30s): open `reports/evidently/data_drift.html` in a
    browser.
20. **Tempo** (cloud/local-compose only, if actually started): a trace for
    one `/predict` request.
21. **Loki** (cloud/local-compose only, if actually started): a log line
    correlated with the trace ID above.
22. **Final PR** (15s): show the PR into `main` containing this work.

Total: adjust step count actually recorded to whichever of the cloud/local
observability steps were genuinely run — skip narrating steps that weren't
executed rather than describing them as if they happened.
