"""analytics — MySQL + Redis + Kafka sample app for iyziops.

Consumes events from Kafka topic `events.v1` (produced by event-store sample),
counts them per type, stores rolling counters in both Redis (real-time) and
MySQL (durable aggregates).

Endpoints:
  GET  /stats               → current counters (Redis + MySQL)
  GET  /consumer-status     → is the Kafka consumer alive?
  POST /track               → manual event injection (bypass Kafka)
  GET  /test                → exercise all 3 services
  GET  /health /ready       → probes
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis
from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger("analytics")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# iyziops Everest-managed MySQL creds.
# Example: mysql://user:pass@host:3306/dbname — we normalize to aiomysql driver.
_MYSQL_RAW = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL", "mysql://analytics:analytics@localhost:3306/analytics")
MYSQL_URL = _MYSQL_RAW.replace("mysql://", "mysql+aiomysql://", 1)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "events.v1")
KAFKA_GROUP = os.getenv("KAFKA_GROUP", "analytics")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class EventCounter(Base):
    __tablename__ = "event_counters"
    event_type: Mapped[str] = mapped_column(String(128), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


engine = create_async_engine(MYSQL_URL, pool_size=5, max_overflow=5)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Kafka consumer — runs in background task
# ---------------------------------------------------------------------------


async def consume_events(state: dict):
    """Consume events from Kafka and roll up counters."""
    state["consumer_alive"] = False
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    try:
        await consumer.start()
        state["consumer_alive"] = True
        state["consumer"] = consumer
        logger.info("kafka consumer started (topic=%s group=%s)", KAFKA_TOPIC, KAFKA_GROUP)
        async for msg in consumer:
            evt = msg.value
            etype = evt.get("type", "unknown")
            # Redis rolling counter (real-time view)
            await state["redis"].incr(f"stats:count:{etype}")
            await state["redis"].set("stats:last_event", json.dumps({"type": etype, "at": datetime.utcnow().isoformat() + "Z"}))
            state["consumed"] += 1
            # Persist every 10 to MySQL
            if state["consumed"] % 10 == 0:
                await _flush_to_mysql(state)
    except asyncio.CancelledError:
        logger.info("consumer cancelled")
        raise
    except Exception:
        logger.exception("kafka consumer crashed")
        state["consumer_alive"] = False
    finally:
        try:
            await consumer.stop()
        except Exception:
            pass


async def _flush_to_mysql(state: dict) -> None:
    """Copy Redis counters to MySQL for durable aggregates."""
    async with SessionLocal() as db:
        keys = await state["redis"].keys("stats:count:*")
        for k in keys:
            etype = k.split(":")[-1]
            count = int(await state["redis"].get(k) or 0)
            await db.execute(
                text(
                    "INSERT INTO event_counters (event_type, count, last_seen) "
                    "VALUES (:t, :c, NOW()) "
                    "ON DUPLICATE KEY UPDATE count = VALUES(count), last_seen = NOW()"
                ),
                {"t": etype, "c": count},
            )
        await db.commit()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

state: dict = {
    "redis": None,
    "consumer": None,
    "consumer_task": None,
    "consumer_alive": False,
    "consumed": 0,
    "ready": False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("analytics starting")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    state["redis"] = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await state["redis"].ping()
    state["consumer_task"] = asyncio.create_task(consume_events(state))
    await asyncio.sleep(2)  # give consumer a chance to connect
    state["ready"] = True
    logger.info("analytics ready")
    yield
    state["ready"] = False
    state["consumer_task"].cancel()
    try:
        await state["consumer_task"]
    except asyncio.CancelledError:
        pass
    await state["redis"].aclose()
    await engine.dispose()


app = FastAPI(title="analytics", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class TrackIn(BaseModel):
    type: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    if not state["ready"]:
        raise HTTPException(503, "not ready")
    return {"status": "ready", "consumer_alive": state["consumer_alive"]}


@app.get("/consumer-status")
async def consumer_status() -> dict:
    return {
        "alive": state["consumer_alive"],
        "consumed": state["consumed"],
        "topic": KAFKA_TOPIC,
        "group": KAFKA_GROUP,
    }


@app.post("/track")
async def track(evt: TrackIn) -> dict:
    """Manually bump a counter (bypass Kafka — useful for testing MySQL/Redis path)."""
    await state["redis"].incr(f"stats:count:{evt.type}")
    await _flush_to_mysql(state)
    return {"ok": True, "type": evt.type}


@app.get("/stats")
async def stats() -> dict:
    """Return current stats from Redis + MySQL."""
    redis_counts: dict = {}
    for k in await state["redis"].keys("stats:count:*"):
        redis_counts[k.split(":")[-1]] = int(await state["redis"].get(k) or 0)

    async with SessionLocal() as db:
        rows = (await db.execute(text("SELECT event_type, count, last_seen FROM event_counters"))).all()
    mysql_counts = [{"type": r[0], "count": r[1], "last_seen": r[2].isoformat() if r[2] else None} for r in rows]

    return {"redis_counts": redis_counts, "mysql_counts": mysql_counts}


@app.get("/test")
async def test_stack() -> dict:
    report: dict = {"stack": "mysql+redis+kafka", "started": time.time(), "checks": {}}
    # MySQL
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        report["checks"]["mysql"] = {"ok": True}
    except Exception as e:
        report["checks"]["mysql"] = {"ok": False, "error": str(e)}
    # Redis
    try:
        await state["redis"].ping()
        report["checks"]["redis"] = {"ok": True}
    except Exception as e:
        report["checks"]["redis"] = {"ok": False, "error": str(e)}
    # Kafka (consumer liveness is the best proxy — producer not needed here)
    report["checks"]["kafka"] = {
        "ok": state["consumer_alive"],
        "consumed": state["consumed"],
    }
    report["elapsed"] = round(time.time() - report["started"], 3)
    report["all_ok"] = all(c.get("ok") for c in report["checks"].values())
    return report
