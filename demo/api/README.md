# demo-api

FastAPI backing `https://demo-api.iyziops.com` — the permanent iyziops demo API.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | API info |
| `GET` | `/health` | Liveness probe (always 200) |
| `GET` | `/ready` | Readiness probe (503 while services connecting) |
| `GET` | `/test` | Exercise PG + Redis + RabbitMQ, return report |
| `GET` | `/stats` | Live counters (Redis hit ratio, RMQ msg count) |
| `POST` | `/notes` | Insert note + publish to RabbitMQ |
| `GET` | `/notes` | List (30s Redis cache) |
| `GET` | `/notes/{id}` | Single (5min Redis cache) |
| `DELETE` | `/notes/{id}` | Delete + invalidate caches |
| `GET` | `/docs` | OpenAPI UI |

## Service env vars (injected by iyziops `connect-service`)

| Var | Source |
|---|---|
| `DATABASE_URL` | `demo-pg` secret (Everest Postgres) |
| `REDIS_URL` | `demo-cache` secret (OpsTree Redis) |
| `RABBITMQ_URL` | `demo-queue` secret (RabbitMQ operator) |
| `DEMO_CORS_ORIGINS` | comma-separated list — defaults to `https://demo.iyziops.com,http://localhost:3000` |

## Deploy via iyziops UI

```
Repo URL:      https://github.com/NimbusProTch/InfraForge-Haven.git
Branch:        main
Build context: demo/api
Dockerfile:    demo/api/Dockerfile
Port:          8000
Custom domain: demo-api.iyziops.com
Health path:   /ready
Services:      demo-pg, demo-cache, demo-queue
```

## Local dev

```bash
cd demo/api
docker-compose up -d      # spins up pg+redis+rabbit
pip install -r requirements.txt
uvicorn app:app --reload
curl http://localhost:8000/test | jq
```

## Why this stack

- **PostgreSQL** (Everest/CNPG) — relational store for notes
- **Redis** (OpsTree operator) — hot read cache, 30s TTL list, 5min TTL single
- **RabbitMQ** (cluster operator) — async notifications, built-in consumer logs to `/stats`

The API itself is intentionally minimal. **The story is the platform**: this entire
app + its 3 managed services deploys via iyziops UI in one 5-step wizard per app.
