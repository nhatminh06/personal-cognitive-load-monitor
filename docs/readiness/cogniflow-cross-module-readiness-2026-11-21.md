# CF-R1 — Cross-module readiness and engineering roadmap (2026-11-21)

## A. Executive summary

**Decision: READY_FOR_NEXT_MILESTONE.** CogniFlow has qualified local pieces, but neither module has a current, security-cleared end-to-end deployment. The best next milestone is a bounded **Kafka → Flink → Redis recovery and correctness implementation**: it improves a real independent path while Spark remains deferred. This is a roadmap decision based on existing evidence; no runtime or security check was run for CF-R1.

## B. Repository baseline

Branch `main`; HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. The working tree already contained edits to `Makefile`, `jobs/internal_job_runner.py`, `src/tests/test_airflow_cold_start.py`, and `src/tests/test_internal_job_runner.py`, plus untracked Module II reports, an analytics test, and a Parquet fixture. Those changes and all ignored evidence were preserved. CF-R1 writes only this report.

Implemented paths include API/preprocessing, session/event handling, training/KFP components, model serving, Kubernetes/Helm/GKE configuration, and Module II Kafka, object storage, Airflow, Spark/Delta, Trino/dbt, Flink, and Redis components. [Architecture](../architecture.md) depicts the intended cross-module flow; its arrows are design, not proof of a qualified deployment. [Evidence index](../evidence.md) records older local batch and streaming rehearsals. The newer [Spark deferral decision](../security-audit/module2-m2-s1e-spark-deferral-closeout-2026-11-21.md) supersedes any interpretation that the old batch rehearsal authorizes current Spark use. Likewise, the earlier [Module I pre-cloud report](../module1/precloud-readiness.md) describes runner security as pending; the later [C5.8 runner report](../security-audit/c58-final-runner-qualification.md) qualifies the local image with 0 HIGH/0 CRITICAL, while publication and deployment remain gated. These documents have different dates and scopes, rather than equivalent current status.

## C. Module I readiness matrix

| Area | Evidence-backed status | Missing acceptance / limitation |
| --- | --- | --- |
| API and preprocessing | Offline source, bounded schema and failure-mapping checks passed in the [pre-cloud review](../module1/precloud-readiness.md). | Hosted TLS/auth, HPA 2→N→2, and backend-bypass behavior need an authorized runtime. |
| Training, evaluation and registry | [C23 six-component image](../course-completion/c23-kfp-component-qualification.md) passed isolated local commands with a synthetic 180-row fixture and 0 HIGH/0 CRITICAL; exact MLflow model retrieval has offline checks. | A real KFP-generated run identity, model approval and registry round trip remain unqualified. Synthetic performance does not establish model validity. |
| KServe, Knative and Kubernetes | Manifests and Helm/Terraform have offline checks; a [local kind evidence packet](../module1/qualification-evidence-review.md) describes synthetic scale-to-zero behavior. | Independent review is pending, compatibility matrix is BLOCKED, and exact controller/predictor digests lack preserved vulnerability scans, SBOMs and signatures. [Isolated qualification](../module1/isolated-qualification.md) does not establish a qualified controller/workload candidate. |
| CI/CD and deployment runner | [C5.8](../security-audit/c58-final-runner-qualification.md) locally qualified the exact runner image, non-root behavior, attestations and offline runtime at 0 HIGH/0 CRITICAL. | Registry publication, signature/SBOM association, immutable deployed digest, runner registration and Kubernetes mutation require separate gates and authorization. The old general “runner security pending” baseline is stale for this exact local image. |
| DVC, observability and cloud | DVC lineage drift is explicitly BLOCKED in the pre-cloud review; metrics/logging/tracing source exists and older local evidence is cited. | Reference/current drift replay, hosted correlation, GKE capacity/IAM/budget, rollback and real deployment are not proven. Cloud is NOT QUALIFIED. |

## D. Module II readiness matrix

| Area | Evidence-backed status | Missing acceptance / limitation |
| --- | --- | --- |
| Kafka and SeaweedFS Bronze | [Local checkpoint](../security-audit/module2-local-checkpoint-2026-11-21.md) records patched Kafka image at 0 HIGH/0 CRITICAL and seven preserved topics; older [evidence index](../evidence.md) records ingestion. | No current security-cleared full batch path. SeaweedFS equivalence to the course MinIO requirement remains unresolved in [README](../../README.md). |
| Airflow | [Independent qualification](../security-audit/module2-independent-airflow-qualification-2026-11-21.md): PASS for six-task local orchestration against mocks. | Mock Spark calls are not Spark execution or full integration. |
| Spark/Delta and S3A | [M2-S1E](../security-audit/module2-m2-s1e-spark-deferral-closeout-2026-11-21.md): BLOCKED and DEFER_SPARK_ENFORCED. Spark 3.5.5 had 152 HIGH/5 CRITICAL; 3.5.9 had 525/22; 4.2.1 had 579/24. Separate S3A closure had 15/1. | No real Spark execution is qualified. Direct Docker operators can bypass the application runner guard; this is a documented residual risk. |
| Trino/dbt and data quality | [Independent analytics qualification](../security-audit/module2-independent-trino-dbt-qualification-2026-11-21.md): PASS for local synthetic data, seven models, eight tests, repeat MERGE and persistence. | Does not prove Spark-produced Silver, true end-to-end lineage or production-sized correctness. |
| Flink and Redis | [Local checkpoint](../security-audit/module2-local-checkpoint-2026-11-21.md) records a bounded smoke run with duplicate and stale-write behavior; [older streaming evidence](../evidence.md) records wider isolated rehearsals and checkpoint restoration. | Checkpoint recovery was not retested in the newer checkpoint; zero-valued REST counters in older evidence remain unexplained. No current whole-path security or production claim follows. |
| Offline reproducibility and resources | [M2-S2D](../security-audit/module2-m2-s2d-clean-install-reproducibility-2026-11-21.md): fresh Python 3.11 install, 29 offline tests, scoped MyPy/Ruff and Compose parse passed. | No new image vulnerability scan, live service run, or representative load/resource acceptance in that milestone. Full Module II remains UNVERIFIED. |

