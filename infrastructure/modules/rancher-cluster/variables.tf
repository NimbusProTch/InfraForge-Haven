# ===== Cluster =====
variable "cluster_name" {
  description = "RKE2 cluster name"
  type        = string
}

variable "kubernetes_version" {
  description = "RKE2 Kubernetes version"
  type        = string
}

# ===== Cilium CNI =====
variable "enable_hubble" {
  description = "Enable Hubble observability (UI + Relay)"
  type        = bool
  default     = true
}

variable "cilium_operator_replicas" {
  description = "Number of Cilium operator replicas"
  type        = number
  default     = 1
}

variable "disable_kube_proxy" {
  description = "Let Cilium replace kube-proxy (eBPF)"
  type        = bool
  default     = true
}

variable "disabled_rke2_charts" {
  description = "RKE2 built-in Helm charts to disable"
  type        = list(string)
  default     = ["rke2-ingress-nginx"]
}

# ===== Longhorn Storage =====
variable "longhorn_replica_count" {
  description = "Longhorn default replica count (auto-set from worker_count)"
  type        = number
  default     = 1
}

# ===== Monitoring (rancher-monitoring) =====
variable "monitoring_retention_size" {
  description = "Prometheus retention size"
  type        = string
  default     = "5GB"
}

variable "monitoring_retention_days" {
  description = "Prometheus retention period"
  type        = string
  default     = "7d"
}

variable "prometheus_cpu_request" {
  description = "Prometheus CPU request"
  type        = string
  default     = "250m"
}

variable "prometheus_memory_request" {
  description = "Prometheus memory request"
  type        = string
  default     = "512Mi"
}

variable "prometheus_memory_limit" {
  description = "Prometheus memory limit"
  type        = string
  default     = "2Gi"
}

# ===== Logging (rancher-logging) =====
variable "fluentbit_cpu_request" {
  description = "Fluent Bit CPU request"
  type        = string
  default     = "100m"
}

variable "fluentbit_memory_request" {
  description = "Fluent Bit memory request"
  type        = string
  default     = "128Mi"
}

variable "fluentbit_memory_limit" {
  description = "Fluent Bit memory limit"
  type        = string
  default     = "256Mi"
}

variable "fluentd_cpu_request" {
  description = "Fluentd CPU request"
  type        = string
  default     = "200m"
}

variable "fluentd_memory_request" {
  description = "Fluentd memory request"
  type        = string
  default     = "256Mi"
}

variable "fluentd_memory_limit" {
  description = "Fluentd memory limit"
  type        = string
  default     = "512Mi"
}

# ===== Harbor (Image Registry) =====
variable "harbor_host" {
  description = "Harbor hostname (e.g., harbor.<IP>.sslip.io)"
  type        = string
  default     = ""
}

variable "harbor_admin_password" {
  description = "Harbor admin password"
  type        = string
  default     = "Harbor12345"
  sensitive   = true
}

variable "harbor_registry_storage_size" {
  description = "Harbor registry PVC size"
  type        = string
  default     = "20Gi"
}

# ===== MinIO (Object Storage) =====
variable "minio_root_user" {
  description = "MinIO root username"
  type        = string
  default     = "admin"
}

variable "minio_root_password" {
  description = "MinIO root password"
  type        = string
  default     = "MinIO12345!"
  sensitive   = true
}

variable "minio_storage_size" {
  description = "MinIO PVC size"
  type        = string
  default     = "20Gi"
}

variable "minio_console_host" {
  description = "MinIO Console hostname (e.g., minio.<IP>.sslip.io)"
  type        = string
  default     = ""
}

variable "minio_api_host" {
  description = "MinIO API hostname (e.g., s3.<IP>.sslip.io)"
  type        = string
  default     = ""
}

# ===== ArgoCD =====
variable "argocd_host" {
  description = "ArgoCD hostname (e.g., argocd.<IP>.sslip.io)"
  type        = string
  default     = ""
}

# ===== Keycloak =====
variable "keycloak_host" {
  description = "Keycloak hostname (e.g., keycloak.<IP>.sslip.io)"
  type        = string
  default     = ""
}

variable "keycloak_admin_password" {
  description = "Keycloak admin password"
  type        = string
  default     = "Keycloak12345!"
  sensitive   = true
}

variable "keycloak_db_password" {
  description = "Keycloak embedded PostgreSQL password (Sprint 1)"
  type        = string
  default     = "KeycloakDB12345!"
  sensitive   = true
}

# ===== External-DNS =====
variable "external_dns_cloudflare_token" {
  description = "Cloudflare API token for External-DNS"
  type        = string
  default     = ""
  sensitive   = true
}

variable "external_dns_domain_filters" {
  description = "Domain filters for External-DNS"
  type        = list(string)
  default     = []
}
