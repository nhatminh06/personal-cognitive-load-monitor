# Third-party material

This repository does not vendor third-party Python packages, container images, Kubernetes release bundles, or scanner databases. `uv.lock`, service requirement locks, `dvc.lock`, and Terraform lock files are generated resolution metadata; installation retrieves dependencies from their upstream distributions, which remain subject to their own licenses.

GitHub Actions workflows reference immutable upstream action commits and a checksum-pinned Gitleaks release download. Those references do not copy the upstream projects into this repository. The MIT license in this repository applies to original CogniFlow code and documentation; it does not relicense dependencies or referenced external projects.

Generated notebooks, raw scanner output, copied upstream manifests/checksum lists, serialized model artifacts, and Track B operational evidence were excluded from this publication candidate because their redistribution basis was not established for the final file set.
