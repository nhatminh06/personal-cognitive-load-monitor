provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_service_account" "gke_nodes" {
  account_id   = "cognitive-load-gke-nodes"
  display_name = "Cognitive Load GKE Nodes"
}

resource "google_project_iam_member" "artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "cognitive-load-images"
  description   = "Container images for cognitive load monitor"
  format        = "DOCKER"
}

resource "google_storage_bucket" "model_bucket" {
  name                        = "${var.project_id}-cognitive-load-models"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
}

resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.region

  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false

  release_channel {
    channel = "REGULAR"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
  }
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = var.node_count

  node_config {
    machine_type    = var.machine_type
    service_account = google_service_account.gke_nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    labels = {
      project = "cognitive-load-monitor"
    }
  }
}
