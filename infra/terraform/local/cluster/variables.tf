variable "cluster_name" {
  description = "Dedicated local kind cluster name."
  type        = string
  default     = "cogniflow-local"

  validation {
    condition     = var.cluster_name == "cogniflow-local"
    error_message = "This configuration may manage only cogniflow-local."
  }
}

variable "node_image" {
  description = "Pinned local kind node image."
  type        = string
  default     = "kindest/node@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
}

variable "kubeconfig_path" {
  description = "Repository-local ignored kubeconfig written by the kind provider."
  type        = string
  default     = "../.kube/cogniflow-local.yaml"
}
