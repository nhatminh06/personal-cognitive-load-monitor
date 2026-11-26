# Deployment and operations

## Public V0.1 — running

Production: [cogniflow.minhpham06.com](https://cogniflow.minhpham06.com).
Preview: [cogniflow-v01.mphamnhat2006.workers.dev](https://cogniflow-v01.mphamnhat2006.workers.dev).
Both point to the existing TypeScript `cogniflow-v01` Worker and D1 database.
The qualified version is `22909605-0e00-4189-89a8-0406342ce256`. The live
architecture is [diagrammed here](architecture.md); exact deployment, security,
CPU, D1 and rollback evidence is in the
[Cloudflare report](readiness/cogniflow-v01-cloudflare-free-deployment.md).
The live Wrangler file is deliberately ignored because it contains account-specific
bindings. `deploy/cloudflare/wrangler.ts.jsonc` is the route-free local template;
`deploy/cloudflare/wrangler.release.example.jsonc` records the non-secret
production route, both-host origin and disabled logging. Both use a placeholder
D1 ID and are not deployable until an authorized owner supplies the account-specific
binding and Worker secret. Keep local credential and runtime files ignored.
`demo_rule` estimates are synthetic, and actual billable charges remain
unverified despite an active Workers Free subscription.

### Lightweight maintenance

- Check aggregate Worker requests, errors and resource-limit outcomes, including
  HTTP error 1102, after changes and periodically during use. Individual CPU logs
  are intentionally disabled; use bounded, separately authorized qualification
  before changing that privacy setting.
- Review Workers Free request/CPU allowances and D1 rows read, rows written and
  storage in Cloudflare analytics. Review Billing → Billable Usage as the account
  owner; never infer a zero charge from the Free subscription alone.
- Check `/health` and `/ready` on both HTTPS hosts, anonymous private-route 401s,
  and a bounded owner synthetic session workflow. Treat unexpected 5xx, auth or
  CSRF failures as release incidents. Keep synthetic records separate from real
  personal data.
- Keep the owner credential in the private password manager and Worker secret.
  Do not put it in Git, static assets, logs or support artifacts. Review access,
  rate limits and exact HTTPS origins before any Worker change; rotate only with
  separate owner approval. Keep host-only Secure, HttpOnly, SameSite=Strict cookies.
- Preserve the current D1 database, workers.dev preview and disabled persisted
  logging. Any future deployment, DNS change, paid feature, migration or rollback
  needs explicit owner authorization and a recorded version/configuration.

## Historical GCP deployment research — inactive

The material below is retained for qualification reproducibility only. It is not
an active V0.1 deployment runbook; `DEFER_KFP` and `DEFER_SPARK_ENFORCED` remain
in effect.

### Historical deployment and release

### Authorization boundary

No project name, time window or budget threshold authorizes deployment. Before any
cloud action, the owner must approve the exact commit, project, billing account,
region, Terraform plan, image ledger, model decision and teardown procedure. Never
run Terraform apply/destroy, publish images, create registry credentials or mutate
a cluster from an ordinary verification run.

The candidate project is `pnm-cognitive-load`; the planning assumptions are an
eight-hour window and a $15 budget-alert threshold. Alerts do not cap spend.

### Release order

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

### Capacity

The 73-object headless KFP render contains ten steady workload Pods requesting
884m CPU and 3,164 MiB. One concurrent serialized pipeline Pod adds 475m and
1,088 MiB, for a 1,359m / 4,252 MiB peak. MySQL and SeaweedFS each require a 20
GiB RWO PVC. Two `e2-standard-4` nodes provide a conservative post-reserve budget
of 6,400m and 26,214 MiB; place the two RWO workloads on separate nodes. Exact
figures live in `deploy/gke/resource-budget.yaml`.

Release and deployment runners are sequential. Their bounded writable storage is
15 GiB and 6 GiB respectively. Runner manifests keep registry placeholders until
publication succeeds.

### Local-only qualification

The GCS-capable MLflow image and deployment runner each passed local whole-image
Trivy scans at 0 HIGH / 0 CRITICAL. The runner local index is
`sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a`;
its runtime manifest is
`sha256:3aab5b8fe68d83df3608c6cb1f7b3c1b02798643c068345344a56b8816b2b182`.
These are not remote registry references.

Both locally qualified images passed the `0 HIGH/CRITICAL` release gate.

For local Kubernetes use, follow the Makefile targets and keep Module I and Module
III release ownership separate. Never deploy the restricted Spark image.
