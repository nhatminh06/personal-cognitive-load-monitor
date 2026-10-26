locals {
  kubeconfig = abspath("${path.module}/${var.kubeconfig_path}")
}

provider "kubernetes" {
  config_path    = local.kubeconfig
  config_context = var.kubernetes_context
}

provider "helm" {
  kubernetes = {
    config_path    = local.kubeconfig
    config_context = var.kubernetes_context
  }
}
