# Phase History — Haven / iyziops Platform

> Arşivlenmiş sprint tarihçesi. CLAUDE.md'den taşındı 2026-04-13.
> **Canlı durum için** → `memory/RESUME_HERE.md`.
> Bu dosya tarihsel referans — sprintleri tekrar okumak, PR'ları hatırlamak, test count'larını izlemek içindir.

---

## Phase -1: Dev Environment Setup ✅
- [x] Monorepo klasör yapısı
- [x] CLAUDE.md
- [x] .gitignore
- [x] api/pyproject.toml
- [x] infrastructure/ OpenTofu config
- [x] git init + ilk commit

## Phase 0: Haven K8s Cluster ✅ (Haven dev, Rancher-based — superseded by Option B)
- [x] Hetzner base infra (hetzner-infra module)
- [x] Rancher management node (K3s + Helm, production-grade)
- [x] rancher2 provider (two-provider pattern: bootstrap + admin)
- [x] RKE2 cluster (rancher2_cluster_v2)
- [x] Cilium CNI (cni=cilium + chart_values, built-in Helm controller)
- [x] Longhorn storage (rancher2_app_v2, enable/disable)
- [x] Master/Worker nodes (cloud-init registration)
- [x] cloud-init bashism fix (dash uyumu)
- [x] Helm templates module'e taşındı (rancher-cluster module)
- [x] Cluster readiness: `rancher2_cluster_sync` (native, replaces bash curl loops)
- [x] App timeouts: all `rancher2_app_v2` have explicit timeouts (Longhorn 20m)
- [x] Destroy ordering: serialized (Longhorn last, 20m timeout)
- [x] Firewall: NodePort removed (Gateway API), hardening deferred (Hetzner public IP issue)

