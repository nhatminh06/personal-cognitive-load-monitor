variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for the regional GKE cluster."
  type        = string
  default     = "asia-southeast1"
}

variable "cluster_name" {
  description = "Name of the GKE cluster."
  type        = string
  default     = "cognitive-load-gke"
}

variable "node_count" {
  description = "Initial node count for the default node pool."
  type        = number
  default     = 2
}

variable "machine_type" {
  description = "GKE node machine type."
  type        = string
  default     = "e2-standard-2"
}

variable "github_repository" {
  description = "GitHub repo allowed to assume the deployer identity, as \"owner/repo\" (e.g. \"nhatminh06/personal-cognitive-load-monitor\")."
  type        = string
}

variable "master_authorized_networks" {
  description = "CIDRs allowed to reach the GKE control plane. Use narrow operator/VPN ranges."
  type = list(object({
    cidr_block   = string
    display_name = string
  }))

  validation {
    condition     = length(var.master_authorized_networks) > 0 && alltrue([for network in var.master_authorized_networks : can(cidrnetmask(network.cidr_block))])
    error_message = "Provide at least one valid authorized control-plane CIDR."
  }
}

