# M10.3 final deployment-runner security gate

## Decision

**Overall decision: `BLOCKED`; deployment remains NO-GO.** No official,
supported kubectl candidate available on 2026-11-17 contains both required Go
dependency fixes. The exact M10.2 image was not rebuilt unchanged: its local
identity was preserved and its mandatory scan was repeated with the same
result, **2 HIGH and 0 CRITICAL**. It is not `PASS_EXACT_IMAGE`.

- Starting commit: `f45429e414ebc650b82432fbe6a57f33ae0f1e83`
- Published ancestor: `b7f3ddef1d30eb52e80887d27445c5724a198ce3`
- Branch: `feat/m10-1-security`
- Final commit: the commit containing this report; record its SHA in the local
  handoff because a commit cannot contain its own identity.
- Research and verification timestamp: 2026-11-17 14:28-14:34 CST

## Official release investigation

Only official Kubernetes and Google Cloud sources were used:

- Kubernetes release index and patch schedule:
  `https://kubernetes.io/releases/` and
  `https://kubernetes.io/releases/patch-releases/`
- Official downloads: `https://dl.k8s.io/`
- Kubernetes artifact-signing procedure:
  `https://kubernetes.io/docs/tasks/administer-cluster/verify-signed-artifacts/`
- Kubernetes version-skew policy:
  `https://kubernetes.io/releases/version-skew-policy/`
- Google Cloud CLI release notes and GKE kubectl installation guidance:
  `https://cloud.google.com/sdk/docs/release-notes` and
  `https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl`

| Candidate | Authenticity and dependency result | Decision |
|---|---|---|
| Kubernetes 1.35.10 linux/amd64 | Current and final published 1.35 patch at investigation time; official SHA-256 `c49a28f1f4efc4d475ed05f47f2ce8e563bf7bef69ed77fe1b924ea6d83b6327`; embeds Go 1.26.10, `x/net` 0.56.0 and `x/text` 0.39.0 | `BLOCKED`: both HIGH findings remain |
| Kubernetes 1.36.6 linux/amd64 | Latest supported newer minor; official adjacent checksum and Kubernetes Sigstore certificate both passed; SHA-256 `29818b6729dc9262b692307470d0558d027725e738be5dd47c760261868a2634`; commit `1b2171b110bb2a2542e1322035c6583ec86eb976`; Go 1.26.10, `x/net` 0.56.0, `x/text` 0.39.0 | `BLOCKED`: supported skew but neither dependency is fixed |
| Kubernetes 1.37.2 linux/amd64 | Official release exists, but a 1.37 client is two minor versions newer than the intended 1.35 API server | Rejected before download: unsupported version skew |
| Google Cloud CLI kubectl component | Google documents 1.36.6 as its current default and lists 1.35.10 as an additional version; these are the same upstream version lines already evaluated, not an independently fixed GKE binary | Rejected: no distinct qualified artifact or dependency fix |
| Private or locally rebuilt kubectl | Not evaluated | Prohibited workaround; would replace upstream provenance and require unsupported functional qualification |

The Kubernetes policy supports kubectl within one minor version of the API
server. Thus 1.36.6 is compatible in principle with a 1.35 server, but security
qualification still fails. Compatibility does not override the mandatory
zero-HIGH/zero-CRITICAL policy.

### Kubernetes 1.36.6 binary verification

The official binary, adjacent SHA-256, `.sig`, and `.cert` were downloaded from
`https://dl.k8s.io/release/v1.36.6/bin/linux/amd64/`. The adjacent checksum
matched. Cosign 3.1.4 returned `Verified OK` using the Kubernetes-documented
identity `krel-staging@k8s-releng-prod.iam.gserviceaccount.com` and issuer
`https://accounts.google.com`.

| Object | SHA-256 |
|---|---|
| `kubectl` | `29818b6729dc9262b692307470d0558d027725e738be5dd47c760261868a2634` |
| `kubectl.sha256` | `d99bdfb7552626a6b9d28f54d4a64ac8e8cbad1afff0eb0c68ad94b505e50248` |
| `kubectl.sig` | `f9cfad7f4f1f43976f7484bdaacb89e780b3e589ab35dd47653b8e39063ce3a5` |
| `kubectl.cert` | `db090c25a1fa6c555cf051e4dc8fa00a5c904d4dec98ec016c4611d4fc797d2b` |

`kubectl version --client -o yaml` identified linux/amd64 v1.36.6, clean tree,
build timestamp `2026-10-27T12:05:48Z`. `go version -m` independently showed:

```text
dep golang.org/x/net  v0.56.0
dep golang.org/x/text v0.39.0
```

