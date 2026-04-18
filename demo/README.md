# iyziops Permanent Demo

**Live**: https://demo.iyziops.com → talks to https://demo-api.iyziops.com

This is the **permanent** demo app used to pitch iyziops to prospects. It is
deployed **entirely through the iyziops UI** — zero YAML, zero kubectl.

## The Story (3-minute pitch)

> *"Let me show you the platform. I'm not going to open a terminal. Watch."*
>
> 1. Open `iyziops.com`, log in.
> 2. **Services tab** → create Postgres, Redis, RabbitMQ. (3 clicks each.)
> 3. **Apps tab → New App** wizard:
>    - Pick GitHub repo.
>    - Choose build context + Dockerfile.
>    - Attach the 3 services with checkboxes.
>    - Hit "Create & Build".
> 4. Watch the live build log stream. Clone → Detect → Build → Push to Harbor → Deploy.
> 5. App URL appears. Open it. Creates a note. RabbitMQ consumes. Redis caches.
> 6. Repeat for the UI app.
>
> *"Start to finish, 15 minutes. Both apps in production, TLS, HPA, isolated tenant namespace. This is the same flow your developers will use."*

## Architecture

```
┌──────────────────────┐      ┌──────────────────────┐
│ demo.iyziops.com     │──►──►│ demo-api.iyziops.com │
│ Next.js 14 (no auth) │ CORS │ FastAPI              │
│ public notes UI      │      │                      │
└──────────────────────┘      └───────┬──────────────┘
                                      │
                        ┌─────────────┼────────────┐
                        │             │            │
                ┌───────▼──────┐ ┌────▼────┐ ┌────▼──────┐
                │ demo-pg      │ │demo-cache│ │demo-queue│
                │ Everest/CNPG │ │ Redis    │ │ RabbitMQ │
                │ Postgres 17  │ │ OpsTree  │ │ operator │
                └──────────────┘ └──────────┘ └──────────┘

        All 3 services provisioned through iyziops Services tab.
        demo-api + demo-ui built from this repo's demo/ dir via BuildKit.
        Images pushed to harbor.iyziops.com/library/ per deploy.
        Both apps deployed through iyziops 5-step wizard.
```

## Deploy reproducing steps (operator runbook)

### Prerequisites
- iyziops platform running (https://iyziops.com accessible)
- Keycloak test user: `testuser` / `test123456`
- This repo's `main` branch up to date

### 1. Create the tenant
- Browser: https://iyziops.com → Sign in
- **Organizations** → New Organization → name `Demo Tenant`, slug `demo`
- Navigate into the tenant.

### 2. Create 3 managed services
- **Services** tab → + New Service
  - name `demo-pg`, type `postgres`, tier `dev` → Create
  - name `demo-cache`, type `redis`, tier `dev` → Create
  - name `demo-queue`, type `rabbitmq`, tier `dev` → Create
- Wait for all 3 to reach **ready** (takes 2-4 min).

### 3. Deploy demo-api (5-step wizard)
- **Apps** tab → + New App
- Step 1 **Identity**: name `Demo API` (slug auto → `demo-api`)
- Step 2 **Source**: Connect GitHub → select `NimbusProTch/InfraForge-Haven`, branch `main`.
  (Or enter the repo URL manually if the picker is unavailable.)
- Step 3 **Build**: toggle "Use custom Dockerfile" → `dockerfile_path: demo/api/Dockerfile`, `build_context: demo/api`, port `8000`.
- Step 4 **Runtime**:
  - Resource tier: Standard
  - Custom domain: `demo-api.iyziops.com`
  - Health check path: `/ready`
  - Env vars: (leave empty — connect-service injects `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`)
- Step 5 **Services**: check `demo-pg`, `demo-cache`, `demo-queue`.
- Review → **Create & Build**.
- Watch the build log stream (5 pipeline steps). Wait for pod Running (~8-10 min).
- Open `https://demo-api.iyziops.com/test` → should return `{"all_ok": true}`.

### 4. Deploy demo-ui
- **Apps** tab → + New App
- Step 1: name `Demo UI`
- Step 2: same repo, branch `main`.
- Step 3: `dockerfile_path: demo/ui/Dockerfile`, `build_context: demo/ui`, port `3000`.
- Step 4:
  - Custom domain: `demo.iyziops.com`
  - Health path: `/`
  - Env vars: `NEXT_PUBLIC_API_URL=https://demo-api.iyziops.com`
- Step 5: no services.
- Review → **Create & Build**.
- Open `https://demo.iyziops.com` → notes list renders, create note works, stats bar updates.

### 5. Verify
- Click around. No console errors. No CORS failures. Redis hit counter climbs as you re-list.

## What you're actually proving

- Multi-tenant namespace isolation (tenant-demo) with PSA, ResourceQuota, CiliumNetworkPolicy
- Managed service operators (Everest/CNPG, OpsTree, RabbitMQ cluster op) provisioning on demand
- Git-based builds via BuildKit + Nixpacks/Dockerfile + push to Harbor
- HTTPRoute on Cilium Gateway with wildcard `*.iyziops.com` TLS
- SSE log streaming, Harbor image digest pinning, auto-scaling HPA

All through one 5-step wizard per app.

## Live URLs

| Service | URL |
|---|---|
| Demo UI | https://demo.iyziops.com |
| Demo API | https://demo-api.iyziops.com |
| Demo API docs | https://demo-api.iyziops.com/docs |
| Demo API `/test` | https://demo-api.iyziops.com/test |
| Demo API `/stats` | https://demo-api.iyziops.com/stats |

## Rollback

If the demo needs to be torn down and re-provisioned:

```
Apps tab  → delete demo-ui, demo-api
Services  → delete demo-queue, demo-cache, demo-pg
Organizations → delete demo tenant
```

Then repeat the "Deploy reproducing steps" above. 15 minutes, zero terminal.
