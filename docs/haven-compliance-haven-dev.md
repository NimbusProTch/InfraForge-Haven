# Haven Compliance Snapshot — Haven Dev Cluster (2026-04-09)

> Arşivlenmiş compliance tablosu. CLAUDE.md'den taşındı 2026-04-13.
> Bu tablo **eski Haven dev cluster'ına** (Rancher-based, Hetzner nbg1+hel1) ait.
> iyziops prod Option B mimarisi taze — tablo re-baseline edilecek. Güncel compliance durumu için: bir sonraki Haven-check sprint'i.

## Gerçek skor: 13/15 (canlı doğrulanmış 2026-04-09 sabah)

> **Tarihçe**: Tablo bir zamanlar "15/15" idi ama 5-agent + 4-tur audit gerçek skoru `11.5/15` çıkardı. Sprint H0 → H4 sonrası **13/15** — kalan 2 maddeden biri `tofu apply` bekliyordu (kod hazır, lokal tfvars'ta), diğeri yeni kod gerektiriyordu.

| # | Check | Durum (Haven dev) | Status |
|---|---|---|---|
| 1 | Multi-AZ | Cluster `nbg1+hel1` (Helsinki). `terraform.tfvars` `location_secondary = "fsn1"` kod-hazır ama apply bekliyor (~60 dk node rebuild). | ⚠️ KOD HAZIR |
| 2 | 3+ master, 3+ worker | 3 master + 3 worker, hepsi Ready | ✅ |
| 3 | CNCF Conformance | RKE2 v1.32.3+rke2r1 — certified list'te | ✅ |
| 4 | kubectl access via OIDC | RKE2 master cloud-init'te `--oidc-issuer-url` flag YOK. `keycloak/haven-realm.json`'da `groups` protocolMapper YOK. PR henüz yok. | ❌ BROKEN |
| 5 | RBAC | Rogue `haven-api-admin → cluster-admin` binding silindi (#89 + #106). ClusterRole privilege escalation gap kapatıldı. `kubectl auth can-i '*' '*' --as=...haven-api` → **no** | ✅ |
| 6 | CIS Hardening | `enable_cis_profile = true`, etcd taint tolerations eklendi | ✅ |
| 7 | CRI containerd | RKE2 default `containerd://2.0.4-k3s2` | ✅ |
| 8 | CNI Cilium + Hubble | Cilium 6 pod Running, Hubble enabled. WireGuard encryption kod-default `true` (#112) | ✅ |
| 9 | Separate master/worker | Distinct VM'ler, label'lar ayrı | ✅ |
| 10 | RWX Storage Longhorn | Default storage class, PVC'ler bağlı | ✅ |
| 11 | Auto-scaling HPA | metrics-server çalışıyor, HPA test edildi | ✅ |
| 12 | Auto HTTPS cert-manager | 14+ Certificate Ready=True, real Let's Encrypt | ✅ |
| 13 | Log aggregation Loki | loki-stack + 6 promtail node, log akıyor | ✅ |
| 14 | Metrics Prometheus + Grafana | Tüm pod'lar Running, ServiceMonitor scraping | ✅ |
| 15 | Image SHA digest | haven-api/haven-ui `@sha256:...` formatında deploy ediliyor (#99 + #105). CI pipeline `docker/build-push-action@v6` digest'i yakalıyor. | ✅ |

**Son skor: 13/15 ✅ + 1 kod-hazır-apply-bekliyor + 1 kırık.** Sprint H1a-1 (Multi-AZ apply) → 14/15. Sprint H1a-2 (kubectl OIDC) → 15/15.

## Doğrulama kuralı

Müşteriye "Haven compliant" denmeden önce tablodaki ⚠️/❌ maddelerin **gerçek implementation'ı** doğrulanmalıdır. Sadece "kodda var" yetmez. Canlı doğrulama komutları:

```bash
kubectl get nodes -L topology.kubernetes.io/zone
kubectl --token=$T get pods -n tenant-X
kubectl get pod ... -o jsonpath='{.spec.containers[*].image}'
```
