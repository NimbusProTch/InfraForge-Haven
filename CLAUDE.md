# Haven Platform / iyziops — Proje Hafızası

> Bu dosya her session'da context'e yüklenir. Şişirilmemeli.
>
> - **Canlı durum** (kubeconfig, son session, next steps) → Claude Code auto-memory `memory/RESUME_HERE.md` (repo dışı, kullanıcı home'u)
> - **Mimari detay** (GitOps flow, 10 architectural decisions) → `.claude/CLAUDE.md`
> - **Sprint tarihçesi** (tamamlanan phase'ler + test count'lar) → `docs/sprints/PHASE_HISTORY.md`

## Proje Nedir?

Haven-Compliant Self-Service DevOps Platform (PaaS). Hollanda'daki 342 belediye için VNG Haven standardına uygun Kubernetes altyapısı üzerine Heroku/Railway benzeri self-service platform. EU data sovereignty garantili.

> **İsimlendirme notu**: Ürün adı **Haven Platform → iyziops** olarak yeniden adlandırılıyor. Mimari/manifestler çoğu yerde hâlâ `haven-*`. "VNG Haven" compliance standardı değişmez. Rename planı: `docs/sprints/RENAME_IYZIOPS_PLAN.md`.

## Tech Stack

| Katman | Teknoloji |
|---|---|
| IaC | OpenTofu (Terraform fork, CNCF) |
| K8s Dağıtımı | RKE2 (CIS hardened, CNCF certified) |
| Cluster Mgmt | RKE2 Helm Controller (vanilla, Rancher YOK) |
| CNI | Cilium (eBPF, Gateway API, Hubble, WireGuard) |
| Ingress | Cilium Gateway API + Hetzner CCM (2-LB pattern) |
| Storage | Longhorn (CNCF, RWX) |
| TLS | Cert-Manager + Let's Encrypt (DNS-01 via Cloudflare) |
| DNS | Cloudflare (manual + External-DNS Phase 2) |
| Auth | Keycloak (realm-per-tenant, OIDC) |
| GitOps | ArgoCD (app-of-apps + per-tenant ApplicationSet) |
| Git Server | Gitea / Forgejo (self-hosted, tenant repos) |
| App Build | BuildKit + Nixpacks (5x faster than Kaniko) |
| Registry | Harbor (self-hosted, Trivy scan) |
| DB (managed) | CNPG (PG), Percona Everest (MySQL/MongoDB), Redis OpsTree, RabbitMQ Operator |
| Secrets | HashiCorp Vault + External Secrets Operator |
| Backup | MinIO S3 per-tenant (PITR) |
| Monitoring | Grafana + Loki + Mimir + Hubble UI |
| Queue | Redis (git writer serialization) |
| Backend | Python 3.12 / FastAPI |
| Frontend | Next.js 14 / shadcn/ui |
| Dev Cloud | Hetzner (Falkenstein fsn1) |
| Prod Cloud | Cyso Cloud / Leafcloud Amsterdam (Phase 2+) |

## Mimari Kararlar

### IaC: Her Şey Kod
UI sadece monitoring/dashboard. Oluşturma/güncelleme/silme hep OpenTofu + GitOps. `tofu apply` → ArgoCD sync → Haven check. Direkt `kubectl apply` yalnızca bootstrap için.

### iyziops Option B: 2-LB + Hetzner CCM + Cilium Gateway
- **2 Hetzner LB**: API LB (tofu-managed, 6443) + ingress LB (tofu shell, CCM adopts via `load-balancer.hetzner.cloud/name` annotation on auto-generated Service). CCM tek LB'yi tofu ile paylaşamıyor (`ReconcileHCLBServices` Service spec'inde olmayan portları siler).
- **Hetzner CCM as raw manifest**: `helm.cattle.io/v1 HelmChart` kullanılamaz — helm-install Job pod'u `node.cloudprovider.kubernetes.io/uninitialized` taint'ini tolere etmez, bootstrap deadlock. Fix: CCM'yi Deployment+SA+ClusterRoleBinding olarak `/var/lib/rancher/rke2/server/manifests/` altına yaz.
- **Gateway API CRDs runtime fetch**: Master cloud-init runcmd ile `curl github.com/kubernetes-sigs/gateway-api/.../experimental-install.yaml` + `kubectl apply --server-side`. Bundle ~600KB, Hetzner 32KB user_data limitini aşıyor.
- **Cilium standard LoadBalancer path**: hostNetwork YOK, `k8sServiceHost=127.0.0.1` (RKE2 agent local LB), WireGuard encryption, tunnel routing. Gateway API CRD'leri kurulduktan sonra `kubectl rollout restart deploy/cilium-operator` zorunlu (CRD detection startup-only).

