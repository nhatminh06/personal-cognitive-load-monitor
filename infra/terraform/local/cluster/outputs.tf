output "cluster_name" {
  value = kind_cluster.cogniflow.name
}

output "kubernetes_context" {
  value = "kind-${kind_cluster.cogniflow.name}"
}

output "kubeconfig_path" {
  value = abspath("${path.module}/${var.kubeconfig_path}")
}
