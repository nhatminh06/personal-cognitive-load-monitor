# ML supply-chain security

The six ordered feature contract and `synthetic_proxy` label provenance are unchanged. CI trains/registers, selects an explicit MLflow model version, downloads it before the Docker build, and no longer passes registry values as build arguments.

Because joblib/pickle can execute code, `local_model` production mode now refuses to load without `MODEL_SHA256` and verifies the file before `joblib.load`. This controls accidental/substituted artifacts but is not a full provenance signature. Production should store the digest in a managed Secret tied to an approved immutable model version, sign image/model attestations, restrict registry writers and prefer a safer serialization format when compatible.

MLflow's safer skops serializer is retained for registry logging. RandomForest training explicitly trusts only `sklearn.tree._tree.Tree`, a type created by the in-process training job; it does not blanket-trust every type reported by an artifact.

DVC credentials are not committed. Remote state and MLflow authentication/TLS require deployment-specific verification.
