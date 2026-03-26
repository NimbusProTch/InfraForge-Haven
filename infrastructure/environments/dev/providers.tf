provider "hcloud" {
  token = var.hcloud_token
}

# Helm provider uses kubeconfig from first master
provider "helm" {
  kubernetes {
    config_path = local_sensitive_file.kubeconfig.filename
  }
}

provider "kubernetes" {
  config_path = local_sensitive_file.kubeconfig.filename
}
