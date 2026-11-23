terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
  }
}
provider "google" {
  project = var.project_id
  region  = "us-central1"
}
variable "project_id" {
  type    = string
  default = "pnm-cognitive-load"
}
variable "zone" {
  type    = string
  default = "us-central1-a"
}
variable "ssh_cidr" {
  type = string
  validation {
    condition     = can(cidrnetmask(var.ssh_cidr)) && endswith(var.ssh_cidr, "/32")
    error_message = "ssh_cidr must be a single IPv4 address in /32 CIDR notation."
  }
}

resource "google_compute_network" "mvp" {
  name                    = "cogniflow-mvp"
  auto_create_subnetworks = false
}
resource "google_compute_subnetwork" "mvp" {
  name          = "cogniflow-mvp"
  region        = "us-central1"
  network       = google_compute_network.mvp.id
  ip_cidr_range = "10.90.0.0/24"
}
resource "google_compute_firewall" "https" {
  name        = "cogniflow-mvp-https"
  network     = google_compute_network.mvp.name
  target_tags = ["cogniflow-mvp"]
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
  source_ranges = ["0.0.0.0/0"]
}
resource "google_compute_firewall" "ssh" {
  name        = "cogniflow-mvp-ssh"
  network     = google_compute_network.mvp.name
  target_tags = ["cogniflow-mvp"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = [var.ssh_cidr]
}
resource "google_compute_address" "mvp" {
  name   = "cogniflow-mvp"
  region = "us-central1"
}
resource "google_compute_disk" "data" {
  name                      = "cogniflow-mvp-data"
  zone                      = var.zone
  type                      = "pd-standard"
  size                      = 10
  physical_block_size_bytes = 4096
}
resource "google_compute_instance" "mvp" {
  name         = "cogniflow-mvp"
  zone         = var.zone
  machine_type = "e2-small"
  tags         = ["cogniflow-mvp"]
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-standard"
    }
  }
  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "cogniflow-mvp-data"
  }
  network_interface {
    subnetwork = google_compute_subnetwork.mvp.id
    access_config {
      nat_ip = google_compute_address.mvp.address
    }
  }
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }
  metadata = { enable-oslogin = "TRUE" }
  labels   = { application = "cogniflow-mvp" }
}
output "ipv4" {
  value = google_compute_address.mvp.address
}
