"""event-store — MongoDB + Kafka sample app for iyziops.

Event-sourced store. Each POST /events both:
  (1) writes the event document to MongoDB (durable store)
  (2) publishes a message to Kafka topic `events.v1` (stream fan-out)

Used alongside `samples/analytics/` which consumes events.v1 from Kafka.

Endpoints:
  POST /events            → store + publish
  GET  /events/{id}       → fetch from Mongo
  GET  /events?type=...   → list (filter by type)
  GET  /test              → exercise both services + return report
  GET  /health /ready     → probes
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from aiokafka import AIOKafkaProducer
from fastapi import FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

logger = logging.getLogger("event-store")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# iyziops Everest-managed MongoDB cred:
#   primary secret key is MONGODB_URI or MONGO_URI; fallback to local.
MONGO_URL = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "mongodb://localhost:27017/events"
MONGO_DB = os.getenv("MONGO_DB", "events")

# iyziops Strimzi-managed Kafka bootstrap servers:
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "events.v1")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EventIn(BaseModel):
    type: str = Field(..., examples=["order.placed"])
    payload: dict = Field(default_factory=dict)


class EventOut(BaseModel):
    id: str
    type: str
    payload: dict
    created_at: str


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

state: dict = {"mongo": None, "events": None, "producer": None, "ready": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("event-store starting")
    state["mongo"] = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    state["events"] = state["mongo"][MONGO_DB]["events"]
    # index on type for /events?type= query
    await state["events"].create_index("type")
    await state["events"].create_index("created_at")

    state["producer"] = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        enable_idempotence=True,
    )
    await state["producer"].start()

    state["ready"] = True
    logger.info("event-store ready (mongo=%s kafka=%s)", MONGO_URL, KAFKA_BOOTSTRAP)
    yield
    state["ready"] = False
    await state["producer"].stop()
    state["mongo"].close()


app = FastAPI(title="event-store", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    if not state["ready"]:
        raise HTTPException(503, "not ready")
    return {"status": "ready"}


@app.post("/events", response_model=EventOut)
async def create_event(ev: EventIn) -> EventOut:
    ev_id = str(uuid.uuid4())
    doc = {
        "_id": ev_id,
        "type": ev.type,
        "payload": ev.payload,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    await state["events"].insert_one(doc)
    # Publish to Kafka for downstream consumers
    await state["producer"].send_and_wait(KAFKA_TOPIC, {"id": ev_id, **{k: doc[k] for k in ("type", "payload", "created_at")}})
    return EventOut(id=ev_id, type=ev.type, payload=ev.payload, created_at=doc["created_at"])


@app.get("/events/{event_id}", response_model=EventOut)
async def get_event(event_id: str) -> EventOut:
    doc = await state["events"].find_one({"_id": event_id})
    if not doc:
        raise HTTPException(404, "event not found")
    return EventOut(id=doc["_id"], type=doc["type"], payload=doc["payload"], created_at=doc["created_at"])


@app.get("/events", response_model=list[EventOut])
async def list_events(type: str | None = Query(default=None), limit: int = 50) -> list[EventOut]:
    query = {"type": type} if type else {}
    cursor = state["events"].find(query).sort("created_at", -1).limit(min(limit, 200))
    return [
        EventOut(id=d["_id"], type=d["type"], payload=d["payload"], created_at=d["created_at"])
        async for d in cursor
    ]


@app.get("/test")
async def test_stack() -> dict:
    report: dict = {"stack": "mongo+kafka", "started": time.time(), "checks": {}}
    # Mongo
    try:
        await state["mongo"].admin.command("ping")
        count = await state["events"].estimated_document_count()
        report["checks"]["mongodb"] = {"ok": True, "events_count": count}
    except Exception as e:
        report["checks"]["mongodb"] = {"ok": False, "error": str(e)}
    # Kafka
    try:
        meta = await asyncio.wait_for(
            state["producer"].client.fetch_all_metadata(), timeout=5.0
        )
        report["checks"]["kafka"] = {
            "ok": True,
            "brokers": len(meta.brokers),
            "topics": [t for t in meta.topics if not t.startswith("__")][:10],
        }
    except Exception as e:
        report["checks"]["kafka"] = {"ok": False, "error": str(e)}
    report["elapsed"] = round(time.time() - report["started"], 3)
    report["all_ok"] = all(c.get("ok") for c in report["checks"].values())
    return report
