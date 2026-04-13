# Overnight Sprint — 2026-04-14

Goal: extend the iyziops platform with the core self-service PaaS building blocks (monitoring, object storage, secrets management, image registry) without breaking the 13/15 Haven baseline, 100% hands-off.

Backup tag: `backup/main-pre-overnight-20260413-214826`.

Duration: ~4h of execution (phase-to-phase, excluding research).

Outcome: **Haven baseline preserved at 13/15**, 16 ArgoCD Applications Synced+Healthy, 4 new platform layers live.

---

## Phase 0 — Safety Net

- Pushed `backup/main-pre-overnight-20260413-214826` tag to origin for fast rollback.
- Verified all 12 existing apps Synced+Healthy before touching anything.
- `make haven` baseline: 13/15 PASS (multiaz + privatenetworking both NO, both require infra refactor).

## Phase 1 — Prometheus + Grafana

Added `kube-prometheus-stack` 66.3.1 at sync-wave 3 in `platform/argocd/appsets/platform-helm.yaml`.

Inline values:
- Prometheus 50Gi Longhorn, 15d retention, `retentionSize: 40GB`.
- Grafana 10Gi Longhorn, Loki pre-wired as secondary datasource (`http://loki.logging.svc.cluster.local:3100`).
- Alertmanager 10Gi Longhorn, 1 replica.
- Node-exporter DaemonSet with `tolerations: [operator: Exists]` so it runs on all 6 nodes (RKE2 masters carry `CriticalAddonsOnly=true:NoExecute`, default chart toleration only covers `NoSchedule`).
- RKE2 control-plane ServiceMonitors disabled (kubeControllerManager/Scheduler/Proxy/Etcd) — RKE2 hides these behind auth so Prometheus scrape would 401.
- `serviceMonitorSelectorNilUsesHelmValues: false` so Prometheus discovers ServiceMonitors cluster-wide.

PSA trap: monitoring namespace initially set to `baseline` — node-exporter still blocked (`hostPort` 9100 + `hostPID` + `hostNetwork` all denied). Bumped to `privileged` enforce, kept `restricted` audit/warn so non-exporter workloads still get flagged.

Grafana HTTPRoute: `grafana.iyziops.com` → ReferenceGrant (monitoring ns) → gateway https listener → `kube-prometheus-stack-grafana:80`. Covered by existing wildcard cert.

Grafana admin password: chart-generated random, stored in `kube-prometheus-stack-grafana` secret.

Commits: `90154a1`, `65bb2f2`, `3211863`.

## Phase 2 — MinIO

**Chart-picker trap**: First tried Bitnami `minio` chart (already in AppProject sourceRepos). 14.10.5 didn't exist (Bitnami moved post-14.8.5 to OCI-only), 14.8.5 pulled `docker.io/bitnami/minio:2024.11.7-debian-12-r0` which now 404s on Docker Hub (Bitnami legacy cutoff late-2025 — free public tarballs reaped).

Switch: official MinIO community chart from `https://charts.min.io` (5.4.0). Pulls `quay.io/minio/minio` (always free). Added to:
- `infrastructure/modules/rke2-cluster/manifests/argocd-projects.yaml.tpl` → `sourceRepos`
- Live `iyziops-platform` AppProject via `kubectl patch` (for this cluster; next `tofu apply` picks up the tpl change)

Chart config:
- Standalone mode (not distributed), 1 replica, 1 drive.
- 50Gi Longhorn PVC.
- `existingSecret: minio-credentials` — bootstrap secret created out-of-band via `kubectl create secret generic minio-credentials --from-literal=rootUser=admin --from-literal=rootPassword=<openssl rand 32>`. Phase 3+ migrates this to a Vault-backed ExternalSecret.
- Default buckets: `iyziops-backups`, `iyziops-registry`.
- ServiceMonitor with label `release: kube-prometheus-stack` so Prometheus Operator picks it up.
- `securityContext: { runAsUser: 1000, fsGroup: 1000, runAsNonRoot: true }` chart-native.

HTTPRoutes: `minio.iyziops.com` → port 9001 (console), `s3.iyziops.com` → port 9000 (S3 API). Both go through the same ReferenceGrant (minio-system ns).

