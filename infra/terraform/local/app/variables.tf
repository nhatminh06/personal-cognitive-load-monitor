variable "kubeconfig_path" {
  description = "Kubeconfig created by the cluster stage."
  type        = string
  default     = "../.kube/cogniflow-local.yaml"
}

variable "kubernetes_context" {
  description = "Exact context this stage is allowed to manage."
  type        = string
  default     = "kind-cogniflow-local"

  validation {
    condition     = var.kubernetes_context == "kind-cogniflow-local"
    error_message = "This configuration may target only kind-cogniflow-local."
  }
}

variable "namespace" {
  description = "Dedicated local application namespace."
  type        = string
  default     = "cognitive-load"
}