Required fixed versions remain `x/net >= 0.60.0` and `x/text >= 0.41.0`.

## Exact-image gate

No suitable replacement exists, so the controlled build inputs, Dockerfile and
checksum manifest were intentionally not changed. Rebuilding the same bytes or
substituting equally vulnerable 1.36.6 would add no qualification evidence and
would violate the task's stop condition.

The preserved exact linux/amd64 image was inspected and rescanned:

- Image: `sha256:dfd51490064d4834bc00cfbddc35f7f151d0c274ccec10270eb45cf790d1cde2`
- Runtime user: `1001:1001`
- Scanner: Trivy 0.76.2
- Database schema: 2
- Database updated: `2026-10-25T19:10:35.479132794Z`
- Database downloaded: `2026-10-26T01:03:17.454763791Z`
- Check bundle digest:
  `sha256:0491169789b867ae5a7353381220c1d4d97b3a0d6d9dfd84a25d06f0ba68aa93`
- Scan report SHA-256:
  `1c4bf52ccaf73e65b26297975b031a3d3f88d2ce4d988087a29a4d26995bb9`
- Mandatory exit code: 1

| Finding | Component | Installed | Fixed | Severity |
|---|---|---|---|---|
| CVE-2026-78669 | `golang.org/x/net` in `/usr/local/bin/kubectl` | 0.56.0 | 0.60.0 | HIGH |
| CVE-2026-56851 | `golang.org/x/text` in `/usr/local/bin/kubectl` | 0.39.0 | 0.41.0 | HIGH |

Result: **2 HIGH, 0 CRITICAL, `BLOCKED`**. No suppression, allowlist,
exception, severity reduction, binary patch, private build, registry
publication or cluster operation was used. The M10.2 SBOM remains applicable
because the exact image did not change; no new SBOM was generated.

## M11 disposable-cluster acceptance protocol

Status: `NEEDS_OWNER_APPROVAL` and `NEEDS_RUNTIME`. Do not begin until an exact
runner image reaches `PASS_EXACT_IMAGE`, all images are approved by immutable
registry digest, the Terraform provider provenance blocker is closed, and an
owner explicitly authorizes cloud credentials, cost and cluster creation.

Every phase records commands, UTC timestamps, immutable input identities,
sanitized outputs and pass/fail status. Never capture tokens, Secret values,
customer data, kubeconfig contents or private Track B evidence. Stop on any
unexpected public endpoint, mutable image, privileged runner, policy bypass,
credential exposure or HIGH/CRITICAL exact-image finding.