**Cleanup trap**: when switching chart repos, the old Bitnami Deployment + PVC from the broken sync lingered. `kubectl delete deploy minio -n minio-system` + `kubectl delete pvc -n minio-system --all` forced ArgoCD to recreate with the new chart's resource set.

Commits: `305c915`, `b7c353c`, `930d579`.

## Phase 3 — Vault + External Secrets Operator

Two new elements at sync-wave 4 in `platform-helm.yaml`:

### Vault 0.29.1 (hashicorp/vault chart)
- `standalone.enabled: true`, file backend at `/vault/data`.
- 10Gi data + 10Gi audit Longhorn PVCs.
- `global.tlsDisable: true` — in-cluster traffic only, rely on CNI overlay confidentiality.
- Injector disabled (ESO is the preferred integration model).
- Image pinned `hashicorp/vault:1.18.2`.
- Post-deploy init/unseal (not automatable through ArgoCD):
  ```
  kubectl exec -n vault-system vault-0 -- vault operator init -key-shares=1 -key-threshold=1 -format=json
  kubectl exec -n vault-system vault-0 -- vault operator unseal <UNSEAL_KEY_B64>
  ```
- Unseal key + root token persisted to `vault-init` secret in vault-system namespace for operator retrieval.
- Configured via `vault` CLI inside the pod:
  - KV-v2 secret engine mounted at `iyziops/`.
  - Kubernetes auth method enabled (`kubernetes_host: https://kubernetes.default.svc.cluster.local:443`).
  - `iyziops-reader` policy with read/list on `iyziops/data/*` and `iyziops/metadata/*`.
  - K8s auth role `iyziops-reader` bound to `external-secrets` ServiceAccount in `external-secrets` namespace.

### External Secrets 0.10.7 (external-secrets/external-secrets chart)
- `external-secrets` namespace (PSA restricted — ESO is a plain controller, no hostPath).
- Controller + webhook + certController, 1 replica each.
- `installCRDs: true`.

### Round-trip verification
- Wrote `iyziops/test` KV with `hello=world foo=bar`.
- Applied an `ExternalSecret` pointing at `ClusterSecretStore/iyziops-vault`.
- ESO synced `vault-roundtrip-test` Secret in `external-secrets` namespace with both keys base64-encoded correctly (`d29ybGQ=` / `YmFy`).
- Cleaned up test artifacts.

### K8s 1.32 StatefulSet drift trap
Vault stayed `OutOfSync` (Healthy) after first sync because K8s 1.32 default-fills several fields on StatefulSets that the Helm chart does not emit:
- `spec.persistentVolumeClaimRetentionPolicy`
- `spec.ordinals`
- `spec.minReadySeconds`
- `spec.revisionHistoryLimit`
- `spec.volumeClaimTemplates[].spec.volumeMode` ← the real culprit
- `spec.volumeClaimTemplates[].apiVersion`
- `spec.volumeClaimTemplates[].kind`
- `spec.volumeClaimTemplates[].metadata.creationTimestamp`
- `spec.volumeClaimTemplates[].status`

Added all of these as `jqPathExpressions` under `ignoreDifferences` in the ApplicationSet template. Applies cluster-wide to every generated StatefulSet (vault, alertmanager, prometheus, loki singleBinary, harbor-database, harbor-redis) — drift is the same pattern everywhere because it's K8s-level, not chart-level.

Commits: `2cfa8e1`, `2053cf4`, `67d3300`.

## Phase 4 — Harbor

`harbor-system` namespace (PSA baseline).

Chart: `goharbor/harbor` 1.16.2 at wave 5 in `platform-helm.yaml`. Inline values:
- `expose.type: clusterIP`, internal TLS disabled. Gateway API terminates external TLS.
- `externalURL: https://harbor.iyziops.com`.
- Persistent storage: filesystem PVCs on Longhorn (50Gi registry + 5Gi jobservice + 5Gi database + 2Gi redis). MinIO S3 backend deferred — needs Vault ExternalSecret wiring to avoid secret-in-git.
- Bundled internal PostgreSQL + Redis (chart defaults).
- Trivy + Chartmuseum + exporter disabled for smaller footprint.
- Admin password `Harbor12345` (chart default; will rotate via Vault ExternalSecret in a follow-up).

