output "namespace" {
  value = kubernetes_namespace_v1.cogniflow.metadata[0].name
}

output "helm_release" {
  value = helm_release.cogniflow.name
}

output "service_name" {
  value = "cognitive-load-monitor"
}
