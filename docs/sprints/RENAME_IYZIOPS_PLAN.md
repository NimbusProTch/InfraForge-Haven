# Rename: Haven Platform → iyziops

## Context

Proje ürün adı **Haven Platform**tan **iyziops**a taşınacak. Sebep: "haven" ve "infraforge" domain'lerinin yoğun squatlanması, ve iyzi ürün ailesine (iyzitrace, iyziops) tutarlı bir marka stratejisi oluşturma ihtiyacı. `iyziops.com` ve `iyziops.nl` whois ile canlı doğrulandı — ikisi de şu anda boş (2026-04-12). iyzitrace + iyziops = DevOps + Observability açık ürün ailesi.

## Kritik disambiguasyon kuralı (en önemli)

"Haven" kelimesi repo'da **iki farklı anlam**da geçiyor:

1. **Ürün/proje adı** → `iyziops` olarak değişecek. Örnek: `haven-api`, `haven-system`, `haven-platform`, `charts/haven-pg`, `haven-realm.json`.
2. **VNG Haven Compliance Standard** → 342 Hollanda belediyesi için resmi standart. **DEĞİŞMEYECEK.** Örnek: "VNG Haven standaard", "Haven 15/15", "Haven compliant", `docs/haven-compliance/`, `HAVEN_COMPLIANCE_PLAN.md`.

Global find-replace **yasak**. Bunun yerine whitelist pattern'ler ile iki pass:

- **Pass 1 (korumaya al)**: Şu pattern'leri geçici placeholder ile escape et:
  - `VNG Haven`
  - `Haven standaard` (tr: standart)
  - `Haven-compliant` / `Haven Compliant` / `Haven compliancy` / `Haven compliance`
  - `Haven 15/15` / `15/15 Haven`
  - `haven-compliance/` (docs dizini yolu)
  - `HAVEN_COMPLIANCE_PLAN`
- **Pass 2 (ürün adı değişimi)**: Kalan tüm `haven` / `Haven` / `HAVEN` → `iyziops` / `IyziOps` / `IYZIOPS` (case-preserving).
- **Pass 3 (placeholder geri yükle)**: Pass 1'deki placeholder'ları orijinal haline çevir.

Sed/awk tek başına yetmez — Python script ile yapılmalı, whitelist pattern listesi tek yerde tutulmalı, git diff review adımı zorunlu.

## Önkoşullar (kod öncesi)

