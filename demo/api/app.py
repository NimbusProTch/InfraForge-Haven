"""demo-api — iyziops Permanent Demo API

PostgreSQL + Redis + RabbitMQ. NO AUTH (demo is about platform, not auth).

Story: "I deployed this API via iyziops UI in 5 minutes. It uses managed PG,
Redis cache, and async RabbitMQ notifications. Zero YAML, zero kubectl."

Endpoints:
  GET  /health                → always 200 (liveness)
  GET  /ready                 → 200 only when PG+Redis+RabbitMQ all connected
  GET  /test                  → exercise every service, return JSON report
  GET  /stats                 → live counters (redis hits/misses, rmq messages)
  GET  /notes                 → list notes (Redis-cached 30s)
  GET  /notes/{id}            → single note (Redis-cached 5min)
  POST /notes                 → insert + RabbitMQ publish
  DELETE /notes/{id}          → delete + cache invalidate
  GET  /                      → API info + links

Env vars injected by iyziops `connect-service`:
  DATABASE_URL (postgres)     → demo-pg
  REDIS_URL                   → demo-cache
  RABBITMQ_URL                → demo-queue
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

import aio_pika
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, String, func, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger("demo-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Config — iyziops connect-service injects these via envFrom.secretRef
# ---------------------------------------------------------------------------

POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://demo:demo@localhost:5432/demo",
).replace("postgresql://", "postgresql+asyncpg://", 1)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# CORS: demo-ui.iyziops.com → demo-api.iyziops.com
# Wildcard forbidden (platform security rule). Literal origins only.
CORS_ALLOW_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "DEMO_CORS_ORIGINS",
        "https://demo.iyziops.com,http://localhost:3000",
    ).split(",")
    if o.strip()
]


# ---------------------------------------------------------------------------
# SQLAlchemy model
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(4096))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


engine = create_async_engine(POSTGRES_URL, pool_size=5, max_overflow=5)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NoteIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., max_length=4096)


class NoteOut(BaseModel):
    id: str
    title: str
    body: str
    created_at: str | None = None


# ---------------------------------------------------------------------------
# Lifespan: connect services + start RabbitMQ consumer + seed data
# ---------------------------------------------------------------------------

state: dict = {
    "redis": None,
    "rabbit_conn": None,
    "rabbit_channel": None,
    "consumer_task": None,
    "ready": False,
    "counters": {
        "redis_hits": 0,
        "redis_misses": 0,
        "rmq_published": 0,
        "rmq_consumed": 0,
    },
}


async def _rabbit_consumer(state: dict) -> None:
    """Background task: consume `notes.created` and increment counter."""
    try:
        channel = state["rabbit_channel"]
        queue = await channel.declare_queue("notes.created", durable=True)
        logger.info("rabbit consumer started on notes.created")
        async with queue.iterator() as q_iter:
            async for msg in q_iter:
                async with msg.process():
                    state["counters"]["rmq_consumed"] += 1
                    try:
                        body = json.loads(msg.body)
                        logger.info("consumed: id=%s type=%s", body.get("id", "?"), body.get("type", "?"))
                    except Exception:
                        pass
    except asyncio.CancelledError:
        logger.info("rabbit consumer cancelled")
        raise
    except Exception:
        logger.exception("rabbit consumer crashed")


async def _seed_notes() -> None:
    """Insert 5 sample notes if the table is empty (fresh demo)."""
    async with SessionLocal() as db:
        count = (await db.execute(text("SELECT COUNT(*) FROM notes"))).scalar() or 0
        if count > 0:
            logger.info("skipping seed (notes already populated: %d)", count)
            return
        samples = [
            ("Welcome to iyziops Demo", "This API is deployed through the iyziops platform. Zero YAML, zero kubectl."),
            ("Backed by PostgreSQL", "Managed by Percona Everest. Created via Services tab in iyziops UI."),
            ("Cached with Redis", "GET /notes hits Redis first; DB fallback on miss. See /stats for hit ratio."),
            ("Notifications via RabbitMQ", "Every POST /notes publishes to the notes.created queue. Consumer logs show up in /stats."),
            ("Try it", "curl -X POST demo-api.iyziops.com/notes -d '{\"title\":\"hello\",\"body\":\"world\"}' — it survives pod restart."),
        ]
        for title, body in samples:
            db.add(Note(id=str(uuid.uuid4()), title=title, body=body))
        await db.commit()
        logger.info("seeded 5 sample notes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("demo-api starting — cors=%s", CORS_ALLOW_ORIGINS)
    # Create table if missing
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed sample data
    try:
        await _seed_notes()
    except Exception:
        logger.exception("seed failed (non-fatal)")
    # Redis
    state["redis"] = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await state["redis"].ping()
    # RabbitMQ
    state["rabbit_conn"] = await aio_pika.connect_robust(RABBITMQ_URL)
    state["rabbit_channel"] = await state["rabbit_conn"].channel()
    await state["rabbit_channel"].declare_queue("notes.created", durable=True)
    # Background consumer
    state["consumer_task"] = asyncio.create_task(_rabbit_consumer(state))
    state["ready"] = True
    logger.info("demo-api ready")
    yield
    state["ready"] = False
    if state["consumer_task"]:
        state["consumer_task"].cancel()
        try:
            await state["consumer_task"]
        except asyncio.CancelledError:
            pass
    await state["redis"].aclose()
    await state["rabbit_conn"].close()
    await engine.dispose()


app = FastAPI(
    title="iyziops Demo API",
    description="Permanent demo backing https://demo.iyziops.com — FastAPI + Postgres + Redis + RabbitMQ",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root() -> dict:
    return {
        "name": "iyziops Demo API",
        "docs": "/docs",
        "endpoints": ["/health", "/ready", "/test", "/stats", "/notes"],
        "ui": "https://demo.iyziops.com",
        "deployed_via": "iyziops platform (UI wizard)",
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    if not state["ready"]:
        raise HTTPException(503, "not ready — services still connecting")
    return {"status": "ready"}


@app.get("/stats")
async def stats() -> dict:
    async with SessionLocal() as db:
        note_count = (await db.execute(text("SELECT COUNT(*) FROM notes"))).scalar() or 0
    return {
        "notes_in_db": note_count,
        **state["counters"],
        "cache_hit_ratio": (
            round(
                state["counters"]["redis_hits"]
                / max(state["counters"]["redis_hits"] + state["counters"]["redis_misses"], 1),
                3,
            )
        ),
    }


@app.post("/notes", response_model=NoteOut)
async def create_note(note: NoteIn) -> NoteOut:
    note_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    async with SessionLocal() as db:
        db.add(Note(id=note_id, title=note.title, body=note.body))
        await db.commit()
    await state["rabbit_channel"].default_exchange.publish(
        aio_pika.Message(
            body=json.dumps({"id": note_id, "title": note.title, "type": "note.created"}).encode(),
            content_type="application/json",
        ),
        routing_key="notes.created",
    )
    state["counters"]["rmq_published"] += 1
    await state["redis"].delete("notes:list")
    return NoteOut(id=note_id, title=note.title, body=note.body, created_at=now)


@app.get("/notes", response_model=list[NoteOut])
async def list_notes() -> list[NoteOut]:
    cached = await state["redis"].get("notes:list")
    if cached:
        state["counters"]["redis_hits"] += 1
        return [NoteOut(**n) for n in json.loads(cached)]
    state["counters"]["redis_misses"] += 1
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id, title, body, created_at::text AS created_at "
                    "FROM notes ORDER BY created_at DESC LIMIT 100"
                )
            )
        ).all()
    out = [NoteOut(id=r[0], title=r[1], body=r[2], created_at=r[3]) for r in rows]
    await state["redis"].setex("notes:list", 30, json.dumps([n.model_dump() for n in out]))
    return out


@app.get("/notes/{note_id}", response_model=NoteOut)
async def get_note(note_id: str) -> NoteOut:
    cached = await state["redis"].get(f"notes:{note_id}")
    if cached:
        state["counters"]["redis_hits"] += 1
        return NoteOut(**json.loads(cached))
    state["counters"]["redis_misses"] += 1
    async with SessionLocal() as db:
        row = (
            await db.execute(
                text("SELECT id, title, body, created_at::text AS created_at FROM notes WHERE id=:i"),
                {"i": note_id},
            )
        ).one_or_none()
    if not row:
        raise HTTPException(404, "note not found")
    out = NoteOut(id=row[0], title=row[1], body=row[2], created_at=row[3])
    await state["redis"].setex(f"notes:{note_id}", 300, json.dumps(out.model_dump()))
    return out


@app.delete("/notes/{note_id}")
async def delete_note(note_id: str) -> dict:
    async with SessionLocal() as db:
        result = await db.execute(text("DELETE FROM notes WHERE id=:i"), {"i": note_id})
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(404, "note not found")
    await state["redis"].delete(f"notes:{note_id}")
    await state["redis"].delete("notes:list")
    return {"deleted": note_id}


@app.get("/test")
async def test_stack() -> dict:
    """Exercise every service and return a structured health report."""
    report: dict = {"stack": "pg+redis+rabbitmq", "started": time.time(), "checks": {}}
    # PG
    try:
        async with SessionLocal() as db:
            count = (await db.execute(text("SELECT COUNT(*) FROM notes"))).scalar() or 0
        report["checks"]["postgres"] = {"ok": True, "notes_count": count}
    except Exception as e:
        report["checks"]["postgres"] = {"ok": False, "error": str(e)}
    # Redis
    try:
        pong = await state["redis"].ping()
        await state["redis"].setex("demo:test:ping", 5, str(int(time.time())))
        val = await state["redis"].get("demo:test:ping")
        report["checks"]["redis"] = {"ok": bool(pong) and val is not None}
    except Exception as e:
        report["checks"]["redis"] = {"ok": False, "error": str(e)}
    # RabbitMQ
    try:
        await state["rabbit_channel"].default_exchange.publish(
            aio_pika.Message(body=json.dumps({"type": "test.ping", "ts": time.time()}).encode()),
            routing_key="notes.created",
        )
        state["counters"]["rmq_published"] += 1
        report["checks"]["rabbitmq"] = {"ok": True, "counters": dict(state["counters"])}
    except Exception as e:
        report["checks"]["rabbitmq"] = {"ok": False, "error": str(e)}
    report["elapsed"] = round(time.time() - report["started"], 3)
    report["all_ok"] = all(c.get("ok") for c in report["checks"].values())
    return report
