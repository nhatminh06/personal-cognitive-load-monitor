# Security and privacy

The API validates bounded inputs, does not label metrics with user/session identifiers, returns sanitized backend errors, and never silently substitutes a predictor in KServe mode. Kubernetes ingress requires an externally created basic-auth Secret; no credential hash is committed. Images run as UID 10001 with dropped capabilities and a read-only root filesystem in Helm.

Only load model artifacts produced by the trusted local/CI MLflow registry. Joblib/pickle deserialization is executable code and must not be used for unknown artifacts. The demo records no real user history and makes no medical claim.
