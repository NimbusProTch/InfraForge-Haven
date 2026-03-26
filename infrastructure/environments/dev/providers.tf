provider "hcloud" {
  token = var.hcloud_token
}

# Two-phase apply:
# Phase 1: tofu apply -target=local_sensitive_file.kubeconfig (creates cluster + retrieves kubeconfig)
# Phase 2: tofu apply (installs operators via Helm)
provider "helm" {
  kubernetes {
    config_path = "${path.module}/kubeconfig"
  }
}

provider "kubernetes" {
  config_path = "${path.module}/kubeconfig"
}
