# notes-api — PG + Redis + RabbitMQ

A minimalist note-taking API that exercises three iyziops managed services:

- **PostgreSQL** (Everest-managed) — notes table
- **Redis** (OpsTree operator) — read cache (30s TTL on lists, 5min on single)
- **RabbitMQ** (RabbitMQ operator) — publishes `notes.created` on every POST

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness probe (no deps) |
| `GET` | `/ready` | Readiness probe (asserts startup complete) |
| `GET` | `/test` | **Exercise every service** and return JSON report |
| `POST` | `/notes` | Create a note (PG insert + RMQ publish) |
| `GET` | `/notes` | List last 100 notes (Redis-cached 30s) |
| `GET` | `/notes/{id}` | Fetch a note (Redis lookup, PG fallback) |
| `GET` | `/docs` | OpenAPI Swagger UI |

## Service env vars

iyziops injects these via `envFrom.secretRef` when connected services are wired:

| Var | Source |
|---|---|
| `DATABASE_URL` | `svc-<pg-service-name>` secret, key `uri` (Everest) |
| `REDIS_URL` | `<redis-service-name>` secret, key `uri` (OpsTree) |
| `RABBITMQ_URL` | `<rabbitmq-service-name>-default-user` secret (RabbitMQ operator) |

## Deploy via iyziops

```
Repo URL:      https://github.com/NimbusProTch/InfraForge-Haven.git
Branch:        main
Build context: samples/notes-api
Dockerfile:    samples/notes-api/Dockerfile
Port:          8000
```

Request three services during app creation:
- `notes-pg` → PostgreSQL (Everest)
- `notes-cache` → Redis
- `notes-queue` → RabbitMQ

After services reach READY, iyziops auto-connects them (sets the env vars)
and re-deploys the app. Watch `/test` return `{"all_ok": true}`.

## Local dev

```bash
docker compose up -d   # starts pg + redis + rabbitmq
pip install -r requirements.txt
uvicorn app:app --reload
curl http://localhost:8000/test | jq
```

## Why this stack

PG + Redis + RabbitMQ is the canonical "modern webapp" pairing. It validates
the three most common provisioner paths:
- **Everest → Percona PG** (managed relational)
- **OpsTree → Redis** (direct CRD, no Everest)
- **RabbitMQ operator** (direct CRD, no Everest)

If any of these provisioners regress, `notes-api` is the first to fail in
`/test`.
