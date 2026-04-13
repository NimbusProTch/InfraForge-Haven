---
# Pre-create the cert-manager namespace at cluster bootstrap so the
# Cloudflare API token Secret can land here before the cert-manager chart
# itself is installed by ArgoCD. Both the ArgoCD-managed cert-manager
# Helm chart and the sync-wave-2 ClusterIssuers reference this same
# namespace by name.
apiVersion: v1
kind: Namespace
metadata:
  name: cert-manager
  labels:
    app.kubernetes.io/part-of: iyziops-platform
    pod-security.kubernetes.io/enforce: privileged
