# Haven Compliance — Remediation Index

`make haven` çalıştırıldığında FAIL çıkan 3 kriter için pointer dokümanları. Her biri farklı bir sprint'e ait; bu klasör sadece yönlendirme, fix kodu YOK.

## Baseline: 12/15 PASS (2026-04-13, iyziops prod, Haven CLI v12.8.0)

JSON raporunun tam hali: `haven/reports/baseline-20260413.json` (ve `.txt`).

## Bilinen FAIL'ler (Haven CLI resmi check isimleriyle)

| # | Check name | Category | Dosya | Sprint | Durum |
|---|---|---|---|---|---|
| 1 | `multiaz` | Infrastructure | `01-multi-az.md` | Phase 2 Cyso | **ACCEPTED** — Hetzner fsn1 tek-region mimari kısıt |
| 2 | `privatenetworking` | Infrastructure | `07-private-networking.md` | Sprint H-net-private | Investigation needed — Option A/B/C trade-off |
| 3 | `logs` | Haven+ | `13-log-aggregation.md` | Sprint H-obs-loki | Loki + Promtail deploy |

## Aslında PASS olan (önceki custom audit yanılmıştı)

Bizim önceki custom bash audit'imiz şu FAIL'leri iddia ediyordu, ama **resmi Haven CLI bunları PASS veriyor** ya da hiç check etmiyor:

| Custom audit claim | Haven CLI gerçeği |
|---|---|
| "kubectl OIDC gerekli" | Haven CLI OIDC'yi kontrol etmiyor — sadece kubeconfig çalışıyor mu diye bakıyor. PASS. |
| "Prometheus + Grafana gerekli" | Haven CLI sadece `metrics-server` arıyor (HPA için). rke2-metrics-server var → PASS. |
| "CIS Hardening explicit profile verify" | CIS check'i Haven CLI'da "Suggested" kategoride, `--cis` flag ile opt-in. Default check listesinde YOK. |

**Ders**: Upstream tool'un gerçek check listesini custom audit'le tahmin etmek yerine binary'yi çalıştır ve output'tan doğrula.

## Baseline'dan bu yana değişenler

Değişim olduğunda bu section güncellenir (her remediation sprint tamamlandığında yeni baseline eklenir).

## Upstream Kaynaklar

- Docs: https://haven.commonground.nl/techniek/compliancy-checker
- Source: https://gitlab.com/commonground/haven/haven
- Rationale (her check için neden önemli): `haven check --rationale`
