# event-store — MongoDB + Kafka

Event-sourced API. Every `POST /events` both persists to MongoDB and publishes
to Kafka topic `events.v1`. Meant to be paired with `samples/analytics/`
which consumes the same topic.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health`, `/ready` | Probes |
| `GET` | `/test` | Exercise MongoDB + Kafka, return report |
| `POST` | `/events` | Insert event into Mongo + publish to Kafka |
| `GET` | `/events/{id}` | Fetch a single event |
| `GET` | `/events?type=...` | List events (filter by type) |
| `GET` | `/docs` | OpenAPI Swagger |

## Service env vars

| Var | Source |
|---|---|
| `MONGODB_URI` | MongoDB service secret (Everest PSMDB) |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka service secret (Strimzi) |
| `KAFKA_TOPIC` | Defaults to `events.v1` — override per deploy |

## Deploy via iyziops

```
Repo URL:      https://github.com/NimbusProTch/InfraForge-Haven.git
Branch:        main
Build context: samples/event-store
Dockerfile:    samples/event-store/Dockerfile
Port:          8000
```

Request: `events-mongo` (mongodb), `events-stream` (kafka).

## Why this stack

- **MongoDB** exercises the Everest PSMDB (Percona Server for MongoDB) operator
  path — different from the PXC/PG paths the other samples use.
- **Kafka** is the newest managed service (added as type #6 in commit 7474cb1
  on 2026-04-17). This sample is the canonical functional test that Kafka
  actually works E2E through iyziops: Strimzi CRD → operator reconcile →
  bootstrap Service → client connects → messages flow.

If you need to validate the Strimzi operator after any platform change,
deploy this app and watch `/test` return `{"kafka": {"ok": true}}`.
