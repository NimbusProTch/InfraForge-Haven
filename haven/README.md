# Haven Compliance Gate

Resmi [VNG Haven Compliancy Checker](https://haven.commonground.nl/techniek/compliancy-checker) CLI'ını indirip cluster'a karşı çalıştıran ince wrapper. Custom check kodu yok — upstream tool'a tam delegasyon.

## Quick start

```bash
make haven              # Default cluster (prod) — human-readable scoreboard
make haven-json         # JSON (pipe to jq)
make haven-cis          # + external CIS Kubernetes Benchmark
make haven-all          # + CIS + Kubescape (full external checks)
```

İlk çalıştırma `haven/install.sh` üzerinden `haven v12.8.0` binary'sini GitLab package registry'den indirir (~14 MB). Sonraki çağrılar cached binary'yi kullanır (`haven/bin/haven`, gitignored).

## Dosyalar

| Path | Amaç |
|---|---|
| `VERSION` | Pin'lenmiş CLI version (bump etmek için düzenle) |
| `install.sh` | Idempotent downloader (OS/arch detect + curl + unzip + install) |
| `bin/haven` | Downloaded binary (gitignored, her OS/arch için ayrı) |
| `reports/` | Generated run output'ları (gitignored) |
| `remediation/` | Bilinen FAIL'ler için pointer dokümanlar + fix sprint referansları |

## Upgrade etmek

```bash
echo v12.9.0 > haven/VERSION      # Yeni version pin'le
make haven-install                # Re-download
make haven                        # Yeniden çalıştır
```

## Kaynak

- **Upstream docs**: https://haven.commonground.nl/techniek/compliancy-checker
- **GitLab repo**: https://gitlab.com/commonground/haven/haven
- **Releases**: https://gitlab.com/commonground/haven/haven/-/releases
- **Package registry**: https://gitlab.com/commonground/haven/haven/-/packages

Check tanımları, exit code'ları, output format'ı — hepsi upstream VNG Common Ground ekibinin sorumluluğunda. Bu repoda re-implement ETME.

## Bilinen FAIL'ler (bu sprint'te fix edilmez)

| # | Criterion | Durum | Fix sprint |
|---|---|---|---|
| 1 | Multi-AZ | Hetzner fsn1 tek-region mimari kısıt | Phase 2 Cyso Cloud migration |
| 4 | kubectl OIDC | Keycloak realm + kube-apiserver flag'leri yok | Sprint H1a-OIDC |
| 13 | Log aggregation (Loki) | Observability stack kurulmadı | Sprint H-obs-loki |
| 14 | Metrics (Prometheus+Grafana) | Observability stack kurulmadı | Sprint H-obs-metrics |

Detay: `haven/remediation/` altındaki per-item pointer dosyaları.

## CI integration

Post-merge + nightly CI gate için: `.github/workflows/haven-compliance.yml`. Secret `IYZIOPS_KUBECONFIG` GitHub Secrets'a eklenmeli (operator action).
