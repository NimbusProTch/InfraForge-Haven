# analytics — MySQL + Redis + Kafka

Stream consumer. Tails Kafka topic `events.v1` (produced by `samples/event-store/`),
rolls counters per event type into Redis (hot view) and MySQL (durable aggregates).

Designed to run alongside `samples/event-store/` to validate end-to-end flow
across two iyziops apps connected by a shared Kafka service.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health`, `/ready` | Probes |
| `GET` | `/test` | Exercise MySQL + Redis + Kafka consumer alive check |
| `GET` | `/consumer-status` | Kafka consumer liveness + total consumed |
| `GET` | `/stats` | Current counters from Redis + MySQL |
| `POST` | `/track` | Manually bump a counter (bypass Kafka) |
| `GET` | `/docs` | OpenAPI Swagger |

## Service env vars

| Var | Source |
|---|---|
| `DATABASE_URL` | MySQL service secret (Everest PXC) — `mysql://...` |
| `REDIS_URL` | Redis service secret |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka service secret (Strimzi) |
| `KAFKA_TOPIC` | Defaults `events.v1` — must match event-store's topic |
| `KAFKA_GROUP` | Defaults `analytics` |

## Deploy via iyziops

```
Repo URL:      https://github.com/NimbusProTch/InfraForge-Haven.git
Branch:        main
Build context: samples/analytics
Dockerfile:    samples/analytics/Dockerfile
Port:          8000
```

Request: `analytics-mysql` (mysql), `analytics-cache` (redis), `analytics-stream` (kafka).

**Critical**: `analytics-stream` should reuse the SAME Kafka service instance
that `event-store` uses so consumer sees publisher's messages. In iyziops UI,
after creating both apps you can either:
- Share one Kafka service by connecting the existing one to analytics (via
  connect-service API/UI), OR
- Create two Kafka services (easier, more isolation, doubles cluster cost)

## Why this stack

- **MySQL** exercises Everest PXC (Percona XtraDB Cluster) operator path —
  different from PG (CNPG-via-Everest) and MongoDB (PSMDB-via-Everest).
- **Redis** read-path validates the cache service.
- **Kafka consumer** validates the subscriber side of the Strimzi integration
  (event-store validated the producer side). Together they prove bidirectional
  Kafka flow through iyziops-managed services.

## Local dev

```bash
docker compose up -d
pip install -r requirements.txt
uvicorn app:app --reload
# In another shell — inject events
curl -X POST localhost:8000/track -H 'content-type: application/json' -d '{"type":"login"}'
curl localhost:8000/stats | jq
```