### Multi-Tenancy: 5 Katmanlı İzolasyon
1. **Namespace**: `tenant-{slug}`
2. **CiliumNetworkPolicy**: L7 izolasyon
3. **ResourceQuota**: CPU/RAM/Disk limitleri
4. **RBAC**: Tenant admin sadece kendi namespace'i
5. **Keycloak**: Tenant başına realm

### GitOps-First + Queue-Based Git Writer
Tüm state değişiklikleri Gitea → ArgoCD'den akar. Concurrent commit conflict'lerini önlemek için tek Redis FIFO queue worker'ı (`api/app/workers/git_worker.py`) tüm git commit'leri seri işler. DLQ (`haven:git:dlq`) 3 retry sonrası fail'leri yakalar.

### ApplicationSet per Tenant
Tek `tenants` ArgoCD ApplicationSet'i (git generator) `gitops/tenants/*` altındaki her dizini otomatik `tenant-{slug}` Application'a çeviriyor (`platform/argocd/appsets/tenants.yaml`). Yeni app deploy'u API çağrısı gerektirmez; git directory'ye values.yaml düşer, generator otomatik keşfeder. (Per-app ayrı ApplicationSet YOK.)

### Vault + External Secrets for Sensitive Vars
Non-sensitive env vars → `values.yaml` (plaintext, version-controlled). Sensitive vars (DB passwords, API keys) → Vault → ESO `ExternalSecret` CRD → K8s Secret. UI'da `🔒` toggle ile mark ediliyor.

### Managed DB via Helm Charts
Her DB tipi için `charts/haven-{pg,mysql,mongodb,redis,rabbitmq}/` altında Helm wrapper. DB provision = GitOps repo'ya yeni values.yaml push → ArgoCD → CNPG/Percona/OpsTree CRD. Connection string otomatik app'in values.yaml'ına `DATABASE_URL` olarak enjekte edilir.

### BuildKit > Kaniko
BuildKit paralel layer build + akıllı cache (5x hız). `haven-builds` ns'inde Deployment olarak çalışır, `buildctl` Job submission. Nixpacks dil/framework auto-detect + fallback Dockerfile generation.

### Build Log Streaming via SSE
Build logs K8s Pod logs'tan Server-Sent Events ile akıyor. ANSI escape codes browser'da `ansi-to-html` ile render. Hard timeout: 10dk. No-output timeout: 2dk.

### Backup: MinIO per Tenant
Her tenant kendi MinIO bucket'ına sahip (`backups-{slug}`). CNPG WAL archiving ile PITR. Scheduled backup 02:00 UTC, on-demand backup API endpoint'i ile.

## Konvansiyonlar

### Python / FastAPI
- Python 3.12+, type hints zorunlu
- Pydantic v2 (`model_validator`, `field_validator`)
- SQLAlchemy 2.0 async (`mapped_column`, `DeclarativeBase`)
- Ruff linter + formatter (`line-length = 120`)
- Import sırası: stdlib → third-party → local
- Router: `api/app/routers/{resource}.py`
- Service: `api/app/services/{domain}.py`
- Test: `api/tests/test_{module}.py`

### TypeScript / Next.js
- Next.js 14 App Router (Pages Router YOK)
- shadcn/ui (reinvent etme)
- `export const dynamic = "force-dynamic"` useSearchParams'lı sayfalarda
- Suspense boundary zorunlu

### OpenTofu / HCL
- Module: `infrastructure/modules/{provider}-{resource}/`
- Environment: `infrastructure/environments/{env}/`
- Helm templates: module içinde `templates/*.yaml.tpl`
- Secrets: macOS Keychain (`iyziops-env` loader) + tfvars (gitignored), hardcode YASAK
- `.claude/rules/iac-discipline.md`: 10 zorunlu IaC kuralı (200 satır cap, inline kubectl/curl yasak, vb.)

