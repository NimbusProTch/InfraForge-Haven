# Remediation #1 — infraMultiAZ

## Durum: **ACCEPTED** (mimari kısıt, fix edilmiyor)

## Haven kriteri

`infraMultiAZ` — Nodes distributed across 2+ availability zones (`topology.kubernetes.io/zone` labels on nodes).

## Canlı durum

iyziops prod cluster'ı Hetzner `fsn1-dc14` data center'ında, tek zone'da çalışıyor. Tüm 6 node aynı zone etiketine sahip:

```
$ kubectl get nodes -L topology.kubernetes.io/zone
NAME               STATUS   ROLES                       ZONE
iyziops-master-0   Ready    control-plane,etcd,master   fsn1-dc14
iyziops-master-1   Ready    control-plane,etcd,master   fsn1-dc14
iyziops-master-2   Ready    control-plane,etcd,master   fsn1-dc14
iyziops-worker-0   Ready    <none>                      fsn1-dc14
iyziops-worker-1   Ready    <none>                      fsn1-dc14
iyziops-worker-2   Ready    <none>                      fsn1-dc14
```

## Neden fix edilmiyor

Hetzner Cloud, **tek bir availability zone içinde** cluster çalıştırmayı hedefliyor. Multi-AZ için 2 yol var:

1. **Cross-region cluster** (fsn1 + nbg1 + hel1 karışık): Ağ latency'si yüksek (20-40 ms inter-region), etcd quorum stability'sini tehdit eder. Hetzner bu setup'ı **önermez** ve officially desteklemez.
2. **Multi-provider** (Hetzner + başka cloud): cost + complexity patlaması, Cilium native routing Hetzner'a özel.

**Sonuç**: iyziops dev + staging Hetzner single-zone'da çalışacak. Production Haven deployment (Phase 2) **Cyso Cloud Amsterdam** veya **Leafcloud**'a migrate olacak — onlar gerçek multi-AZ sağlıyor (Amsterdam AM2/AM3/AM4 region'ları).

## Fix sprint

**Phase 2 — Cyso Cloud Migration** (tarih TBD, 2026 Q3+ bekleniyor):
- Terraform OpenStack provider ile yeni cluster
- Multi-AZ node dağıtımı: master-{0,1,2} → farklı AZ'ler, worker'lar da öyle
- `topology.kubernetes.io/zone` label'ları otomatik (OpenStack CCM sağlar)
- Bu noktada `haven check` kendiliğinden PASS verecek

## Geçici davranış

`make haven` bu criterion'da her zaman FAIL dönecek. Bu bilinen + kabul edilmiş durum. Toplam skor raporu 14/15 veya daha düşük olduğunda paniklemeyin — Multi-AZ FAIL mimari kararımızın bilinçli parçası.

## İlgili issue'lar

- VNG Haven Community'de "single-zone dev cluster" tartışması: https://gitlab.com/commonground/haven/haven/-/issues (search "multi-az")
- Hetzner kube-hetzner community: genelde single-zone kabul edilir
