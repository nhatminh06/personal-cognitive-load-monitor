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
