resource "kubernetes_namespace_v1" "cogniflow" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/part-of"    = "cogniflow"
      "app.kubernetes.io/managed-by" = "terraform"
      "cogniflow.dev/scope"          = "local-only"
    }
  }
}

resource "helm_release" "cogniflow" {
  name      = "cognitive-load-monitor"
  namespace = kubernetes_namespace_v1.cogniflow.metadata[0].name
  chart     = abspath("${path.module}/../../../../helm/cognitive-load-monitor")
  values    = [file(abspath("${path.module}/../../../../helm/cognitive-load-monitor/values.local.yaml"))]

  atomic          = true
  cleanup_on_fail = true
  timeout         = 180
  wait            = true
}
