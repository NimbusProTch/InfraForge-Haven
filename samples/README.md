# iyziops Sample Applications

Three reference applications that exercise the iyziops PaaS features end-to-end.
Each stack picks a different combination of managed services so the platform's
6 service types (PostgreSQL / MySQL / MongoDB / Redis / RabbitMQ / Kafka) are
all covered across the three apps.

| Sample | Stack | Story |
|---|---|---|
| [`notes-api`](./notes-api/) | PostgreSQL + Redis + RabbitMQ | Classic webapp — persistent notes, hot-cache reads, async notifications |
| [`event-store`](./event-store/) | MongoDB + Kafka | Event-sourced store — writes events to Mongo, publishes to Kafka |
| [`analytics`](./analytics/) | MySQL + Redis + Kafka | Stream-consumer analytics — consumes Kafka events, rolls counters into MySQL + Redis |

Each app exposes at minimum:
- `GET /health` — liveness + readiness probe target (must return 200 within 2s)
- `GET /ready` — deep health including service connectivity
- `GET /test` — exercises every connected service and returns a structured report
- FastAPI auto-generated OpenAPI docs at `/docs`

## Deployment via iyziops

All three apps live in this repository. Deploy them through iyziops UI by
pointing a new app at **this repo** with the appropriate `build_context`:

```
Repo URL:      https://github.com/NimbusProTch/InfraForge-Haven.git
Branch:        main
Build context: samples/notes-api   (or event-store / analytics)
Dockerfile:    samples/notes-api/Dockerfile
Port:          8000
```

### Service wiring

During app creation, request the services for the chosen stack; iyziops
auto-provisions them and wires their secrets via `envFrom.secretRef`:

| App | Services requested |
|---|---|
| notes-api | `notes-pg` (postgres), `notes-cache` (redis), `notes-queue` (rabbitmq) |
| event-store | `events-mongo` (mongodb), `events-stream` (kafka) |
| analytics | `analytics-mysql` (mysql), `analytics-cache` (redis), `analytics-stream` (kafka) |

For analytics, point its Kafka consumer at the same topic that event-store
publishes to (`events.v1`) to get a live stream flow across two apps.

## Local development

Every app has a `docker-compose.yml` that spins up its dependencies locally:

```bash
cd samples/notes-api
docker compose up -d
uvicorn app:app --reload
```

## Sprint 2026-04-18 note

These samples were added during the overnight sprint that brought Everest
online. They double as the canonical regression test for the 6 managed
service types — if any service provisioner breaks, one of these apps' `/test`
endpoint will start returning non-200 and the Playwright E2E
`journey-sample-apps.spec.ts` will fail.
