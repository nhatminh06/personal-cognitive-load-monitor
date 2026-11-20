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