## E. Security and operations findings

| Severity / type | Finding and impact | Boundary |
| --- | --- | --- |
| Critical blocker, confirmed | Spark and required S3A closure exceed the zero HIGH/CRITICAL gate; batch Silver and full Module II cannot be qualified. | [M2-S1E](../security-audit/module2-m2-s1e-spark-deferral-closeout-2026-11-21.md). No exception or scan relaxation. |
| High blocker, confirmed evidence gap | Module I controller/predictor exact digests have no retained whole-image scan, SBOM or signature in the independent review; privileged Istio CNI and broad upstream AuthorizationPolicies need review. | [Module I evidence review](../module1/qualification-evidence-review.md); this is missing proof, not an asserted CVE count. |
| High release gate, confirmed | Local runner and KFP image passes do not prove remote registry provenance, deployed digest, credentials or model approval. | [C5.8](../security-audit/c58-final-runner-qualification.md), [C23](../course-completion/c23-kfp-component-qualification.md). |
| Operational risk, confirmed | DVC manifest revision drift blocks the pre-cloud matrix; GKE prerequisites/capacity and runtime recovery remain unproven. | [Pre-cloud review](../module1/precloud-readiness.md). |
| Operational verification gap | Streaming checkpoint restoration has historical evidence, but the latest bounded smoke did not retest it; older REST counters are unexplained. | [Evidence index](../evidence.md), [local checkpoint](../security-audit/module2-local-checkpoint-2026-11-21.md). |

Controls visible in the reports include non-root containers, bounded resources, authenticated runners, immutable image references and fail-closed Spark runner behavior. Their scopes differ; none establishes complete secret rotation, hosted observability, cloud IAM, disaster recovery or production supply-chain integrity. Those are future verification items, not new findings from a live audit.

## F. Engineering gap analysis

The largest functional gap is the blocked Spark/Delta Silver producer; independent dbt and Airflow passes cannot bridge it. The independently operable Kafka/Flink/Redis path has a concrete recovery/correctness gap with a feasible local acceptance test. Module I has local source and image evidence but still needs independent image review and genuine KFP/KServe runtime qualification before cloud. Avoid simply increasing test counts or repeating already qualified synthetic checks; target failure modes and contracts.

## G. Prioritization matrix

Scale: **5 is more impact, security importance, portfolio value, feasibility, or independence**. For maintenance burden and complexity, **5 means more costly**. Scores are planning estimates, not measured effort; `*` marks the most uncertain estimates. Rows cover meaningful unfinished work, including blocked paths.

| Candidate | Impact | Security | Research | Feasible | Independent | Burden | Complexity | Evidence / main uncertainty |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Streaming recovery and correctness implementation | 4 | 3 | 4 | 4* | 5 | 2* | 3* | Existing local smoke and older checkpoint evidence; host capacity for bounded repeat needs preflight. |
| Module I exact-digest KServe/controller security and local contract closure | 4 | 5 | 4 | 3* | 5 | 3* | 4* | Missing digest evidence and reviewer decision; local cluster capacity uncertain. |
| Local headless KFP training runtime qualification | 4 | 3 | 5 | 2* | 4 | 4* | 4* | C23 image works in isolation; KFP dependency/resource constraints remain. |
| DVC lineage reconciliation and reproducible model artifact replay | 3 | 2 | 3 | 4* | 5 | 2 | 2* | Known revision drift; model/data governance approval may constrain any mutation. |
| Deployment runner registry/publication gate | 4 | 5 | 3 | 2 | 4 | 4* | 4* | Local image pass exists; remote writes/credentials require explicit authorization. |
| Spark secure runtime and full batch integration | 5 | 5 | 5 | 1 | 1 | 5* | 5* | Multiple failed image gates and unresolved dependency closure. |
| GKE/Kubernetes production qualification | 5 | 5 | 4 | 1 | 2 | 5* | 5* | Cloud authorization, capacity, image and model gates remain. |

## H. Recommended next milestone

