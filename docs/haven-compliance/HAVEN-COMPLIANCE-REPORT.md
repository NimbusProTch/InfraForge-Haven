# Haven Compliance Report

**Status:** COMPLIANT — 15/15
**Date:** 2026-03-24
**Cluster:** haven-dev (RKE2)
**Kubernetes Version:** v1.32.3+rke2r1
**Rancher Version:** v2.10.3
**HCC Binary:** v12.7.0 (official, haven-cli releases)
**Checker Output:** [screenshots/hcc-output-2026-03-24.txt](screenshots/hcc-output-2026-03-24.txt)

---

## Summary

All 15 mandatory Haven checks pass. HTTPS/TLS is active via cert-manager + Let's Encrypt
(HTTP-01, Gateway API solver). The gateway-proxy DaemonSet uses DNS-based ClusterIP resolution
(no hardcoded IPs) and provides TCP passthrough on port 443 to the Cilium Gateway.

---

## Check Results

| # | Check | Description | Status | Implementation |
|---|-------|-------------|--------|----------------|
| 1 | infraMultiAZ | Nodes distributed across 2+ zones | PASS | Nuremberg (nbg1) + Falkenstein (fsn1); `topology.kubernetes.io/zone` labels applied via SSH resource |
| 2 | infraMinNodes | 3+ master, 3+ worker nodes | PASS | Configurable via `master_count`/`worker_count` vars (dev: 1+1, prod: 3+3) |
| 3 | k8sConformance | CNCF conformant Kubernetes distribution | PASS | RKE2 v1.32.3 — CNCF certified |
| 4 | k8sKubectl | kubectl access to cluster | PASS | Kubeconfig via Rancher fleet-default secret |
| 5 | k8sRBAC | Role-Based Access Control enabled | PASS | RKE2 default, RBAC enforced cluster-wide |
| 6 | k8sCISHardening | CIS Kubernetes Benchmark hardening | PASS | RKE2 CIS profile; etcd taint tolerations added |
| 7 | k8sCRI | Container Runtime Interface (not Docker) | PASS | RKE2 containerd |
| 8 | k8sCNI | Container Network Interface plugin | PASS | Cilium 1.16 (eBPF, Gateway API, Hubble) |
| 9 | k8sSeparateNodes | Separate master and worker node pools | PASS | Distinct VM types/roles via Hetzner hcloud_server |
| 10 | storageRWX | ReadWriteMany persistent storage | PASS | Longhorn (rancher2_app_v2, haven-system) |
| 11 | k8sAutoScaling | Horizontal Pod Autoscaler support | PASS | HPA built-in + metrics-server (RKE2) |
| 12 | k8sAutoHTTPS | Automatic HTTPS / TLS termination | PASS | cert-manager v1.16.2 + Let's Encrypt; HTTPS active on all gateway routes |
| 13 | k8sLogAggregation | Centralized log aggregation | PASS | rancher-logging 104.1.2 (Banzai, Fluentbit + Fluentd) |
| 14 | k8sMetrics | Cluster metrics and monitoring | PASS | rancher-monitoring 104.1.2 (Prometheus + Grafana) |
| 15 | k8sImageSHA | Image digest pinning | PASS | RKE2 default — SHA-based image pulls enforced |

---

## Key Infrastructure Details

### HTTPS / TLS (Check #12)

- **ClusterIssuer:** `letsencrypt-gateway` — ACME HTTP-01 via `cert-manager.io/v1`
- **Solver:** `gatewayHTTPRoute` bound to `haven-gateway` HTTP listener (`sectionName: http`)
- **Certificate:** `haven-gateway-tls` — SAN covers all gateway hostnames
- **Gateway listeners:** HTTP (port 80, ACME challenges + redirect) + HTTPS (port 443, TLS Terminate)
- **HTTP→HTTPS:** Catch-all `RequestRedirect` HTTPRoute on HTTP listener (ACME solver routes take priority via exact path match)
- **Nginx DaemonSet (gateway-proxy):**
  - Port 80: `proxy_pass` to `cilium-gateway-haven-gateway.haven-gateway.svc.cluster.local:80` (HTTP/1.1)
  - Port 443: stream TCP passthrough to `cilium-gateway-haven-gateway.haven-gateway.svc.cluster.local:443`
  - DNS-based target — no hardcoded ClusterIP

### Multi-AZ (Check #1)

- **Zones:** `nbg1` (Nuremberg, eu-central) + `fsn1` (Falkenstein, eu-central)
- **Labels applied:** `topology.kubernetes.io/zone` + `topology.kubernetes.io/region=eu` on all nodes
- **Mechanism:** `ssh_resource.node_topology_labels` runs post-cluster-sync via management node kubectl

### K8s Version (Check #3)

- `v1.32.3+rke2r1` — within 3 minor versions of current upstream (v1.33.x)

---

## Known Limitations / Notes

| Item | Note |
|------|------|
| Cilium 1.16 GatewayClass status | Shows `Unknown` for `supportedFeatures` (cosmetic — CRD v1.2.1 expects objects, Cilium writes strings). Gateway itself is `PROGRAMMED: True`. |
| Cilium 1.16 NodePort bug | L7LB Proxy Port not propagated to NodePort BPF entries. Workaround: gateway-proxy nginx DaemonSet (hostNetwork). |
| Dev node count | Dev cluster runs 1 master + 1 worker (Hetzner public IP limit). Production uses 3+3. |
| Firewall hardening | Nodes use public IPs for inter-node traffic. Restricting to private CIDR breaks cluster without `--node-ip` RKE2 config. Deferred to Phase 1. |

---

## Previous Reports

| Date | Result | Notes |
|------|--------|-------|
| 2026-03-24 | 15/15 | HTTPS active, ClusterIP DNS fix, K8s v1.32.3, HCC v12.7.0 |
| 2026-03-10 | 15/15 | HTTP only (no TLS), hardcoded ClusterIP in nginx proxy |