### Git
- Conventional commits: `feat:`, `fix:`, `infra:`, `docs:`
- Kod yorumları İngilizce, CLAUDE.md + docs Türkçe
- Feature branch → PR → architect+tester agent review → merge
- Main'e direkt push YASAK

### CI/CD
- Self-hosted runner: `runs-on: [self-hosted, haven]` (ubuntu-latest YASAK)
- PostgreSQL testlerde docker run step (service container DEĞİL)
- Makefile her operasyon için (`make api-test`, `make ci`, `make deploy-check` — bkz. `.claude/rules/conventions.md`)

### Genel
- Dil: Türkçe (CLAUDE.md, dokümantasyon)
- Kod içi isimler + yorumlar: İngilizce
- Secret'lar: `.env` (gitignored), prod'da K8s Secret / Vault / ESO
- Para harcamamak için test bitince `tofu destroy`

## iyziops Option B Gotcha'ları (aktif)

Geçen sprint'te gerçekten çarpan tuzaklar:

- **Hetzner CCM bootstrap deadlock**: `helm.cattle.io/v1 HelmChart` for `hcloud-cloud-controller-manager` asla complete olmaz — helm-install Job pod'u `node.cloudprovider.kubernetes.io/uninitialized:NoSchedule` tolerate etmez. Her node CCM gelene kadar taint'li, ama CCM Job zamanlanamıyor. Fix: CCM'yi raw Deployment+SA+ClusterRoleBinding olarak `/var/lib/rancher/rke2/server/manifests/` altına yaz (`infrastructure/modules/rke2-cluster/manifests/hetzner-ccm.yaml.tpl`). Manifest applier rke2-server içinde çalışır, Pod scheduling yok.

- **Cilium operator Gateway API CRD detection startup-only**: CRD presence kontrolü bir kez yapılır, re-check yok. Fresh cluster'da Cilium ArgoCD'den önce boot ettiğinden CRD'ler sonradan geliyor. Fix: `kubectl rollout restart deploy/cilium-operator -n kube-system` gateway-api-crds Application sync'i sonrası.

- **gateway-api-crds runtime fetch (mevcut implementasyon)**: Gateway API CRD'leri ArgoCD ile DEĞİL, ilk master cloud-init runcmd'sinde `curl ... experimental-install.yaml | kubectl apply --server-side` ile kuruluyor (`master-cloud-init.yaml.tpl:~250`, pin `var.gateway_api_version` v1.2.0) — ArgoCD/Cilium boot'undan önce. Eski tasarım (sibling `appsets/gateway-api-crds.yaml` sync-wave -10) UYGULANMADI; K8s label'ları negatif sync-wave kabul etmiyor, cloud-init pre-install bu sırayı zaten garantiliyor.