| Phase | Prerequisites and action | Expected observation | Stop condition |
|---|---|---|---|
| 1. Preflight | Owner-approved project/location/budget; verify clean approved source commit, exact GKE 1.35 patch availability, signed provider, runner and application image digests, signatures, SBOMs and zero-HIGH/CRITICAL scans | All identities match the approval record; no tag-only image | Any identity mismatch, unavailable version, missing signature/provenance, mutable reference or scan failure |
| 2. Isolated creation | Create one disposable private GKE cluster through the approved backend and Terraform workflow; no reuse of an existing cluster | Private control plane/node configuration, bounded labels/budget and intended Kubernetes patch | Public control plane/workload exposure, wrong project/region/version, unapproved IAM or resource |
| 3. Namespace/security baseline | Create dedicated namespaces; apply Pod Security, quotas, LimitRanges, service accounts, default-deny NetworkPolicies and storage classes before workloads | Namespace boundaries, quotas and deny-by-default state are observable | Privileged/default service account use, unbounded quota or policy rejection/bypass |
| 4. Controllers/CRDs | Install cert-manager 1.21.2, Gateway API 1.4.0, External Secrets 2.13.0, Knative Serving then Eventing 1.23.0, and KServe 0.20.0; wait for each CRD/controller before the next layer | CRDs Established; controller deployments Available; admission webhooks healthy; exact digest identities | Timeout, webhook fail-open, crash loop, unexpected cluster scope or mutable controller image |
| 5. Runner bootstrap | Start one ephemeral deployment runner using the exact accepted digest and bounded service account; exercise registration, one no-op job and deregistration | Non-root UID/GID 1001, read-only root, only declared writable mounts, no Docker socket/daemon/sudo, one ephemeral job, cleanup succeeds | Root/privileged execution, unexpected group/capability/mount/network path, persistent registration or cleanup failure |
| 6. Model serving | Deploy digest-bound model-serving resources and perform internal readiness, inference and malformed-request checks | KServe readiness; expected response/schema; invalid input fails safely; no external route | Unready/restarting workload, mutable image, data leakage, unauthenticated external reachability or unsafe error |
| 7. Events/anomaly flow | Install Broker/Trigger resources and send unique synthetic events through the outbox-to-consumer-to-detector path; repeat/replay and conflict cases | At-least-once delivery is idempotent; event/hash transaction persists atomically; replay conflict remains HTTP 409; metrics correlate by synthetic ID | Loss, duplicate side effects, partial event/hash state, conflict semantic change or sensitive payload in logs |
| 8. Storage/recovery | Write synthetic state, snapshot/backup as designed, restart/evict workloads, restore and verify hashes; test full and unavailable storage | RWO behavior and recovery objectives are observed; corruption/full storage fails closed with actionable signals | Data loss/corruption, multi-writer attachment, silent partial recovery or credential exposure |
| 9. Gateway security | Configure the approved managed Gateway, TLS certificate, IAP/authentication, Cloud Armor rate limits and health checks only after internal tests pass | Valid TLS, authenticated authorized access, denial for unauthenticated/unauthorized clients, rate limiting and healthy backend | Plain HTTP exposure, invalid certificate, auth bypass, route to unintended namespace/service or fail-open policy |
| 10. NetworkPolicy | From allowed and denied test Pods, probe API, DNS, metadata, cross-namespace, controller and internet paths | Only explicitly required ingress/egress succeeds; metadata and lateral paths remain denied | Any unapproved path succeeds or a required path relies on broad allow rules |
| 11. Secrets | Exercise External Secrets through Workload Identity; rotate a synthetic secret and restart/refresh consumers | No static cloud key; namespace-scoped secret material; rotation propagates without logging values | Long-lived key, cross-namespace read, plaintext evidence/log output or stale access after revocation |
| 12. Capacity | Apply representative requests/limits and quota pressure; observe scheduling, autoscaling bounds and recovery | Expected workloads schedule within approved capacity; excess is predictably Pending/rejected; no budget escape | Unbounded autoscaling, priority inversion, eviction of required controls or capacity outside approval |
| 13. Failure/rollback | Inject one controlled controller restart, runner interruption, event retry, model rollout failure and Gateway backend failure; execute documented rollback | Alerts fire; retries remain bounded/idempotent; rollback restores the last approved digests without public fail-open | Data corruption, unbounded retry, stale runner, rollback to mutable/unscanned image or external fail-open |
| 14. Evidence/teardown | Capture sanitized manifests/status/events/log summaries and hashes; destroy through approved Terraform workflow; independently query inventory and billing labels | Evidence contains no secrets; namespaces, disks, IPs, load balancers, service accounts and cluster are absent; state handling follows owner procedure | Sensitive evidence, orphaned billable/public resource, destroy mismatch or unaccounted state mutation |

M11 must use runtime observations for every phase; repeating the M10.2 schema
validator is a preflight aid, not acceptance evidence. Any failed phase leaves
M11 incomplete and requires teardown before diagnosis unless preserving the
resource is explicitly authorized for incident analysis.

## Offline validation and remaining blocker

M10.3 changes documentation only; source and build inputs are unchanged.
Nevertheless, the complete Python suite and coverage gate were rerun: 604
passed, 2 skipped, 5 warnings, and 87.08% coverage against the 81% minimum.
The focused security/GKE/schema subset passed 35 tests, and Ruff passed. The
remaining exact static, secret and whitespace results are recorded in the final
handoff.

The only safe next action is to monitor official Kubernetes 1.35 patches or
the latest policy-compatible 1.36 patch. When an official linux/amd64 kubectl
embeds both `x/net >= 0.60.0` and `x/text >= 0.41.0`, an owner can repeat:

```bash
curl -fSLO https://dl.k8s.io/release/VERSION/bin/linux/amd64/kubectl
curl -fSLO https://dl.k8s.io/release/VERSION/bin/linux/amd64/kubectl.sha256
curl -fSLO https://dl.k8s.io/release/VERSION/bin/linux/amd64/kubectl.sig
curl -fSLO https://dl.k8s.io/release/VERSION/bin/linux/amd64/kubectl.cert
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check
cosign verify-blob kubectl --signature kubectl.sig --certificate kubectl.cert \
  --certificate-identity krel-staging@k8s-releng-prod.iam.gserviceaccount.com \
  --certificate-oidc-issuer https://accounts.google.com
go version -m kubectl | grep -E 'golang.org/x/(net|text)'
```

Only then update `deploy-inputs.SHA256SUMS`, rebuild with the existing
network-disabled procedure, generate an SBOM and require two consistent exact
image scans with zero unsuppressed HIGH/CRITICAL findings. Until that happens,
stop the remediation cycle rather than creating another preparation milestone.
