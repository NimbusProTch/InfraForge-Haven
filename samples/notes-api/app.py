"""notes-api — PostgreSQL + Redis + RabbitMQ sample app for iyziops.

Exercises all three connected services:
  POST /notes            → INSERT into PG + RabbitMQ publish ("notes.created")
  GET  /notes            → SELECT ... from PG (optionally Redis-cached)
  GET  /notes/{id}       → Redis lookup first, fallback PG + cache
  GET  /test             → health + exercise every service, structured report
  GET  /health /ready    → k8s probe endpoints
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import aio_pika
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger("notes-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Config (iyziops injects service creds via envFrom.secretRef)
# ---------------------------------------------------------------------------

# PostgreSQL — iyziops Everest-managed creds:
#   DATABASE_URL is iyziops-convention. Fallback to compose of PG* parts.
POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://notes:notes@localhost:5432/notes",
).replace("postgresql://", "postgresql+asyncpg://", 1)

# Redis — iyziops OpsTree managed
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# RabbitMQ — iyziops RabbitMQ operator managed
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


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
# Lifespan: connect, create table, keep connections alive
# ---------------------------------------------------------------------------

state: dict = {"redis": None, "rabbit_conn": None, "rabbit_channel": None, "ready": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("notes-api starting")
    # PG schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Redis
    state["redis"] = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await state["redis"].ping()
    # RabbitMQ
    state["rabbit_conn"] = await aio_pika.connect_robust(RABBITMQ_URL)
    state["rabbit_channel"] = await state["rabbit_conn"].channel()
    await state["rabbit_channel"].declare_queue("notes.created", durable=True)
    state["ready"] = True
    logger.info("notes-api ready")
    yield
    state["ready"] = False
    await state["redis"].aclose()
    await state["rabbit_conn"].close()
    await engine.dispose()


app = FastAPI(title="notes-api", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class NoteIn(BaseModel):
    title: str
    body: str


class NoteOut(BaseModel):
    id: str
    title: str
    body: str


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


@app.post("/notes", response_model=NoteOut)
async def create_note(note: NoteIn) -> NoteOut:
    note_id = str(uuid.uuid4())
    async with SessionLocal() as db:
        db.add(Note(id=note_id, title=note.title, body=note.body))
        await db.commit()
    await state["rabbit_channel"].default_exchange.publish(
        aio_pika.Message(body=json.dumps({"id": note_id, "title": note.title}).encode()),
        routing_key="notes.created",
    )
    await state["redis"].delete("notes:list")
    return NoteOut(id=note_id, title=note.title, body=note.body)


@app.get("/notes", response_model=list[NoteOut])
async def list_notes() -> list[NoteOut]:
    cached = await state["redis"].get("notes:list")
    if cached:
        return [NoteOut(**n) for n in json.loads(cached)]
    async with SessionLocal() as db:
        rows = (await db.execute(text("SELECT id,title,body FROM notes ORDER BY created_at DESC LIMIT 100"))).all()
    out = [NoteOut(id=r[0], title=r[1], body=r[2]) for r in rows]
    await state["redis"].setex("notes:list", 30, json.dumps([n.model_dump() for n in out]))
    return out


@app.get("/notes/{note_id}", response_model=NoteOut)
async def get_note(note_id: str) -> NoteOut:
    cached = await state["redis"].get(f"notes:{note_id}")
    if cached:
        return NoteOut(**json.loads(cached))
    async with SessionLocal() as db:
        row = (
            await db.execute(text("SELECT id,title,body FROM notes WHERE id=:i"), {"i": note_id})
        ).one_or_none()
    if not row:
        raise HTTPException(404, "note not found")
    out = NoteOut(id=row[0], title=row[1], body=row[2])
    await state["redis"].setex(f"notes:{note_id}", 300, json.dumps(out.model_dump()))
    return out


@app.get("/test")
async def test_stack() -> dict:
    """Exercise every service and return a structured health report."""
    report: dict = {"stack": "pg+redis+rabbit", "started": time.time(), "checks": {}}
    # PG
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        report["checks"]["postgres"] = {"ok": True}
    except Exception as e:
        report["checks"]["postgres"] = {"ok": False, "error": str(e)}
    # Redis
    try:
        pong = await state["redis"].ping()
        report["checks"]["redis"] = {"ok": bool(pong)}
    except Exception as e:
        report["checks"]["redis"] = {"ok": False, "error": str(e)}
    # RabbitMQ
    try:
        await state["rabbit_channel"].default_exchange.publish(
            aio_pika.Message(body=b'{"ping":true}'),
            routing_key="notes.created",
        )
        report["checks"]["rabbitmq"] = {"ok": True}
    except Exception as e:
        report["checks"]["rabbitmq"] = {"ok": False, "error": str(e)}
    report["elapsed"] = round(time.time() - report["started"], 3)
    report["all_ok"] = all(c.get("ok") for c in report["checks"].values())
    return report
