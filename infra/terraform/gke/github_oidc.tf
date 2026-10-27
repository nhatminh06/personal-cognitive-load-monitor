# Lets GitHub Actions authenticate to GCP via short-lived OIDC tokens (no
# downloaded JSON service-account keys). This is what the `deploy` job in
# .github/workflows/ci-cd.yaml expects to find in:
#   secrets.GCP_WORKLOAD_IDENTITY_PROVIDER
#   secrets.GCP_SERVICE_ACCOUNT
#
# Without this file, those two secrets have nothing to point at and the
# "Authenticate to Google Cloud" step in the deploy job fails.

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Identity pool for GitHub Actions OIDC federation"

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions Provider"

  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.repository"  = "assertion.repository"
    "attribute.ref"         = "assertion.ref"
    "attribute.environment" = "assertion.environment"
  }

  # Credentials are issued only from main through one of the two protected
  # environments; each service account binding below narrows this further.
  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.ref == \"refs/heads/main\" && assertion.environment in [\"production\", \"production-release\"]"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_actions" {
  account_id   = "github-actions-deployer"
  display_name = "GitHub Actions Deployer"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "github_actions_release" {
  account_id   = "github-actions-release"
  display_name = "GitHub Actions Release Publisher"

  depends_on = [google_project_service.required]
}

# Allow the GitHub Actions identity (scoped to this repo) to impersonate the
# deployer service account.
resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/production"
}

resource "google_service_account_iam_member" "github_release_wif_binding" {
  service_account_id = google_service_account.github_actions_release.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.environment/production-release"
}

# Project-level access only discovers the cluster. Namespace mutation is granted
# separately by deploy/gke/cogniflow-guardrails.yaml.
resource "google_project_iam_member" "github_actions_gke_viewer" {
  project = var.project_id
  role    = "roles/container.clusterViewer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_artifact_registry_repository_iam_member" "github_actions_writer" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_actions_release.email}"
}
