# C5.4 security-qualified kubectl

**Qualification date:** 2026-11-17

**Decision:** the standalone client qualification is **PASS**. The source-built
linux/amd64 client has zero HIGH and zero CRITICAL findings and passed read-only
validation against the named Kubernetes 1.34.11 qualification cluster. M10.3 as
a whole remains **NO-GO** until this binary is incorporated into, and the exact
deployment-runner image passes, its existing image gate. No cluster object was
changed.

## Selection and compatibility

The official Kubernetes 1.35.10 binary remains unsuitable. Its exact current
Trivy scan reports three HIGH findings:

| Finding | Module | Official version | Fixed version |
|---|---|---:|---:|
| CVE-2026-78661 | `golang.org/x/net` | 0.56.0 | 0.62.0 |
| CVE-2026-78669 | `golang.org/x/net` | 0.56.0 | 0.60.0 |
| CVE-2026-56851 | `golang.org/x/text` | 0.39.0 | 0.41.0 |

Kubernetes 1.35.10 is the final available 1.35 patch on the inspection date.
The selected solution therefore uses its authentic source at commit
`ae6fece6fea92ecfcccd13af7d5f2ea8cb9b33fe`, with only the Go module closure
required by fixed `x/net` 0.62.0. The resulting client reports
`v1.35.10-cogniflow.1`. A 1.35 client is within the Kubernetes-supported one
minor client skew for the inspected 1.34.11 API server.

The old modules are compiled into the official client. `x/net` supplies HTTP,
HTTP/2, proxy, IDNA and HTML-related packages used in the client dependency
graph; `x/text` is also reached through charset/IDNA processing. No reachability
exception was used because M10.3 requires zero findings.

## Authentic inputs and build

| Input | Identity | Verification |
|---|---|---|
| Kubernetes source | v1.35.10 archive, commit `ae6fece6…` | Official adjacent SHA-512 matched; Kubernetes Sigstore certificate and signature verified with `krel-staging@k8s-releng-prod.iam.gserviceaccount.com` and `https://accounts.google.com` |
| Source archive | SHA-256 `3049a97c6be1aed0cefe5db304d6a6ff1a440c95bcd031a7a9b6976049f40730` | `https://dl.k8s.io/v1.35.10/kubernetes-src.tar.gz` |
| Go toolchain | go1.27.4 linux/amd64 | Official SHA-256 `7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840` |

`go mod tidy -compat=1.26` produced the fixed, internally consistent module
closure. It changed no Kubernetes source code:

| Module | Upstream | Candidate |
|---|---:|---:|
| `golang.org/x/crypto` | 0.53.0 | 0.58.0 |
| `golang.org/x/net` | 0.56.0 | 0.62.0 |
| `golang.org/x/sync` | 0.21.0 | 0.24.0 |
| `golang.org/x/sys` | 0.46.0 | 0.49.0 |
| `golang.org/x/term` | 0.44.0 | 0.47.0 |
| `golang.org/x/text` | 0.39.0 | 0.43.0 |
| `golang.org/x/tools` | 0.47.0 | 0.51.0 |
| `golang.org/x/mod` | 0.37.0 | 0.41.0 |

The build used `CGO_ENABLED=0`, `GOWORK=off`, `GOTOOLCHAIN=local`,
`-buildvcs=false`, `-mod=mod`, `-p=2`, `-trimpath`, and the upstream
`selinux,notest,grpcnotrace` tags. Link metadata binds the upstream commit,
archive tree state, release-derived version and original release build date.
The binary is static and stripped. Two consecutive builds from the same inputs
were byte-identical.

Reproduction requires downloading and verifying the three exact inputs above,
then, from the extracted source:

