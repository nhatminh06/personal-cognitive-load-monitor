# Required GCP APIs. A brand-new project has none of these enabled, and
# `terraform apply` will fail on every downstream resource until they are on.
locals {
  required_apis = [
    "container.googleapis.com",        # GKE
    "artifactregistry.googleapis.com", # Artifact Registry
    "iam.googleapis.com",              # Service accounts
    "iamcredentials.googleapis.com",   # Workload Identity Federation token exchange
    "sts.googleapis.com",              # WIF token exchange
    "cloudresourcemanager.googleapis.com",
    "storage.googleapis.com", # Model bucket
    "compute.googleapis.com", # GKE networking dependency
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_apis)

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}
