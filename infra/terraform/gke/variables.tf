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