1. **Domain satın al**: `iyziops.com` + `iyziops.nl` (manual, operatör aksiyonu). Cloudflare'e transfer et.
2. **Branch**: `rename/iyziops-big-bang` (main'den)
3. **Backup**: `backup/pre-iyziops-rename-YYYYMMDD` etiketli main snapshot (iş garantisi)
4. **Test env doğrulama**: 3 test tenant (rotterdam, amsterdam, utrecht) silinebilir durumda mı? User confirmation al.

## Implementation — faz sırası

### Faz 1: Disambiguasyon script'i + dry-run
- `scripts/rename-haven-to-iyziops.py` yaz
- Whitelist pattern'leri YAML dosyasından oku (`.rename-whitelist.yaml`)
- `--dry-run` modunda çalıştır, tüm etkilenecek dosyaları ve diff'leri print et
- Operatörle diff'i gözden geçir
- Özellikle `CLAUDE.md` ve `docs/haven-compliance/` içeriğini el ile doğrula — "15/15 Haven" satırları dokunulmamış olmalı

### Faz 2: Kod rename (tek commit)
- Script'i `--apply` ile çalıştır
- Helm chart dizinlerini el ile taşı (script sadece içerik değiştirir):
  - `charts/haven-app` → `charts/iyziops-app`
  - `charts/haven-pg` → `charts/iyziops-pg`
  - `charts/haven-redis` → `charts/iyziops-redis`
  - `charts/haven-mongodb` → `charts/iyziops-mongodb`
  - `charts/haven-mysql` → `charts/iyziops-mysql`
  - `charts/haven-rabbitmq` → `charts/iyziops-rabbitmq`
  - `charts/haven-managed-service` → `charts/iyziops-managed-service`
- Keycloak realm dosyası: `keycloak/haven-realm.json` → `keycloak/iyziops-realm.json`
- Manifest dizinleri: `platform/manifests/haven-api/` → `platform/manifests/iyziops-api/`, aynısı `haven-ui`
- **Commit**: `refactor: rename product Haven → iyziops (VNG standard refs preserved)`

### Faz 3: Makefile + CI
- `make haven-check` → `make vng-haven-check` olarak yeniden adlandır (VNG standardını test ettiğini açıkça belirt), `docs/haven-compliance/` dizini olduğu gibi kalır
- Kalan target'lar: `haven-logs` → `iyziops-logs`, `haven-pod-wait` → `iyziops-pod-wait` vb.
- `.github/workflows/api-ci.yml` ve `ui-ci.yml`: image isimleri `harbor.*/library/haven-api` → `harbor.*/library/iyziops-api`
- **Commit**: `ci: update Makefile + workflows for iyziops rename`

### Faz 4: Infrastructure (OpenTofu)
- `infrastructure/environments/dev/main.tf`: `rancher2_cluster_v2.haven-dev` → `iyziops-dev` (resource + name)
- `infrastructure/modules/rancher-cluster/` template'leri güncelle (cluster name reference)
- `terraform.tfvars`: `cluster_name = "haven-dev"` → `"iyziops-dev"`
- Rancher cluster'ı **yeniden oluşturma** vs **in-place rename**: Rancher cluster yeniden adlandırma destekli değil — yeni cluster oluştur + eski destroy tercih et (dev ortamında kabul edilebilir, 60 dk iş)
- Alternatif (daha az riskli): K8s namespace + service rename'i dışında cluster adı eski kalsın — sadece workload isimlerini değiştir. **Bu plan bu yolu öneriyor**: cluster adı `haven-dev` kalabilir (internal ad, kullanıcı görmez), sadece namespace + workload + domain değişir.
- **Commit**: `infra: rename workload namespaces + services for iyziops`

### Faz 5: K8s namespace + workload cutover
Namespace yeniden adlandırma imkânsız (K8s yenilerini oluşturup eskileri silmek lazım). Sıra:

1. Yeni namespace'leri oluştur: `iyziops-system`, `iyziops-gateway`, `iyziops-builds`
2. Yeni haven-api/ui deployment'larını iyziops-system'a deploy et (ArgoCD manifest path değişti)
3. Gateway HTTPRoute'ları yeni namespace'e taşı
4. DNS + Cert-manager Certificate'ları yeni domain'lere yönlendir
5. Smoke test (Faz 7'ye bkz.)
6. Eski `haven-*` namespace'lerini sil
7. 3 test tenant'ı yeniden provision et (`tenant-rotterdam` vs tenant namespace isimleri değişmez, sadece platform katmanı değişiyor)

### Faz 6: Domain + TLS

**Hostname yapısı (yeni)**:
| Servis | Eski hostname | Yeni hostname |
|---|---|---|
| UI (kök) | `app.46.225.42.2.sslip.io` | **`iyziops.com`** (apex, `app.` yok) |
| API | `api.46.225.42.2.sslip.io` | `api.iyziops.com` |
| Keycloak | `keycloak.46.225.42.2.sslip.io` | `keycloak.iyziops.com` |
| Harbor | `harbor.46.225.42.2.sslip.io` | `harbor.iyziops.com` |
| ArgoCD | `argocd.46.225.42.2.sslip.io` | `argocd.iyziops.com` |

Kritik: UI **apex** domain'de (`iyziops.com`), subdomain'de değil. `www.iyziops.com` → 301 redirect to apex.

**Aksiyonlar**:
- Cloudflare: `iyziops.com` A kaydı → 46.225.42.2, `*.iyziops.com` wildcard CNAME → `iyziops.com`, aynısı `iyziops.nl` için
- Cert-manager: `Certificate` SAN listesi → `iyziops.com`, `www.iyziops.com`, `api.iyziops.com`, `keycloak.iyziops.com`, `harbor.iyziops.com`, `argocd.iyziops.com`, `iyziops.nl`, `*.iyziops.nl` (.nl için wildcard yeterli)
- Gateway `haven-gateway` → `iyziops-gateway`: listener hostname'leri yukarıdaki listeye göre güncelle
- HTTPRoute `iyziops-ui` → parentRef `iyziops-gateway`, hostname `iyziops.com` + `www.iyziops.com` (www redirect için ayrı HTTPRoute veya ingress middleware)
- Dev fallback: `*.46.225.42.2.sslip.io` ikinci listener olarak kalsın (cutover rollback için)
- Let's Encrypt: staging issuer ile test → prod issuer'a geç. Rate limit 50 cert/hafta, tek Certificate resource'u 100 SAN'a kadar alır

**UI tarafında etkilenen yerler**:
- `ui/lib/api-client.ts` — `NEXT_PUBLIC_API_URL` → `https://api.iyziops.com`
- `ui/lib/auth.ts` — Keycloak issuer → `https://keycloak.iyziops.com/realms/iyziops`
- `ui/tests/*.spec.ts` — 15+ test dosyasında hardcoded sslip.io URL'leri → `iyziops.com` + `api.iyziops.com`
- `api/app/config.py` — `CORS_ORIGINS` → `["https://iyziops.com", "https://www.iyziops.com"]`
- `keycloak/iyziops-realm.json` — `redirectUris` → `["https://iyziops.com/*"]`, `webOrigins` → `["https://iyziops.com"]`

### Faz 7: Doğrulama (merge öncesi, zorunlu)
1. **Backend**: `make api-test` — full suite geçmeli (1185 testten hiçbiri kırılmamalı)
2. **Frontend**: `make ui-build` + `make ui-lint`
3. **Playwright E2E**: 152 test — özellikle auth flow (Keycloak realm `haven` → `iyziops` değişti)
4. **Cluster smoke**:
   - `kubectl get pods -n iyziops-system` — haven-api, haven-ui → iyziops-api, iyziops-ui Running
   - `curl https://api.iyziops.com/api/docs` → 200
   - `curl https://iyziops.com/` → 200 (UI apex domain)
   - `curl https://www.iyziops.com/` → 301 → `https://iyziops.com/`
   - `curl -H "Origin: https://iyziops.com" -I https://api.iyziops.com/api/docs | grep -i access-control` → CORS headers mevcut
5. **VNG Haven compliance**: `make vng-haven-check` — **15/15 hâlâ geçmeli**. Bu test değişmemeli, sadece target adı değişti.
6. **3-tenant E2E**: Rotterdam/Amsterdam/Utrecht'i yeniden provision et, app deploy et, service bağla. Full akış.
7. **Image tag doğrulama**: `kubectl get pod -n iyziops-system -l app=iyziops-api -o jsonpath='{.items[0].spec.containers[0].image}'` → `harbor.*/library/iyziops-api@sha256:...` (yeni image adı, digest format korunuyor)

### Faz 8: Docs + memory
- `CLAUDE.md` (root): başlık "Haven Platform - Proje Hafızası" → "iyziops Platform - Proje Hafızası". VNG Haven compliance bölümü aynen kalır.
- `.claude/CLAUDE.md`: aynısı
- `README.md` (varsa): güncel
- `/Users/gaskin/.claude/projects/-Users-gaskin-Desktop-gokhan-askin-GitHub-InfraForge-Haven/memory/MEMORY.md` + ilgili memory dosyaları: proje hafıza index'i güncellenmeli. 27 dosya haven referansı içeriyor; sadece aktif olanlar (proje status, sprint status) güncellensin. Tarihsel session dosyalarına dokunma.
- **Not**: Yerel repo yolu hâlâ `InfraForge-Haven` — fiziksel dizini değiştirmek zorunda değilsin (git remote bağımsız), ama uzun vadede `iyziops-platform` olarak taşı.

## Kritik dosyalar (değiştirilecek)

- `CLAUDE.md` + `.claude/CLAUDE.md` — proje adı, başlık, tech stack tablosu
- `api/app/config.py` — `APP_NAME`, `PROJECT_NAME` varsayılanları
- `api/app/main.py` — FastAPI title
- `ui/app/layout.tsx` — HTML title
- `ui/components/` — logo + footer metni
- `keycloak/haven-realm.json` → `keycloak/iyziops-realm.json` + `"realm": "iyziops"`
- `platform/manifests/haven-api/` → `platform/manifests/iyziops-api/`
- `platform/manifests/haven-ui/` → `platform/manifests/iyziops-ui/`
- `platform/argocd/apps/haven-api.yaml` → `iyziops-api.yaml`
- `platform/argocd/apps/haven-ui.yaml` → `iyziops-ui.yaml`
- `platform/kyverno-policies/*.yaml` — registry restrict pattern'leri (image adı iyziops-api)
- `charts/haven-*` (7 chart) → `charts/iyziops-*`
- `infrastructure/environments/dev/main.tf` — namespace + workload referansları
- `infrastructure/environments/dev/terraform.tfvars` — `project_name` değişkeni
- `.github/workflows/api-ci.yml` + `ui-ci.yml` — image push target
- `Makefile` — target rename
- `runner/main.tf` — CI runner cluster label (varsa)
- `docs/haven-compliance/` → **DOKUNMA** (VNG standard docs)
- `HAVEN_COMPLIANCE_PLAN.md` → **DOKUNMA**

## Risk ve mitigasyon

| Risk | Etki | Mitigasyon |
|---|---|---|
| VNG Haven referansları yanlışlıkla silinir | 🔴 Yüksek — compliance claim bozulur | Whitelist pattern'ler + `--dry-run` + manuel diff review + Faz 7 adım 5'te `make vng-haven-check` |
| Keycloak realm cutover'da user session kaybı | 🟡 Orta | Dev ortamında kabul edilebilir, kullanıcılar yeniden login olur |
| ArgoCD AppSet'ler yeni manifest path'lerini bulamaz | 🟡 Orta | Eski appset'leri sil + yenilerini `iyziops-system`'a deploy et, sync hard refresh |
| Test tenant credential'ları kaybolur (3 tenant) | 🟢 Düşük | Dev verisi, yeniden provision edilebilir |
| Let's Encrypt rate limit (yeni domainler) | 🟡 Orta | Staging issuer ile önce test et, prod issuer'ı sadece cutover'da kullan |
| CI/CD pipeline dockerfile build break | 🟡 Orta | Feature branch'te CI green doğrulanmadan main'e merge yok |
| Memory dosyaları eski proje adı ile karışır | 🟢 Düşük | İlgili aktif memory dosyalarını güncelle, tarihsel olanlarda bırak |

## Tahmin

- **Toplam efor**: 1 tam iş günü (~6-8 saat) aktif çalışma + ~2 saat re-provision
- **File edit count**: ~400-500 dosya (Python script otomatik)
- **Commit count**: 6 commit (1 script, 1 content rename, 1 infra, 1 CI/Makefile, 1 K8s cutover, 1 docs)
- **Downtime**: ~30 dk cutover sırasında dev cluster erişilemez olabilir

## Verification çıkış kriterleri (DoD)

- [ ] Tüm backend testleri geçiyor (1185/1185)
- [ ] Tüm Playwright E2E geçiyor (152/152)
- [ ] `make vng-haven-check` → 13/15 (halihazırdaki skor korunmalı)
- [ ] `https://api.iyziops.com/api/docs` → 200
- [ ] `https://iyziops.com/` → 200 (UI apex)
- [ ] `https://www.iyziops.com/` → 301 → apex
- [ ] Keycloak realm `iyziops` üzerinden login çalışıyor
- [ ] 3 test tenant yeniden provision edildi + app deploy + service bağlama E2E
- [ ] `grep -ri "haven-api\|haven-ui\|haven-system\|haven-gateway\|haven-builds" --exclude-dir=docs/haven-compliance` → 0 hit (VNG docs hariç)
- [ ] `grep -ri "VNG Haven\|Haven 15/15\|Haven compliant"` → önceki count ile aynı (korundu)
- [ ] CI pipeline (self-hosted runner) green
- [ ] Docs güncellendi (CLAUDE.md, .claude/CLAUDE.md, README)
- [ ] Architect + Tester agent review APPROVED
- [ ] PR merged + cluster deploy doğrulandı