- **cert-manager Cloudflare DNS-01 cleanup race (RESOLVED 2026-04-13)**: cert-manager **v1.17.0** Cloudflare'in Şubat 2025 API değişikliğine uyumsuzdu — DNS record response'larında `zone_id` alanı kaldırıldı, v1.17.0'ın cleanup kodu empty zone ID ile `DELETE /zones//dns_records/<id>` gönderiyor, error 7003 ile fail ediyordu. Fresh bootstrap'te `iyziops-wildcard` cert `Issuing`'de takılıyor, stale `_acme-challenge.iyziops.com` TXT'leri birikiyordu. **Kalıcı fix**: cert-manager v1.17.0 → **v1.20.2** upgrade ([PR #7549](https://github.com/cert-manager/cert-manager/pull/7549)). Token permission ile ilgisi yoktu (önceki session'ın notu hatalıydı). Fix: `platform/argocd/appsets/platform-helm.yaml` cert-manager generator `targetRevision: v1.20.2` + `installCRDs: true` → `crds.enabled: true + crds.keep: true` (v1.20 chart schema).

- **iyziops-platform-repo secret vestigial sshPrivateKey**: Bootstrap manifest `sshPrivateKey` field'ı ile Secret oluşturuyor ama GitOps repo public HTTPS. ArgoCD SSH auth'a zorlanıp `ssh: no key found` ile fail ediyor. Fix: `kubectl patch secret iyziops-platform-repo --type=json -p='[{"op":"remove","path":"/data/sshPrivateKey"}]'`. Kalıcı: template'ten field'ı sil.

- **kube-hetzner 2-LB pattern annotation**: ingress LB tofu shell'inde `lifecycle { ignore_changes = [target, labels["hcloud-ccm/service-uid"]] }`. `iyziops-gateway.yaml`'da `spec.infrastructure.annotations` → Cilium v1.17.1 bu annotation'ları generated LoadBalancer Service'e propagate eder → CCM `load-balancer.hetzner.cloud/name` ile adopt eder. Annotation literal Hetzner LB adı ile match etmeli.

- **CCM ingress LB adoption race (Phase C16 — AÇIK/PARTIAL, restart korunuyor)**: Tofu shell oluşturulduktan sonra CCM Cilium-generated Service'i annotation'sız görüp YENİ LB yaratabiliyor (Cilium operator annotation'ı 1-2s sonra Service'e kopyalıyor). Tofu shell dormant kalıyor, gerçek LB CCM-managed ID'de. Destroy'da tofu kendi shell'ini siliyor, orphan LB kalabiliyor. **Şu anki durum (2026-06-16)**: yalnızca ingress LB resource'unda `lifecycle { ignore_changes = [...] }` var; master cloud-init `cilium-operator rollout restart` runcmd'si **hâlâ duruyor** (`master-cloud-init.yaml.tpl:~254`). **Önerilen ama HENÜZ UYGULANMADI**: restart'ı kaldırmak race'i kapatır, AMA bu cluster RKE2 v1.32.3 ile **Cilium 1.16.x** kullanıyor — restart'ın gereksiz olduğu "dynamic Gateway-CRD detection" eşiği dokümante olarak 1.17+; üstelik upstream [cilium#34075](https://github.com/cilium/cilium/issues/34075) 1.16'da Gateway API'nin ds restart'ında bozulduğunu gösteriyor. Yani restart'ı körlemesine kaldırmak **fresh bring-up'ta ingress'i bozma riski** taşıyor. **Karar**: restart-kaldırma bir sonraki canlı bring-up'ta gözleme bağlandı (LB sayısı 1 mi 2 mi + Gateway PROGRAMMED mı?) — kanıtla karar verilecek. **REDDEDİLDİ**: `provisioner "local-exec" { when = destroy }` ile orphan GC → repo'da hiç kullanılmayan `hcloud` CLI + token plumbing gerektirir ve iac-discipline Rule 2 (bash-in-HCL yasağı) ihlal eder; yeniden eklenmesin (guard: `scripts/test_destroy_safety.sh`).

- **CCM route-controller orphan routes (RESOLVED 2026-06-16, Phase C14)**: CCM route-controller her node için `10.42.X.0/24 → <node-private-ip>` route'larını Hetzner network'e yazıyordu. Cilium tunnel mode bunları kullanmıyor ama yazılmaya devam ediyordu → destroy'da node'lar gidince orphan referans → subnet destroy 5+ dk takılıyordu. **Uygulandı**: `hetzner-ccm.yaml.tpl` CCM args'ına `--controllers=*,-route` eklendi (k8s standart cloud-controller-manager flag'i — route-controller kapalı, `--allocate-node-cidrs` (nodeipam) farklı controller olduğu için harmless kalıyor, Hetzner network'e artık route yazılmıyor). Regresyon guard: `scripts/test_destroy_safety.sh` (CI'da `code-quality.yml` iac-quality job'unda gating).

- **First-master cloud-init 32KB tavanı — base64gzip Hetzner'de İMKÂNSIZ (NEW 2026-06-16, bring-up'ta yakalandı)**: `first_master_cloud_init` 10 manifest'i base64 gömüyor (`main.tf:168`). Hetzner `user_data`'yı **32768 byte** ile sınırlıyor. 2026-06-16 bring-up'ta first_master **34525 byte** olup `master[0]` create'i `Length must be between 0 and 32768` ile fail etti (joining master'lar küçük, geçti). **Kök sebep**: #148 + 028be44 commit'leri cloud-init'i şişirmiş, zaten ~33181 byte ile limiti aşıyordu (C14 yorumu +1344 ile kötüleştirdi). **base64gzip ÇÖZÜM DEĞİL**: Hetzner user_data'da yalnızca UTF-8 string kabul ediyor, binary/gzip desteklemiyor ve [desteklemeyeceklerini açıkladılar](https://bugs.launchpad.net/cloud-init/+bug/1884071); base64(gzip) → cloud-init ham gzip magic byte beklediği için decompress etmez → cluster sessizce çöker. **Doğru yol = embedded manifest'leri yalın tut** (büyük içerik runtime'da curl'lenir, Gateway CRD'leri gibi). Fix: `hetzner-ccm.yaml.tpl` yorumları kırpıldı (4115→1155B), first_master 34525→**30577B** (2191 marj). Guard: `scripts/test_destroy_safety.sh` embedded-manifest raw toplamını 15000B ile cap'ler. Kesin pre-apply kontrol: `echo 'nonsensitive(length(module.rke2_cluster.first_master_cloud_init))' | tofu -chdir=infrastructure/environments/prod console` → <32768 olmalı.

- **Haven privatenetworking: kubelet flag yetmez, CCM'yi düşür (NEW 2026-04-14, Sprint Haven 15/15)**: Haven `privatenetworking` check node'ların `.status.addresses[]` listesinde `ExternalIP` type'ında entry olup olmadığına bakar. Kubelet `--node-external-ip=""` veya RKE2 config'den `node-external-ip` satırını silmek YETMEZ — Hetzner CCM server'ın public IPv4'ünü cloud metadata'dan okuyup ExternalIP'ye koymaya devam eder. **Tek doğru yol**: `hcloud_server.master/worker` üzerinde `public_net { ipv4_enabled = false; ipv6_enabled = false }` → CCM'in raporlayacağı public IP yok → `.status.addresses` yalnızca InternalIP içerir → Haven PASS. Cluster node'ları internet'e NAT box üzerinden çıkar (`infrastructure/modules/hetzner-infra/nat.tf` + `hcloud_network_route.default_via_nat`). Eski yanlış not (`haven/remediation/07-private-networking.md` Option B) overridden.

- **Haven multi-AZ: workers farklı DC'de (NEW 2026-04-14, Sprint Haven 15/15)**: Hetzner CCM node'lara otomatik `topology.kubernetes.io/zone=<fsn1-dc14 / nbg1-dc3 / ...>` label'ı basar (source: Hetzner Cloud DC field). Haven `infraMultiAZ` en az 2 distinct zone değeri bekler. Masters `var.location_primary = "fsn1"`, workers `var.worker_location = "nbg1"` → 2 distinct zone → PASS. etcd quorum masters içinde tek DC'de kaldığı için ~25ms inter-region latency etki etmez; yalnızca kubelet → apiserver ve ingress LB → worker path'leri ~15ms cross-DC (kabul edilebilir).

Eski (Haven dev / Rancher era) gotcha'lar için → `docs/gotchas-haven-dev.md`.

## Maliyet

| Ortam | Aylık |
|---|---|
| iyziops prod cluster (Hetzner, 6 node + 2 LB) | ~€177 |
| CI Runner VPS (Hetzner CX23 x3) | ~€15 |
| Anthropic Max | $200 |
| **Toplam (cluster up)** | **~€192 + $200** |
| **Cluster down** (yalnızca runner'lar) | **~€15 + $200** |

## ZORUNLU KURALLAR (ASLA İHLAL EDİLEMEZ)

### Kural 1: Test Yazılmadan Hiçbir Şey "OK" Değildir
- Her yeni feature/fix için YENİ test yazılmalı
- Test sayısı sprint sonunda ARTMALI — aynı kalırsa test yazılmamış demektir
- Önce test yaz (FAIL etmeli) → sonra kodu yaz → test geçmeli
- Integration kodu entegre edilmeden task TAMAMLANMIŞ SAYILMAZ (client yazmak ≠ feature bitti)

### Kural 2: Sprint Adım Sırası (Kesinlikle Bu Sırada)
1. Backend kodu + backend test + backend test ÇALIŞTIR
2. DB/K8s/Gitea/Harbor entegrasyonu gerçek cluster'da doğrula
3. UI kodu + Playwright testi + test ÇALIŞTIR
4. Tüm test suite çalıştır (eski + yeni)
5. Test count artmadıysa → ADIM 1'E DÖN
6. PR → review → merge

### Kural 3: PR ve Review
- Her değişiklik feature branch'te yapılır
- PR'sız main'e merge YASAK
- PR'da test count öncesi/sonrası belirtilmeli
- **Architect + Tester agent review zorunlu** — blocking bug varsa düzelt → tekrar review
- Her PR için 4-agent paralel review (architect, backend, frontend, team-lead) önerilir
- Her ikisi de APPROVED + CI green olmadan merge yok

### Kural 4: Entegrasyon = Bağlama + Test
- Client/service yazmak YETERLİ DEĞİL
- Client'ı çağıran kodu da yazmak lazım (ör: `managed_service.py` → `everest_client`)
- Entegrasyon testi zorunlu (gerçek Everest'ten DB oluştur, status kontrol et)
- "Client hazır" ≠ "Feature tamamlandı"

### Kural 5: DB Migration Kontrolü (Alembic)
- Her SQLAlchemy model değişikliği = Alembic migration
- `alembic upgrade head` init container'da otomatik çalışır — **`stamp head` YASAK**
- Deploy sonrası migration doğrulanmalı:
  ```bash
  kubectl exec -n haven-system deploy/haven-api -- python -m alembic -c alembic/alembic.ini current
  ```
- Migration uygulanmamışsa: `kubectl rollout restart deploy/haven-api -n haven-system`

### Kural 6: CORS Testi (Her API Deploy Sonrası)
- **Curl CORS hatası göstermez** — browser'dan test zorunlu
- Console'da `Access-Control-Allow-Origin` hatası varsa merge YASAK
- Exception handler'lar CORS headers içermeli (500/422/403 response'ları dahil)

### Kural 7: Definition of Done
CI green YETERLİ DEĞİL. Aşağıdakilerin HEPSİ tamamlanmalı:
1. Kod + yeni test + lint/format ✅
2. PR + architect + tester agent APPROVED
3. Main merge + CI ALL GREEN
4. Cluster'a deploy doğrulandı (ArgoCD sync + pod Running + image SHA match)
5. API/UI erişilebilir (curl + browser)
6. Yeni endpoint'ler OpenAPI spec'te görünüyor
7. Ölçülebilir artış: backend test count + Playwright test count

### Kural 8: CLAUDE.md Bakımı — Yağ Bağlatma
- Bu dosya her session'da context'e yüklenir → ŞİŞİRMEK PAHALI
- **Kalacak**: Tech Stack, Mimari Kararlar, Konvansiyonlar, AKTİF Gotcha'lar, ZORUNLU KURALLAR
- **Kalmayacak**: Sprint tarihçesi, tamamlanan task listeleri, eski cluster snapshot'ları, stale status
  - Sprint tarihçesi → `docs/sprints/PHASE_HISTORY.md`
  - Canlı durum → `memory/RESUME_HERE.md`
  - Arşiv gotcha'lar → `docs/gotchas-haven-dev.md`
  - Compliance tablosu snapshot'ları → `docs/haven-compliance-*.md`
- Her sprint sonunda CLAUDE.md büyüdüyse: yağı temizle, arşive taşı, pointer bırak.

---

## Pointer'lar

- **Canlı durum** (kubeconfig, son session, next steps): `memory/RESUME_HERE.md`
- **Mimari detay genişletme**: `.claude/CLAUDE.md`
- **Sprint tarihçesi**: `docs/sprints/PHASE_HISTORY.md`
- **Sprint backlog**: `docs/sprints/SPRINT_BACKLOG.md`
- **Rename planı** (Haven → iyziops): `docs/sprints/RENAME_IYZIOPS_PLAN.md`
- **Haven compliance gate** (resmi VNG CLI wrapper): `haven/README.md` — `make haven` tek komutla 15/15 check. Pin `haven/VERSION` (şu an v12.8.0). Baseline `haven/reports/baseline-*.{txt,json}`. Known FAIL'ler `haven/remediation/`.
- **Haven dev compliance snapshot** (tarihsel, arşiv): `docs/haven-compliance-haven-dev.md`
- **Haven dev gotcha'ları arşivi**: `docs/gotchas-haven-dev.md`
- **Haven dev cluster snapshot (2026-03-31)**: `docs/archive/haven-dev-snapshot-2026-03-31.md`
- **Project map** (repo yapısı + test locations): `.claude/rules/project-map.md`
- **Workflow rules** (PR lifecycle, sprint execution): `.claude/rules/workflow.md`
- **Conventions rules** (Makefile, Python, TS, Git, CI/CD): `.claude/rules/conventions.md`
- **IaC discipline** (OpenTofu 10 kuralı): `.claude/rules/iac-discipline.md`
- **Logs directory kuralı**: `.claude/rules/logs-directory.md`