**M2-S3A — Independent streaming recovery and online-feature correctness.** Objective: make the existing Kafka → Flink → Redis branch recover predictably from an isolated Flink restart, and make correctness observable. Scope: source/event contract, checkpoint state, duplicate/stale-event handling, Redis persistence, quarantine/DLQ and bounded metrics; modify only defects demonstrated by a failing acceptance case. Prerequisites: preserve existing Docker resources and image identities; local resource preflight and isolated test-owned network/volumes; retain the existing zero HIGH/CRITICAL image gate. Outline: establish baseline invariants from current code and evidence, inject unique/duplicate/late events, restart only test-owned Flink, compare pre/post checkpoint state and Redis values, inspect DLQ and metrics, fix the smallest confirmed defect, then run focused regressions. Acceptance: exact expected totals/offsets, no duplicate inflation or stale overwrite, recovery from a recorded checkpoint, no lost/extra event, explainable counters, persisted state and bounded resource measurements with raw evidence. Complexity **3/5 estimate**; environment: local isolated Docker only. Prohibited: Spark startup/build/scan, production topics or volumes, retained clusters, cloud/Kubernetes writes, security exceptions and publication. A local streaming pass would not qualify full Module II.

This comes first because it advances an actual data path with an observable failure/recovery contract and avoids all known Spark/cloud blockers. Its acceptance is stronger than repeating an earlier smoke test: the work must diagnose the counter gap and demonstrate restart invariants against current source.

## I. Short- and medium-term roadmap

**Priority 2 — Module I exact-digest KServe/controller security and local contract closure.** Objective: close the specific evidence gap before considering a qualified local serving candidate. Scope: provenance, SBOM/signature and whole-image scans for each exact required digest, controller/privilege policy review, and independent review of the preserved synthetic local contract. Prerequisites: approved immutable inventory and adequate isolated host resources. Outline: verify artifact identities, scan exact images under the existing gate, resolve findings without exceptions, check compatibility/privileged boundaries, then seek reviewer decision; perform bounded runtime checks only after security passes. Acceptance: every required digest has attributable 0 HIGH/0 CRITICAL evidence, policy review disposition, reviewer sign-off and clearly scoped local runtime result. Complexity **4/5 estimate**; environment: local isolated build/scan and, after gate, disposable Kubernetes. Prohibited: mutation of retained clusters, GCP, registry publication, model approval, or production deployment. If upstream images cannot meet the gate, stop with BLOCKED.

**Priority 3 — Local headless KFP training runtime.** Objective: prove the six-component compiled pipeline under a supported, resource-bounded local KFP control plane. Scope: exact C23 component, run identity, task artifacts, failure/retry behavior and candidate-only MLflow registration. Prerequisites: dependency compatibility, control-plane image security and host capacity; retain source/YAML synchronization. Outline: verify immutable images and dependencies, provision disposable local KFP, execute deterministic synthetic pipeline, reconcile task outputs and clean up only task-owned resources. Acceptance: genuine KFP-generated run ID, six successful steps, reproducible artifacts, explicit candidate-only status, failure-path evidence and resource envelope. Complexity **4/5 estimate**; environment: local disposable Kubernetes, no cloud. Prohibited: model approval, registry publication, retained cluster mutation, Spark, and production deployment. Stop if security or capacity gates fail.

Short term: M2-S3A, then Module I digest security closure; DVC lineage reconciliation can run independently when ownership is clear. Medium term: bounded KFP runtime and release-provenance work after their gates. No milestone here authorizes the environment it proposes to use; each starts with its own resource and security preflight.

## J. Deferred work and reopening conditions

Spark stays **BLOCKED** until an upstream/vendor-supported compatible runtime and full S3A/Delta dependency closure have verified provenance, zero HIGH/CRITICAL across image and external artifacts, resolved duplicate/shaded libraries and a separately approved security qualification. Only then may a distinct functional Spark qualification begin. Full Module II remains **UNVERIFIED**. GKE and production remain **NOT QUALIFIED / NOT READY** until owner authorization, capacity/budget/IAM, exact image and model provenance, hosted security controls, rollback and runtime acceptance are proven. Runner publication and model approval need explicit owner authorization.

## K. Evidence references and limitations

Primary current records: [M2-S2D](../security-audit/module2-m2-s2d-clean-install-reproducibility-2026-11-21.md), [M2-S1E](../security-audit/module2-m2-s1e-spark-deferral-closeout-2026-11-21.md), [Module II local checkpoint](../security-audit/module2-local-checkpoint-2026-11-21.md), [C5.8](../security-audit/c58-final-runner-qualification.md), [C23](../course-completion/c23-kfp-component-qualification.md), [Module I evidence review](../module1/qualification-evidence-review.md), [pre-cloud review](../module1/precloud-readiness.md), and [evidence index](../evidence.md). Reports were read as repository records, not independently replayed during CF-R1. No fresh vulnerability scan, test suite, runtime, container, Kubernetes or cloud result is claimed. Untracked reports and ignored raw artifacts are local evidence and must be preserved by the owner before any clean checkout or publication.
