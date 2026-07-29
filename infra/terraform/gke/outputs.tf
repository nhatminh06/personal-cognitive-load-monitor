output "cluster_name" {
  value = google_container_cluster.primary.name
}

output "cluster_location" {
  value = google_container_cluster.primary.location
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.images.name
}

output "model_bucket" {
  value = google_storage_bucket.model_bucket.url
}

output "artifact_registry_url" {
  description = "Docker registry path for image.repository, e.g. REGION-docker.pkg.dev/PROJECT/cognitive-load-images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "kserve_storage_uri" {
  description = "Value for the KSERVE_STORAGE_URI GitHub secret / helm --set kserve.storageUri"
  value       = "${google_storage_bucket.model_bucket.url}/models/cognitive-load-classifier"
}

# --- Copy these straight into GitHub Actions secrets ---

output "gcp_workload_identity_provider" {
  description = "Value for the GCP_WORKLOAD_IDENTITY_PROVIDER GitHub secret"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "gcp_service_account" {
  description = "Value for the GCP_SERVICE_ACCOUNT GitHub secret"
  value       = google_service_account.github_actions.email
}

output "gcp_project_id" {
  description = "Value for the GCP_PROJECT_ID GitHub secret"
  value       = var.project_id
}

output "gke_cluster" {
  description = "Value for the GKE_CLUSTER GitHub secret"
  value       = google_container_cluster.primary.name
}

output "gke_location" {
  description = "Value for the GKE_LOCATION GitHub secret"
  value       = google_container_cluster.primary.location
}