```bash
go mod edit -require=golang.org/x/net@v0.62.0 \
  -require=golang.org/x/text@v0.41.0
go mod tidy -compat=1.26
LD_FLAGS='-s -w
  -X k8s.io/client-go/pkg/version.buildDate=2026-10-27T12:02:52Z
  -X k8s.io/component-base/version.buildDate=2026-10-27T12:02:52Z
  -X k8s.io/client-go/pkg/version.gitCommit=ae6fece6fea92ecfcccd13af7d5f2ea8cb9b33fe
  -X k8s.io/component-base/version.gitCommit=ae6fece6fea92ecfcccd13af7d5f2ea8cb9b33fe
  -X k8s.io/client-go/pkg/version.gitTreeState=archive
  -X k8s.io/component-base/version.gitTreeState=archive
  -X k8s.io/client-go/pkg/version.gitVersion=v1.35.10-cogniflow.1
  -X k8s.io/component-base/version.gitVersion=v1.35.10-cogniflow.1
  -X k8s.io/client-go/pkg/version.gitMajor=1
  -X k8s.io/component-base/version.gitMajor=1
  -X k8s.io/client-go/pkg/version.gitMinor=35
  -X k8s.io/component-base/version.gitMinor=35'
CGO_ENABLED=0 GOWORK=off GOTOOLCHAIN=local GOMAXPROCS=2 \
  go build -buildvcs=false -mod=mod -p=2 -trimpath \
  -tags=selinux,notest,grpcnotrace \
  -ldflags="$LD_FLAGS" \
  -o kubectl ./cmd/kubectl
```

The local build patch hashes are retained with the untracked build evidence:
`go.mod.patch` SHA-256 `d6b40357a028e4cd68234e32eef3c12640acbb9baeeb3259af311c4426feca85`
and `go.sum.patch` SHA-256
`f4d454e9d7b6387003c292c64a9d456e673ae2b9509b8938d847a1bf595b4460`.

## Exact candidate and security result

- Binary: `build/c54-kubectl/work/_output/c54/kubectl` (ignored local evidence)
- Version: `v1.35.10-cogniflow.1`, linux/amd64, Go 1.27.4
- Binary SHA-256:
  `130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef`
- Trivy: 0.76.2, database schema 2 updated 2026-11-17 19:04:24 UTC
- Scan target: exact standalone Go binary, complete `gobinary` analysis
- Result: **0 HIGH, 0 CRITICAL**, exit code 0, no suppression or scan error
- Trivy JSON SHA-256:
  `6c2632b8225409a35af3a4bf2a51c416078f0eab65149ab51c97675bdf340d94`
- SPDX 2.3 SBOM: 84 packages, SHA-256
  `0a1e1dda8658e4a5d5427953c1515c49076c47fe3c107fc9378b54697ce700fa`

The build is locally reproducible and the source archive has upstream Sigstore
provenance. The derived binary itself was not signed, published, or attested.
Raw binary, scan, SBOM, module patches and caches remain under ignored `build/`
and are not source-controlled.

## Offline and read-only validation

- `kubectl version --client -o yaml`: PASS with the exact identity above.
- Top-level help: PASS.
- Invalid command: rejected with exit code 1.
- Explicit missing kubeconfig: rejected with exit code 1.
- Explicit qualification kubeconfig selected only
  `kind-cogniflow-module1-qualification`.
- Read-only `/version`: Kubernetes v1.34.11, commit `3a634765…`.
- Read-only node query: one v1.34.11 control-plane node.
- Read-only Istio Gateway query: existing
  `istio-system/cluster-local-gateway`,
  `istio-system/istio-ingressgateway`, and
  `knative-serving/knative-local-gateway`.

No `apply`, `patch`, `delete`, rollout, restart, deployment, port-forward or
other mutating operation was run.

## Remaining gates

This result removes the standalone kubectl vulnerability blocker, but does not
qualify an exact deployment-runner image. Before any mutation, the owner must:

1. add the exact binary and checksum to the verified runner build inputs;
2. rebuild the runner with network disabled;
3. generate its exact-image SBOM and provenance evidence;
4. require zero HIGH and zero CRITICAL findings for the whole runner; and
5. retain the existing source, schema and runtime controls.

The C5 gateway/NetworkPolicy correction remains unapplied. FastAPI and KServe
images remain local and require registry publication, digest resolution,
signatures and attestations before authorized Kubernetes acceptance. SEC-022 is
unchanged.
