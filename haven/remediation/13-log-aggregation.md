# Remediation #13 — logs (Log aggregation is running)

## Durum: **Deferred → Sprint H-obs-loki**

## Haven kriteri (v12.8.0 JSON output'tan alınan resmi ifade)

```json
{
  "Name": "logs",
  "Label": "Log aggregation is running",
  "Category": "Haven+",
  "Rationale": "In order to be in control of the workload on a cluster it's mandatory to aggregate all container logs.",
  "Result": "NO"
}
```

## Canlı durum

iyziops prod cluster'da şu an hiçbir log aggregation stack kurulu değil:
```
$ kubectl get pods -A | grep -iE 'loki|promtail|fluentd|fluent-bit|vector'
(no output)
```

## Hedef stack

**Loki + Promtail** (Grafana Labs, CNCF, Helm chart mature):
- `loki`: StatefulSet with Longhorn PVC (ya da S3 backend — MinIO)
- `promtail`: DaemonSet her node'da, kubelet log stream'lerini tail eder
- Optional: Grafana ile data source entegrasyonu (metrics sprint ile birlikte)

## Haven CLI'ın ne beklediği (tahmin)

Haven source code incelenmeden kesin bilinmiyor, ama muhtemelen:
- `logging` veya benzeri namespace'de Loki/Fluentd/Vector pod'ları
- DaemonSet yapısında log collector (Promtail/Fluentbit)
- Container log'ları cluster dışına ya da persistent storage'a export ediliyor

Loki+Promtail kurulumu bu gereksinimi karşılamalı. İlk deploy sonrası `make haven` yeniden çalıştırılıp doğrulanacak.

## Install komutları (sprint'te çalıştırılacak, şimdi DEĞİL)

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Simpler: loki-stack meta-chart (dev tier)
helm upgrade --install loki grafana/loki-stack \
  --namespace logging --create-namespace \
  --set loki.persistence.enabled=true \
  --set loki.persistence.storageClassName=longhorn \
  --set loki.persistence.size=50Gi \
  --set promtail.enabled=true
```

## ArgoCD entegrasyonu (GitOps-compliant)

`platform/argocd/appsets/platform-services.yaml` içine yeni generator:

```yaml
- name: loki
  namespace: logging
  syncWave: "3"
  repoURL: https://grafana.github.io/helm-charts
  chart: loki-stack
  targetRevision: 2.10.2  # pin
  values: |
    loki:
      persistence:
        enabled: true
        storageClassName: longhorn
        size: 50Gi
    promtail:
      enabled: true
```

## Storage + retention

- Dev tier: 30 gün retention, Longhorn PVC 50Gi
- Prod tier: 90 gün retention, S3/MinIO backend
- Backup: MinIO + Longhorn snapshot

## Sprint tahmini

- Helm values hazırlığı: 0.25 sprint
- ArgoCD Application + sync: 0.25 sprint
- Retention + storage sizing: 0.25 sprint
- `make haven` doğrulama: 0.25 sprint
- **Toplam: ~1 sprint**

## Bu plan kapsamı dışı

Bu sprint sadece `make haven` altyapısı + baseline. Loki deploy ayrı PR.
