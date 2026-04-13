# Haven Dev Cluster Snapshot — 2026-03-31

> Arşivlenmiş cluster durum snapshot'ı. CLAUDE.md'den taşındı 2026-04-13.
> Bu dosya **eski Haven dev cluster'ının** (Rancher-based, Hetzner 46.225.42.2) tarihi bir anını korur.
> Güncel iyziops prod durumu için → `memory/RESUME_HERE.md`.

## Cluster Erişimi (tarihsel)

- **Kubeconfig**: `infrastructure/environments/dev/kubeconfig`
- **Cluster API**: `https://46.225.42.2:6443` (Hetzner, Rancher-managed RKE2)
- **Kullanım**: `export KUBECONFIG=/path/to/InfraForge-Haven/infrastructure/environments/dev/kubeconfig`

### API lokal başlatma

```bash
cd api
K8S_KUBECONFIG=../infrastructure/environments/dev/kubeconfig \
EVEREST_URL=http://localhost:8888 \
HARBOR_URL=http://harbor.46.225.42.2.sslip.io \
HARBOR_ADMIN_PASSWORD='HavenHarbor2026!' \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Port-forward'lar

- **Everest**: `kubectl port-forward -n everest-system svc/everest 8888:8080`
- **Keycloak**: `kubectl port-forward -n keycloak svc/keycloak-keycloakx-http 8080:80` → `http://localhost:8080` (haven realm, haven-ui client, admin / HavenAdmin2026!)
- **Gitea**: `kubectl port-forward -n gitea-system svc/gitea-http 3030:3000` → `http://localhost:3030` (havenAdmin / HavenAdmin2026)
- **Harbor external**: `http://harbor.46.225.42.2.sslip.io` (admin/HavenHarbor2026!)

## Cluster Bileşenleri

- 6 node RKE2 cluster (3 master, 3 worker) — Hetzner nbg1+hel1
- **ArgoCD**: haven-platform, haven-api, haven-ui → Synced+Healthy
- **Gitea**: gitea-system ns, haven/haven-gitops repo (tenant manifests aktif)
- **Harbor**: harbor-system ns, `haven` project, tenant image'ları `haven/tenant-{slug}/{app}:{tag}` altında
- **Keycloak**: keycloak ns, haven realm, haven-api + haven-ui client'lar
- **BuildKit**: haven-builds ns, `buildkitd` Deployment
- **Redis Operator**: OpsTree, redis-system ns
- **RabbitMQ Operator**: rabbitmq-system ns
- **CNPG**: cnpg-system ns (platform DB: haven_platform)
- **Percona Everest v1.13.0**: everest-system ns, 3 DB engine operational

## Namespace Yapısı (3-Tenant Demo)

```
everest                  → Everest-managed DB pod'ları
                           rotterdam-app-pg-instance1-*   (PostgreSQL 17.7 + PgBouncer)
                           amsterdam-app-mongo-rs0-0      (MongoDB 8.0.17)
                           utrecht-app-mysql-pxc-0        (MySQL 8.4.7 + HAProxy)
tenant-rotterdam         → rotterdam-api + app-redis-0
tenant-amsterdam         → amsterdam-portal + app-redis-0
tenant-utrecht           → utrecht-worker + app-rabbit-server-0
harbor-system            → Image registry (tenant-rotterdam/amsterdam/utrecht projects)
haven-builds             → BuildKit daemon + build job pod'ları
```

## App Deploy Akışı (E2E — 3 Tenant)

```
1. POST /tenants                      → Tenant oluştur (ns, quota, RBAC, CNP, Harbor, AppSet)
2. POST /tenants/{slug}/apps          → App kaydı oluştur + Gitea values.yaml yaz
3. POST /tenants/{slug}/services      → Managed service provision (Everest/CRD)
4. POST /apps/{slug}/build            → Build trigger (background task)
5. BuildKit: git clone → Dockerfile build → Harbor push
6. Pipeline: Gitea values.yaml image tag güncelle → ArgoCD sync → Pod Running
7. GET /tenants/{slug}/events         → SSE ile adım adım progress stream
```

- **Deploy mode**: GitOps (ArgoCD ApplicationSet per tenant, multi-source Helm)
- **Harbor image format**: `harbor.46.225.42.2.sslip.io/library/tenant-{slug}/{app}:{commit[:8]}`

## Managed Services (5 DB tipi E2E doğrulandı)

- PostgreSQL (Everest) — ~50s ready, credentials: user/pass/host/pgbouncer-host/port
- MySQL (Everest) — ~3.5dk ready, 2Gi RAM + 5Gi storage override (OOMKilled fix)
- MongoDB (Everest) — ~1.5dk ready
- Redis (CRD, OpsTree) — ~22s ready, passwordless, fsGroup:1000 + podSecurityContext gerekli
- RabbitMQ (CRD) — ~1.5dk ready

**Tenant prefix izolasyonu**: Everest DB adı `{tenant_slug}-{service_name}` (ör: `testing-app-pg`).

## Full E2E Doğrulama (3 Tenant, 2026-03-31)

```
✅ Tenant create → namespace + quota + RBAC + CNP + Harbor + AppSet (3 tenant)
✅ App create → Gitea values.yaml + ArgoCD Application (3 app)
✅ Service provision → Everest PG/MySQL/MongoDB + CRD Redis/RabbitMQ (6 service, all READY)
✅ Build trigger → BuildKit → Harbor push (3 build, all Completed)
✅ Gitea values.yaml image update → ArgoCD sync → Pod Running (3 app Running)
✅ Credential provisioning → svc-* secret in tenant namespace
✅ ArgoCD: 3 AppSets + 3 tenant apps + 3 platform apps = all Healthy
✅ Delete tenant → cascade apps + services + namespace + AppSet + Harbor (verified)
```

## Test Durumu (snapshot)

- Backend unit testleri: **1185**
- Playwright E2E: **152 test**
- Real cluster E2E: 3 tenants × (app + 2 services + build + deploy + delete) — all verified
- CI/CD: GitHub Actions → Lint ✅ → Test ✅ → Docker Build ✅ → Harbor Push ✅ → Manifest Update ✅ → ArgoCD Sync ✅

## CI/CD Pipeline

- **GitHub Actions**: `api-ci.yml` (lint → test → build → push → manifest update)
- **Image**: `harbor.46.225.42.2.sslip.io/library/haven-api:{git-sha}`
- **ArgoCD**: `haven-api` Application auto-syncs from `platform/manifests/haven-api/`
- **Swagger docs**: `https://api.46.225.42.2.sslip.io/api/docs`

## Enterprise Hardening (Sprint H1-H3)

- **RBAC**: `require_role("owner", "admin")` decorator, POST /members enforced
- **Container security**: Non-root (USER 1000), drop ALL capabilities, startup probe
- **Request logging**: X-Request-ID correlation header, latency logging
- **Config validation**: Missing SECRET_KEY/DATABASE_URL warning at startup
- **Backup**: MinIO S3 HTTPS, Everest DatabaseClusterBackup, MongoDB/MySQL/PG verified
