# Deployment and release

## Authorization boundary

No project name, time window or budget threshold authorizes deployment. Before any
cloud action, the owner must approve the exact commit, project, billing account,
region, Terraform plan, image ledger, model decision and teardown procedure. Never
run Terraform apply/destroy, publish images, create registry credentials or mutate
a cluster from an ordinary verification run.

The candidate project is `pnm-cognitive-load`; the planning assumptions are an
eight-hour window and a $15 budget-alert threshold. Alerts do not cap spend.

## Release order

1. Re-run tests, coverage, Ruff, MyPy, Helm, schema, Terraform and secret checks.
2. Publish each locally qualified image through an authorized bootstrap path.
3. Verify the registry linux/amd64 manifest digest; scan the exact identity with
   zero HIGH/CRITICAL tolerance, then sign and attest it.
4. Review a backend-enabled Terraform plan. Apply only after explicit approval.
5. Install platform dependencies and storage classes, then KFP/MLflow. Validate
   MySQL, MLMD, GCS and pipeline health before considering model serving.
6. Obtain separate model approval before packaging or deploying KServe.
7. Deploy one ephemeral runner for one authorized job; remove its token, Pod and
   GitHub registration afterward.
8. Record workloads, PVC/PV reclaim policy, image identities, GCS generations,
   costs and teardown evidence.

Stop on an unexpected project, unprotected branch, mutable image tag, failed
signature/scan, unresolved placeholder, capacity mismatch, missing budget alert or
unapproved model.

## Capacity

The 73-object headless KFP render contains ten steady workload Pods requesting
884m CPU and 3,164 MiB. One concurrent serialized pipeline Pod adds 475m and
1,088 MiB, for a 1,359m / 4,252 MiB peak. MySQL and SeaweedFS each require a 20
GiB RWO PVC. Two `e2-standard-4` nodes provide a conservative post-reserve budget
of 6,400m and 26,214 MiB; place the two RWO workloads on separate nodes. Exact
figures live in `deploy/gke/resource-budget.yaml`.

Release and deployment runners are sequential. Their bounded writable storage is
15 GiB and 6 GiB respectively. Runner manifests keep registry placeholders until
publication succeeds.

## Local-only qualification

The GCS-capable MLflow image and deployment runner each passed local whole-image
Trivy scans at 0 HIGH / 0 CRITICAL. The runner local index is
`sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a`;
its runtime manifest is
`sha256:3aab5b8fe68d83df3608c6cb1f7b3c1b02798643c068345344a56b8816b2b182`.
These are not remote registry references.

Both locally qualified images passed the `0 HIGH/CRITICAL` release gate.

For local Kubernetes use, follow the Makefile targets and keep Module I and Module
III release ownership separate. Never deploy the restricted Spark image.

## First GKE release candidate — blocked handoff

The source baseline is merged main `64e2bb692a4d663b335322876f65b0c887a68594`.
The required application path is authenticated FastAPI → approved KServe model →
sanitized Knative Broker/Trigger → persistent consumer and anomaly detector; KFP
uses MySQL, ML Metadata, MLflow and artifact storage. Terraform supplies GKE,
Artifact Registry, GCS, networking and Workload Identity. Kafka/Flink/Redis and
Spark/Delta/Trino retain their isolated local evidence; SEC-022 Spark is never a
GKE image. The exact local KFP image IDs are in
`deploy/releases/kfp-local-images.json`; these are **not** registry digests.

| Gate | Current evidence | Required release input |
|---|---|---|
| Isolated integration | Historical KFP and Knative runs are dated 2026-10-26; hardened anomaly and current approved-model serving have no integrated run | Use an authorized isolated host with at least 12 GiB available RAM and 60 GiB free disk; run the C11 acceptance with the current images and record real run IDs, migrations, readback, Broker delivery, alert/recovery and rejected inputs |
| Controller compatibility | `deploy/c11/controller-compatibility.json` remains `BLOCKED`; GKE 1.35 regional availability and actual node allocatable are unverified | Select supported exact GKE/KServe/Knative/Istio/cert-manager/KFP versions, qualify controller images, check regional version availability and node allocatable on the authorized target |
| Image supply chain | Local linux/amd64 IDs and selected local SBOM/Trivy reports exist; no complete signed remote ledger | Publish every required image only after authorization, resolve each registry manifest digest, run current whole-image zero HIGH/CRITICAL scans, and attach digest-bound SPDX and SLSA attestations verified by `scripts/c11_runtime_preflight.py` |
| Model | The synthetic candidate remains unapproved | Owner reviews exact model version, run, dataset and artifact hashes; no KServe model image or manifest is released before separate approval |
| GKE render | `helm/cognitive-load-monitor/values.gke.yaml` and `deploy/gke/` intentionally retain `SET_*` and zero-digest placeholders | Resolve reviewed registry digests, real host, Secret contracts and approved model values; render and schema-validate the complete production set with no placeholder or restricted Spark reference |
| Cloud plan | No approved project/billing identity, backend, current GKE version, actual Terraform plan, budget channel or GCS round trip | Approve exact project, billing account, region, backend, plan, spend window, teardown and model decision before any apply or publication |

The C11 preflight is for an isolated **kind** target and must not be used as a
GKE target check. `scripts/gke_release_preflight.py` is a read-only GKE identity
check: it binds an explicit project, region, cluster, kubeconfig and context to
the live control-plane endpoint, rejects protected kind contexts, requires ready
nodes with reported allocatable resources, and reuses the C11 controller-matrix
and image-ledger shape gates. It does **not** verify signatures, scans, storage
classes, Secrets or schedulability; those remain separate release gates. A
backend-free Terraform validate or static node budget does not prove live
capacity. The MLMD 1.14 wrong-password path
historically exited with SIGSEGV; current-image negative authentication behavior
still needs an isolated runtime check before this candidate is accepted.

After separate approval, perform the release order above, run the exact KFP
pipeline and negative digest test, verify MLflow GCS object generation and hash,
then exercise KServe readiness/inference/restart and real Knative delivery,
deduplication, dead letter, anomaly alert and outbox recovery. Record request,
run, image and object identities plus metrics/logs. Roll back application
manifests to the last verified digests on failure; preserve MySQL/MLMD and GCS
data for diagnosis. Teardown requires a separate reviewed plan and approval;
capture costs and evidence before any resource destruction. The eight-hour
planning window and $15 budget alert are estimates, not spending limits.
