# C5.3 FastAPI and KServe image remediation

**Date:** 2026-11-17 (America/Chicago)

**Starting revision:** `54633a7ba498ccf1a04441c1ac9fbf59a899bc7a`

## Result

Both locally built application images pass the existing zero-HIGH/
zero-CRITICAL gate. They are local OCI identities, not published or signed
registry artifacts, and were not deployed to Kubernetes.

| Image | Original local ID and findings | Replacement local ID and findings |
|---|---|---|
| FastAPI | `sha256:1c2ae372fb1eb6eaac2175a9fc889a8bae3935666f473c6c69ff6981bbe7baec`; 58 HIGH / 0 CRITICAL | `sha256:9609981bd9c775b3937a0d8cf7158c02e786089cd35ce1de5352d90b4ace26c0`; 0 HIGH / 0 CRITICAL |
| KServe | `sha256:75c140d04fe569757a58b43b2bd4913bb92f94c3b02faf4764312d4d838ab9d6`; 60 HIGH / 0 CRITICAL | `sha256:6e4a0d3c3682fec3c85e3676acb268d422819f5378494f3b26e78ad99cba3f9b`; 0 HIGH / 0 CRITICAL |

The old images contained 50 Debian findings each. The API also contained eight
`pyasn1` findings; KServe contained those plus two `oauthlib` findings. Debian
had no fixes for 39 occurrences. A current distroless Debian 13 candidate was
rejected with 89 HIGH findings. The free Chainguard Python image was clean but
Python 3.15.2, outside KServe's `<3.14` contract.

The replacement uses the supported Wolfi base
`cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90`,
exact `python-3.13=3.13.18_git20261115-r1`, and non-root UID 65532. Build uv is
also digest-pinned. `pyasn1` changed 0.6.4 → 0.6.5 and `oauthlib` 4.0.0 → 4.0.1.
No application inference or approval logic changed.

## Security evidence

Trivy 0.76.2 used vulnerability DB 2 updated `2026-11-17 19:04:24Z` and Java
DB 1 updated `2026-11-17 00:59:10Z`. Both complete scans contained supported
Wolfi OS and Python-package targets, no scanner errors, and no suppression.
Large reports remain outside Git.

| Artifact | SHA-256 |
|---|---|
| API Trivy JSON | `089521be77d63b02be30dc100dbadb5113a4fad1ca0a78eb4934fe52c663502f` |
| KServe Trivy JSON | `0c9ab2a606ee93dec68f12ab8c27eb573f1c7db04b1ed5c6bb713a08061c953e` |
| API SPDX 2.3 SBOM (148 packages) | `345617febf9260351fa69c975467a0edd0dc2608cabc889abe4ded658f043896` |
| KServe SPDX 2.3 SBOM (176 packages) | `3abcd283d6013f7adaa943339f8896a572c721d78f48fb7602116232a6ab6076` |
| API BuildKit provenance metadata | `d0b09bd61379e87238ada70585cf3d5d2cfb283de80c27dceca8b7ec34b5c140` |
| KServe BuildKit provenance metadata | `1941d411c8bf9801251c278cdebd0be9b41b276797f8877142a9e90ee0463623` |

BuildKit recorded `https://mobyproject.org/buildkit@v1` provenance and the
immutable Wolfi and uv materials. BuildKit also generated SBOM attestations;
Trivy independently generated the verified SPDX files above. Local `--load`
does not constitute registry publication, signature, or durable registry
attestation. No Cosign signing was performed.

## Isolated compatibility

The test used only `cogniflow-c53-*` containers/network, loopback ports 19053
and 19054, read-only roots, tmpfs `/tmp`, dropped capabilities,
`no-new-privileges`, 0.5/1 CPU and 512 MiB/1 GiB limits. It used the disposable
Module I qualification fixture, not C2.2. Model SHA-256 was
`835500f0f3ab99b0c3a2fd430fa7a020dec3c1b5514e7d51a4136b340c928e85`.

- KServe readiness, exact metadata and direct six-feature prediction returned 200/LOW.
- FastAPI health and provenance-backed readiness returned 200.
- Unauthenticated prediction returned 401; authenticated prediction returned 200/LOW.
- With the test KServe container stopped, API readiness returned 504 without fallback.
- Restart restored readiness and authenticated prediction returned 200/HIGH.
- A wrong configured model digest caused KServe startup to exit 1 before serving.
- Observed memory: API 429.7 MiB; KServe 197.7 MiB. Image sizes were
  approximately 991 MB and 1.03 GB. Test-owned resources were removed.

## Regression and remaining gates

- Focused FastAPI/KServe/model tests: 158 passed, one collection warning.
- Full suite: 630 passed, 2 skipped, 5 warnings; 87.20% coverage (81% required).
- Ruff passed; scoped MyPy passed for 26 source files.
- Helm lint and the digest-pinned Module I render passed.

The images are source- and local-runtime-qualified for a separately authorized
Kubernetes acceptance after publication, registry digest resolution, signing
and attestation verification. Runtime remains blocked by the kubectl 1.35.10
three-HIGH result and the unactioned gateway/NetworkPolicy correction. M10.3
remains NO-GO and SEC-022 is unchanged.