## Phase 0.5: Platform Servisleri ✅
- [x] Cert-Manager v1.16.2 (Jetstack repo via rancher2_catalog_v2, Haven #12)
- [x] rancher-monitoring 104.1.2 (Prometheus + Grafana, CRD + chart, Haven #14)
- [x] rancher-logging 104.1.2 (Banzai + Fluentbit/Fluentd, CRD + chart, Haven #13)
- [x] Harbor (image registry, rancher2_app_v2, harbor-system)
- [x] MinIO (S3 storage, rancher2_app_v2, minio-system, worker nodeSelector fix)

**11.5/15 Haven Compliant** (Phase 0.5 sonu — 1, 4, 15 partial/broken).

## Phase 0.6: Cilium Gateway API + External Access ✅
- [x] Gateway API experimental CRDs (v1.2.1, tlsroutes dahil)
- [x] Cilium `gatewayAPI.enabled: true` (cilium-values.yaml.tpl)
- [x] GatewayClass `cilium` (Cilium operator oluşturdu)
- [x] Gateway `haven-gateway` (haven-gateway namespace, PROGRAMMED: True)
- [x] HTTPRoute: Harbor, MinIO Console, MinIO S3 (sslip.io hostnames)
- [x] Hetzner LB `use_private_ip: true` (firewall bypass, private network)
- [x] Hetzner LB targets: master + worker (6 node)
- [x] gateway-proxy DaemonSet (nginx, hostNetwork, port 80 → Cilium gateway ClusterIP)
- [x] Hetzner LB destination_port: 80 (firewall açık)
- [x] Dış erişim: Harbor HTTP 200, MinIO Console HTTP 200, MinIO S3 HTTP 403 ✅

## Phase 1 Sprint 1: Platform Servisleri (CNPG, ArgoCD, Keycloak) ✅
- [x] CloudNativePG operator 0.22.1 (cnpg-system, rancher2_app_v2)
- [x] CNPG Cluster `haven-platform` (haven_platform DB, cnpg-system, 1 instance, Longhorn 20Gi)
- [x] ArgoCD 7.7.3 (argocd namespace, insecure mode, HA disabled, HTTP 200)
- [x] Keycloak 26.1 (quay.io/keycloak/keycloak:26.1, start-dev, keycloak namespace, HTTP 302 → login)
- [x] External-DNS (optional, disabled, cloudflare provider ready)
- [x] Platform namespaces: haven-system, haven-builds
- [x] Gateway HTTPRoutes: argocd, keycloak, haven-api (placeholder)
- [x] Certificate SANs updated: argocd, keycloak, api sslip.io hostnames
- [x] Keycloak: ssh_resource ile kubectl apply (quay.io image, Bitnami chart abandon edildi)
- [x] Service selector fix: `kubectl delete svc` before apply (old Bitnami selector override)

## Phase 1 Sprint 2: Build/Deploy Pipeline + UI ✅
- [x] GitHub OAuth per-tenant (token stored server-side in DB)
- [x] Organization repo listing (read:org scope, NimbusProTch)
- [x] OAuth scope encoding fix (colon preservation in `read:user`)
- [x] Suspense boundary fix for OAuth callback page (Next.js 14)
- [x] **BuildKit** build engine (replaced Kaniko, 5x faster builds)
- [x] Nixpacks smart detection (Python/Node/Go/Ruby/Rust auto-detect start command)
- [x] Fallback Dockerfile generation when nixpacks fails
- [x] ARM64 (Apple Silicon) support for nixpacks binary
- [x] Private repo clone via embedded OAuth token in git URL
- [x] Init container log capture on build failures (git-clone, nixpacks, buildctl)
- [x] App CRUD: create, read, update (PATCH), delete with K8s cleanup
- [x] Tenant CRUD: create, delete with K8s namespace lifecycle
- [x] Configurable app port (not hardcoded 8000)
- [x] Pod readiness check before marking deployment as "running"
- [x] CrashLoopBackOff/ImagePullBackOff early detection → FAILED status
- [x] Graceful HTTPRoute skip when Gateway API CRD not installed
- [x] DB enum fix (DeploymentStatus values_callable)
- [x] CI/CD pipeline step visualization in UI (Clone→Detect→Build→Push→Deploy)
- [x] Auto-streaming build logs during active builds
- [x] Deployment status polling (5s interval while building)
- [x] App Settings tab with GitHub repo/branch dropdowns
- [x] "Use existing Dockerfile" toggle option
- [x] Tenant delete with slug confirmation dialog

## Phase 1 Sprint 3: Managed Services + Multi-Tenant E2E ✅
- [x] Everest entegrasyonu (PostgreSQL v17.7, MySQL v8.4.7, MongoDB v8.0.17)
- [x] Redis OpsTree Operator (standalone, dev ephemeral / prod persistent)
- [x] RabbitMQ Cluster Operator (dev 1 replica / prod 3 replicas)
- [x] MySQL/MongoDB credential provisioning (Everest admin secret → tenant namespace)
- [x] SSE lifecycle events (tenant provision/deprovision, service provision/deprovision)
- [x] Helm chart guard: skip Deployment/Service/HPA/HTTPRoute when image.repository empty
- [x] Multi-tenant E2E: 3 tenants (Rotterdam PG+Redis, Amsterdam MongoDB+Redis, Utrecht MySQL+RabbitMQ)
- [x] ArgoCD per-tenant ApplicationSet (appset-{slug}, multi-source: chart + gitops values)
- [x] Gitea haven-gitops repo with tenant/app values.yaml manifests
- [x] Harbor per-tenant projects + robot accounts
- [x] Build + Deploy pipeline E2E: build trigger → BuildKit → Harbor → Gitea values update → ArgoCD sync → Pod Running
- [x] **752 backend tests** (all passing)

## Phase 1 Sprint 3.5: Post-E2E Hardening & Security ✅
- [x] Hardcoded credential temizliği (.env.example, config default'lar boş) — PR #6
- [x] DB unique constraints + race condition fix (IntegrityError → 409) — PR #7
- [x] Background loop per-service isolation — PR #8
- [x] Error handling cleanup (bare except fix, EmailStr validation) — PR #9
- [x] PG custom user via primary endpoint (PgBouncer bypass) — PR #10
- [x] URL-encode database passwords in DATABASE_URL — PR #5
- [x] CiliumNetworkPolicy everest egress + ResourceQuota artırma — PR #4
- [x] Everest namespace revert (everest ns, tenant ns'de secret) — PR #4
- [x] MySQL/MongoDB custom user provisioning (aiomysql, motor) — PR #4
- [x] Background credential provisioning loop (UI bağımlılığı kaldırıldı) — PR #4
- [x] **778 backend tests** (all passing)

## Phase 1 Sprint 4.5: UX Overhaul + Pipeline Fix + Auth Hardening ✅
- [x] Fix: Create App slug validation (silent HTML5 pattern → JS validation with errors)
- [x] Fix: Pod readiness — detect terminated containers + init container failures
- [x] Fix: Queue page "unavailable" → show actual error + retry button
- [x] Fix: ObservabilityTab "Loading pods" → "No deployment yet" or retry
- [x] Add gitops_commit_sha field to Deployment model
- [x] Keycloak token: 5min → 1hr access, 8hr SSO session (haven-realm.json + setup script)
- [x] Frontend 401 interceptor with Promise-based mutex (race-condition safe)
- [x] Session expiry toast notification before redirect
- [x] Token refresh safety margin: 60s → 5min
- [x] New App wizard: 4-step form (Identity → Source → Build → Runtime → Review)
- [x] GitHubFileBrowser component (repo file tree dropdown for Dockerfile selection)
- [x] GitHubRepoPicker component (searchable, org-grouped repo picker)
- [x] Build vs Deploy separation: BUILT status, deploy-image endpoint
- [x] Pipeline: deploy=False stops after build (BUILT status)
- [x] SSE heartbeat fix (data: format for UI parser)
- [x] Auto-start log streaming on build/deploy
- [x] BUILT status UI support (badge, pipeline viz, deploy button)
- [x] AddServiceModal enterprise redesign with official DB logos + backup config
- [x] BackupPanel component (list backups, trigger snapshot, restore)
- [x] Backup API client methods (list, trigger, restore, schedule)
- [x] Build queue service (Redis FIFO, per-tenant concurrency limits)
- [x] Build queue endpoints (status, jobs, position) with graceful Redis fallback
- [x] Dashboard stats: gradient cards, app health dots
- [x] App cards: port, domain, mini deployment status, quick actions
- [x] Config validation: warn about missing recommended settings at startup
- [x] buildOnly() and deployImage() API client methods
- [x] **1081 backend tests** (was 929, +152 new)

## Phase 1 Sprint 5: Broken Fields + Service Dependencies ✅
- [x] Backend: 9 broken field fix (deploy_service, auto_deploy, use_dockerfile, dockerfile_path, build_context, custom_domain, health_check_path, canary_enabled, canary_weight) — PR #47
- [x] Backend: requested_services + auto-connect on app create — PR #47
- [x] Backend: ArgoCD sync options (diff, prune, force, dry_run) — PR #47
- [x] Backend: connected_apps enrichment on service responses — PR #47
- [x] Backend: app services endpoint (GET /apps/{slug}/services) — PR #47
- [x] **1185 backend tests** (was 1081, +104 new)

## Phase 1 Sprint 5.5: Frontend — Modals, Services UX, E2E ✅
- [x] Frontend: API client types + methods (AppServiceEntry, SyncDiffEntry, SyncOptions) — PR #48
- [x] Frontend: Wizard Step 5 "Services" (5 DB types, select/deselect, review) — PR #48
- [x] Frontend: ConnectedServicesPanel (status badges, credentials viewer, disconnect) — PR #48
- [x] Frontend: ScaleModal (replica presets, resource tiers, HPA, impact preview) — PR #48
- [x] Frontend: SyncModal (ArgoCD status, diff, options, history, dry run) — PR #48
- [x] Frontend: RestartModal (pod count, rolling restart warning, downtime info) — PR #48
- [x] Entegrasyon: Modal'ları app detail'e bağla — PR #49
- [x] Entegrasyon: ConnectedServicesPanel app detail'e ekle — PR #49
- [x] Entegrasyon: Provisioning banner — PR #49
- [x] Entegrasyon: Tenant services connected_apps — PR #49
- [x] 33 Playwright E2E tests + auth bypass fix — PR #50
- [x] **152 Playwright tests** (was 36, +116 new)

## Sprint H0–H4: Haven Compliance Security Hardening ✅ (partial)
Güvenlik katmanları Haven dev cluster'a indi (Sprint H0 → H4 + continuation):
- JWT issuer doğrulaması (`verify_iss=True`) + JWKS TTL 1h cache (#86) + http/https scheme tolerance (#109/#110)
- Token revocation (per-user reauth watermark, alembic 0023) (#95)
- JWT `tenant_memberships` claim helpers (#96)
- `platform-admin` realm role + `require_platform_admin` dep (#92)
- 14 router'da `_get_tenant_or_404` → tek canonical `TenantMembership` dep (#90, #97, #100, #101, #102, #103)
- haven-api ClusterRole scope-down + privilege escalation gap kapatıldı (#89, #106)
- haven-api/ui image immutable digest pinning (#99, #105)
- haven-realm.json hardcoded credential temizliği (#91)
- kubectl OIDC integration (RKE2 + Keycloak haven-kubectl client + tenant_service group provisioning) (#108)
- BuildJob model + dead table silindi (#80)
- Static analysis baseline (bandit + vulture + xenon + mypy) + GitHub Security tab SARIF upload (#83, #84)
- Pre-commit hook (gitleaks + ruff format) (#85)
- **Sprint H1d** (PSA / WireGuard / audit log): PSA `restricted` profile tenant ns'lerinde aktif (#111); Cilium WireGuard kod-default `true` (#112); kube-apiserver audit policy file + flags kod-hazır (#113)
- **Sprint H1e** (encryption / vault hibrit kapatma): Tenant deprovision orphan Everest sweep (#114); Harbor TLS externalURL https + BuildKit secure docker config (#115); MinIO server-side encryption KMS kod-hazır (#116); Vault → ESO migration plan + ExternalSecret CRD for haven-api-secrets (#117 → relocated by #118)

Final Haven dev score: **13/15** (2026-04-09). Kalan: Multi-AZ (kod hazır, apply bekliyor) + kubectl OIDC (kısmen broken). Tablo snapshot: `docs/haven-compliance-haven-dev.md`.

## iyziops Option B Refactor ✅ (2026-04-13)
Haven dev → iyziops prod Option B mimarisine geçiş:
- [x] 2-LB split (API LB + ingress LB) + Hetzner CCM raw manifest (bf97401)
- [x] Bootstrap deadlock fix'leri (9dba7d4)
- [x] Gateway API CRDs runtime fetch (6fc44c1)
- [x] gateway-api-crds as sibling Application under appsets/ (sync-wave -10)
- [x] cert-manager + Cloudflare DNS-01 integration (wildcard cert)
- [x] ArgoCD app-of-apps + platform-ingress + platform-operators
- [x] Kyverno, Longhorn, cert-manager-config all Synced+Healthy
- [x] Fresh destroy+apply proven hands-off (~15 min)
- [x] Merge to main (ed2447b)
- [x] Full destroy+verification (2026-04-13 akşam): 30 resource destroyed, zero orphans, 1 Cloudflare TXT cleanup

**Haven → iyziops rename sprint**: deferred — plan hazır, bkz. `docs/sprints/RENAME_IYZIOPS_PLAN.md`.

## Sonraki (planlanmış)
- [ ] Cloudflare token `User:Read` scope → true hands-off apply
- [ ] Haven → iyziops rename sprint
- [ ] Harbor iyziops-native deploy + haven-api/ui image rebuild
- [ ] Keycloak realm bootstrap + kubectl OIDC
- [ ] Observability stack (Grafana + Loki + Mimir + Hubble UI)
- [ ] Tailscale + operator_cidrs daraltma
- [ ] Everest + CNPG + Redis + RabbitMQ operators iyziops'ta
- [ ] BuildKit + External Secrets + Vault iyziops'ta
- [ ] Phase 1 Sprint 4: Monorepo + smart detection (dependency analizi ile DB auto-provision)
- [ ] Phase 1 Sprint 5: Observability per-app (Loki + Mimir + Tempo dashboards)
- [ ] Phase 1 Sprint 6: Production hardening (custom domain, webhook auto-deploy, one-click rollback)
