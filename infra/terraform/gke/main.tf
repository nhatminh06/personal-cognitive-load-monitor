provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = {
    application = "cogniflow"
    environment = "demo"
    managed_by  = "terraform"
  }
}

resource "google_compute_network" "gke" {
  name                    = "cogniflow-gke"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.required]
}

resource "google_compute_subnetwork" "gke" {
  name                     = "cogniflow-gke-${var.region}"
  region                   = var.region
  network                  = google_compute_network.gke.id
  ip_cidr_range            = var.nodes_ipv4_cidr
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "cogniflow-pods"
    ip_cidr_range = var.pods_ipv4_cidr
  }
  secondary_ip_range {
    range_name    = "cogniflow-services"
    ip_cidr_range = var.services_ipv4_cidr
  }
}

resource "google_compute_router" "gke" {
  name    = "cogniflow-gke"
  region  = var.region
  network = google_compute_network.gke.id
}

resource "google_compute_router_nat" "gke" {
  name                               = "cogniflow-gke"
  router                             = google_compute_router.gke.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.gke.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }
  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

resource "google_service_account" "gke_nodes" {
  account_id   = "cogniflow-gke-nodes"
  display_name = "CogniFlow GKE nodes"
  depends_on   = [google_project_service.required]
}

resource "google_project_iam_member" "gke_node_agent" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "cogniflow-images"
  description   = "Digest-pinned CogniFlow container images"
  format        = "DOCKER"
  labels        = local.labels
  depends_on    = [google_project_service.required]
}

resource "google_artifact_registry_repository_iam_member" "node_reader" {
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_storage_bucket" "model_bucket" {
  name                        = "${var.project_id}-cogniflow-mlflow"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.labels

  versioning {
    enabled = true
  }
  retention_policy {
    retention_period = var.model_retention_seconds
  }
  lifecycle_rule {
    condition {
      age        = var.noncurrent_version_retention_days
      with_state = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }
  depends_on = [google_project_service.required]
}

resource "google_service_account" "mlflow" {
  account_id   = "cogniflow-mlflow"
  display_name = "CogniFlow MLflow artifact writer"
}

resource "google_service_account" "kserve" {
  account_id   = "cogniflow-kserve"
  display_name = "CogniFlow KServe artifact reader"
}

resource "google_service_account" "api" {
  account_id   = "cogniflow-api"
  display_name = "CogniFlow API runtime"
}

resource "google_storage_bucket_iam_member" "mlflow_artifacts" {
  bucket = google_storage_bucket.model_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.mlflow.email}"
}

resource "google_storage_bucket_iam_member" "kserve_artifacts" {
  bucket = google_storage_bucket.model_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.kserve.email}"
}

resource "google_service_account_iam_member" "mlflow_workload_identity" {
  service_account_id = google_service_account.mlflow.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[mlflow/mlflow]"
}

resource "google_service_account_iam_member" "kserve_workload_identity" {
  service_account_id = google_service_account.kserve.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[cogniflow/cogniflow-kserve]"
}

resource "google_service_account_iam_member" "api_workload_identity" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[cogniflow/cogniflow-api]"
}

resource "google_secret_manager_secret" "api_key" {
  secret_id = "cogniflow-api-key"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "api_key_accessor" {
  secret_id = google_secret_manager_secret.api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_container_cluster" "primary" {
  name                = var.cluster_name
  location            = var.region
  node_locations      = var.node_locations
  network             = google_compute_network.gke.id
  subnetwork          = google_compute_subnetwork.gke.id
  networking_mode     = "VPC_NATIVE"
  datapath_provider   = "ADVANCED_DATAPATH"
  deletion_protection = true
  min_master_version  = "1.34"

  remove_default_node_pool = true
  initial_node_count       = 1

  release_channel {
    channel = "REGULAR"
  }
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.control_plane_ipv4_cidr
  }
  ip_allocation_policy {
    cluster_secondary_range_name  = "cogniflow-pods"
    services_secondary_range_name = "cogniflow-services"
  }
  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }
  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
  }
  resource_labels = local.labels
  depends_on      = [google_project_service.required, google_compute_router_nat.gke]
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  node_count = var.nodes_per_zone

  node_config {
    machine_type    = var.machine_type
    service_account = google_service_account.gke_nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    disk_type       = "pd-balanced"
    disk_size_gb    = 100
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    metadata = {
      disable-legacy-endpoints = "true"
    }
    labels = local.labels
  }
  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

resource "google_billing_budget" "demo" {
  billing_account = var.billing_account_id
  display_name    = "CogniFlow demo review threshold"
  budget_filter {
    projects = ["projects/${var.project_number}"]
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }
  dynamic "threshold_rules" {
    for_each = toset([0.25, 0.5, 0.75, 0.9, 1.0])
    content {
      threshold_percent = threshold_rules.value
    }
  }
}
