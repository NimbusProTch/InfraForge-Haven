---
# Pre-create longhorn-system at cluster bootstrap with the `privileged`
# Pod Security admission profile. RKE2 CIS mode defaults unlabelled
# namespaces to the `restricted` profile, which refuses Longhorn's
# longhorn-manager DaemonSet (needs privileged=true, hostPath /dev +
# /sys, NET_ADMIN) with `FailedCreate: violates PodSecurity
# "restricted:latest"` — the helm-install job then never lands a pod
# and Longhorn never starts. Creating the namespace up front with the
# right labels means the ArgoCD Longhorn Application just lands on top
# of an already-labelled namespace and everything schedules cleanly.
apiVersion: v1
kind: Namespace
metadata:
  name: longhorn-system
  labels:
    app.kubernetes.io/part-of: iyziops-platform
    pod-security.kubernetes.io/enforce: privileged
    pod-security.kubernetes.io/audit: privileged
    pod-security.kubernetes.io/warn: privileged
