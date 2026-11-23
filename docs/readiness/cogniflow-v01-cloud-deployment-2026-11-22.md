# CogniFlow V0.1 cloud deployment — 2026-11-22

**Status: `CLOUD_MVP_BLOCKED_BILLING`.** Live read-only access to `pnm-cognitive-load` succeeded (project number `143577378448`); billing is disabled. Compute Engine and Artifact Registry APIs are disabled, so live VM inventory, quota and registry inventory are unavailable. No cloud resource was created and the local MVP remains running.

## Selected target

Use one `e2-small` VM in `us-central1-a` (2 GiB RAM, shared CPU), a 20 GiB standard boot disk, a separate 10 GiB standard SQLite disk, one in-use static IPv4 address, and Caddy TLS ingress. The API is private to the Compose network. SSH is limited to an owner-provided `/32`; only 80/443 are public. A DNS A record for an owner-controlled hostname is required for automatic HTTPS certificate issuance. Cloud Run is deferred because the current SQLite write contract needs a mounted durable single-writer disk; GKE adds no V0.1 requirement.

Infrastructure source: `deploy/mvp-cloud/main.tf`. Runtime source: `deploy/mvp-cloud/compose.yml` and `Caddyfile`. The data disk is separate to make restore and VM replacement possible. Set up Docker Engine and Compose on the Debian VM, format and mount the new data disk at `/srv/cogniflow-mvp`, and create `data` owned by UID 65532. Place the API key at `/srv/cogniflow-mvp/secrets/api-key`, mode 0600, with a read-only ACL for UID 65532; do not copy it into image layers or Terraform state. Install the Compose files under `/srv/cogniflow-mvp/deploy`, use a digest-qualified `MVP_IMAGE`, and set `MVP_DOMAIN` in a root-readable local environment file. Enable Docker at boot; `restart: unless-stopped` restores the application. Caddy certificate data persists in its named volume.

The local image's OCI index is `sha256:d4bca2717cbbe10a4ecebc99f986b1f64ffdf1b3651369fc8c39ab35d4c95017`, with a fresh local Trivy 0/0 report. Publication must verify the remote digest and linux/amd64 descriptor against the local image, then freshly scan the exact remote image. Caddy's exact image identity, provenance and 0/0 scan are **not yet qualified**; deployment must stop until both runtime images pass. API authentication remains the existing single shared key; the frontend never embeds it. For an internet-facing service, this is single-tenant access only and needs an owner decision on acceptable user access.

## Cost and ownership

At 730 hours, official listed on-demand `e2-small` price $0.016752855/hour is about **$12.23/month**. Thirty GiB standard disk at $0.04/GiB-month is **$1.20/month**; in-use external IPv4 at $0.005/hour is **$3.65/month**. Baseline is about **$17.08/month**, excluding snapshots, Artifact Registry above its 0.5 GiB account-wide free tier, DNS, egress, logging and taxes. A $25 monthly budget alert is a notification, not a spending cap. Verify the final calculator estimate and project quota before applying.

## One consolidated owner authorization

Authorize linking a billing account to project `pnm-cognitive-load`; enabling `compute.googleapis.com`, `artifactregistry.googleapis.com`, `iam.googleapis.com`, `logging.googleapis.com`, `monitoring.googleapis.com`, and `billingbudgets.googleapis.com`; creating the exact VM, two disks, static IPv4, VPC/subnet, 80/443 and owner-/32 SSH firewall rules, a private Artifact Registry repository and budget alert; publishing the exact qualified MVP image and a separately qualified Caddy image; and making the owner-controlled DNS A record. Supply the DNS hostname and SSH `/32`. Required roles must permit billing linking, service enablement, Compute/Network administration, Artifact Registry write, budget configuration and VM OS Login; least-privilege grants should be reviewed before use. Expected URL: `https://HOSTNAME/focus` after DNS and certificate issuance.

After authorization, initialize and review Terraform with a remote protected state backend; `terraform plan` must show only these resources. Provision once, mount the data disk by stable device ID, install Docker/Compose, verify both image scans and digests, then start the Compose project. Run the synthetic smoke against HTTPS, plus live effort rating and timeline acceptance, restart the API, confirm SQLite persistence and sample CPU/memory. Observe health and sanitized `docker compose logs`; ship bounded host/container logs to Cloud Logging only after configuration review. No cloud success is claimed here.

Backup with a SQLite online backup to a separate restricted destination and periodic persistent-disk snapshots; test restore on a disposable VM before claiming recovery. Roll back by pinning the previous scanned image digest and restarting only the API. Shutdown uses `docker compose down` while preserving data. Teardown requires a verified backup, then `terraform destroy` against the reviewed state; preserve the data disk or its snapshot until the owner explicitly authorizes deletion.

Offline checks: Terraform format passed; Compose parsed as exactly `api` plus `ingress`, and the API has no published port. Terraform provider validation, live plan, quotas, cloud image scans, HTTPS, browser interaction and live data tests remain pending billing/API enablement and owner authorization.

`DEFER_KFP` and `DEFER_SPARK_ENFORCED` remain in force.
