# Cloud security (deferred)

Terraform was reviewed and formatted only; no apply occurred. Buckets use uniform access and no public grant. Workload Identity is configured and GitHub federation is now repository-and-main-ref restricted. Node OAuth scope is broad but effective access is constrained by the node service account's IAM role.

Before deployment, verify: private/control-plane networking, authorized networks, deletion protection policy, separate KServe storage identity, Secret Manager/external secrets, TLS certificates, restrictive namespace RBAC, Pod Security admission, image digest/signature policy, audit logging, backup/retention and budget alerts.

The GKE configuration requires at least one explicit control-plane authorized CIDR and uses `GKE_METADATA` for node workload metadata. The current Helm NetworkPolicy is intentionally generic and permits broad namespace ingress and HTTP(S) egress. It must be narrowed against the actual ingress controller, DNS, Tempo and KServe namespaces before cloud approval. KServe storage authorization, HPA behavior and scale-to-zero are static-only.
