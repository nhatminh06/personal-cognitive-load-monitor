variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for the regional GKE cluster."
  type        = string
  default     = "us-central1"
}

variable "cluster_name" {
  description = "Name of the GKE cluster."
  type        = string
  default     = "cognitive-load-gke"
}

variable "node_locations" {
  description = "Two zones used by the regional node pool; keep this bounded for the demo."
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b"]
}

variable "nodes_per_zone" {
  description = "Fixed nodes in each node location."
  type        = number
  default     = 1
}

variable "machine_type" {
  description = "GKE node machine type."
  type        = string
  default     = "e2-standard-4"
}

variable "nodes_ipv4_cidr" {
  type        = string
  description = "Primary node subnet CIDR."
  default     = "10.10.0.0/20"
}

variable "pods_ipv4_cidr" {
  type        = string
  description = "Secondary pod CIDR."
  default     = "10.20.0.0/16"
}

variable "services_ipv4_cidr" {
  type        = string
  description = "Secondary service CIDR."
  default     = "10.30.0.0/20"
}

variable "control_plane_ipv4_cidr" {
  type        = string
  description = "Private GKE control-plane CIDR."
  default     = "172.16.0.0/28"
}

variable "model_retention_seconds" {
  type        = number
  description = "Minimum retention for MLflow artifacts and approved model evidence."
  default     = 2592000
}

variable "noncurrent_version_retention_days" {
  type        = number
  description = "Days to retain noncurrent object versions after retention permits deletion."
  default     = 45
}

variable "billing_account_id" {
  type        = string
  description = "Owner-approved billing account for mandatory pre-deployment budget alerts."
  sensitive   = true
}

variable "project_number" {
  type        = string
  description = "Numeric GCP project number used to scope the optional budget."
  validation {
    condition     = can(regex("^[0-9]+$", var.project_number))
    error_message = "project_number must be numeric so the mandatory budget is project-scoped."
  }
}

variable "monthly_budget_usd" {
  type        = number
  description = "Demo budget alert amount; alerts do not cap spend."
  default     = 100
}

variable "github_repository" {
  description = "GitHub repo allowed to assume the deployer identity, as \"owner/repo\" (e.g. \"nhatminh06/personal-cognitive-load-monitor\")."
  type        = string
}

variable "master_authorized_networks" {
  description = "Fixed IPv4 /32 addresses allowed to reach the GKE control plane (operator/VPN and deployment-runner NAT only)."
  type = list(object({
    cidr_block   = string
    display_name = string
  }))

  validation {
    condition = length(var.master_authorized_networks) > 0 && alltrue([
      for network in var.master_authorized_networks :
      can(cidrnetmask(network.cidr_block)) && can(regex("^[0-9.]+/32$", network.cidr_block))
    ])
    error_message = "Provide only fixed IPv4 /32 control-plane CIDRs; unrestricted or dynamic ranges are forbidden."
  }
}