HTTPRoute: `harbor.iyziops.com` → ReferenceGrant (harbor-system ns) → gateway https listener → `harbor:80` (nginx-proxy multiplexes portal + core + registry blob paths).

Commit: `d9c6a78`.

---

## Final State

### Cluster
- 6 nodes Ready (3 masters 4c/8Gi + 3 workers 8c/16Gi).
- 11 PVCs bound on Longhorn (total allocation after replication: ~240 Gi × 3 = ~720 Gi, well under 1290 Gi budget).
- 16 ArgoCD Applications — all Synced+Healthy:

| # | App | Layer | Wave |
|---|---|---|---|
| 1 | iyziops-root | root | — |
| 2 | platform-namespaces | platform-raw | 0 |
| 3 | platform-ingress | platform-raw | 0 |
| 4 | cert-manager | platform-helm | 0 |
| 5 | longhorn | platform-helm | 0 |
| 6 | kyverno | platform-helm | 0 |
| 7 | cert-manager-config | platform-raw | 1 |
| 8 | kyverno-policies | platform-raw | 1 |
| 9 | loki | platform-helm | 3 |
| 10 | alloy | platform-helm | 3 |
| 11 | kube-prometheus-stack | platform-helm | 3 |
| 12 | minio | platform-helm | 4 |
| 13 | vault | platform-helm | 4 |
| 14 | external-secrets | platform-helm | 4 |
| 15 | harbor | platform-helm | 5 |
| 16 | iyziops-api, iyziops-ui | tenant-management | 5 |

### Haven baseline
```
Results: 13 out of 15 checks passed, 0 skipped, 0 unknown.
FAIL: Infrastructure / Multiple availability zones in use
FAIL: Infrastructure / Private networking topology
```

Both remaining failures are infra-level and cannot be fixed from within the cluster — they need a tofu apply cycle (and in the case of multiaz, possibly a new Hetzner project). See the 15/15 roadmap doc for the concrete follow-up.

### Credentials — where they live

| Service | Namespace | Secret | Keys |
|---|---|---|---|
| Grafana admin | monitoring | `kube-prometheus-stack-grafana` | `admin-user` / `admin-password` |
| MinIO root | minio-system | `minio-credentials` | `rootUser` / `rootPassword` |
| Vault init | vault-system | `vault-init` | `unsealKey` / `rootToken` |
| Harbor admin | harbor-system | `harbor-core` | `HARBOR_ADMIN_PASSWORD` (fixed `Harbor12345`) |

All four should be migrated to `ExternalSecret` pointing at Vault KV once the operator has the time to populate `iyziops/grafana`, `iyziops/minio`, `iyziops/harbor`. Phase 3 already proved the round-trip works.

### Known issues (not blockers)
1. **Harbor admin password is the chart default (`Harbor12345`).** Rotate via Vault ExternalSecret in a follow-up.
2. **Harbor uses filesystem PVC blob backend, not MinIO S3.** Migration deferred — needs ExternalSecret wiring.
3. **Vault single-shard unseal.** Production should use 5-of-3 Shamir split + auto-unseal via GCP KMS / cloud-init-provided shard, but this cluster is iyziops-dev so single-shard is acceptable.
4. **cert-manager DNS-01 cleanup race** (pre-existing, documented in CLAUDE.md).

---

## Rollback recipe

```bash
# Full revert
git reset --hard backup/main-pre-overnight-20260413-214826
git push origin main --force-with-lease

# Then refresh ArgoCD
kubectl --kubeconfig=/tmp/iyziops-kubeconfig -n argocd annotate \
  application iyziops-root argocd.argoproj.io/refresh=hard --overwrite

# Or selective: just delete the new apps and their namespaces
kubectl --kubeconfig=/tmp/iyziops-kubeconfig -n argocd delete app \
  kube-prometheus-stack minio vault external-secrets harbor
kubectl --kubeconfig=/tmp/iyziops-kubeconfig delete ns \
  monitoring minio-system vault-system external-secrets harbor-system
```
