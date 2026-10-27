"""SQLAlchemy 2 models. Every table carries tenant_id; create_all on startup (v0.1, no Alembic)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, Integer, String, UniqueConstraint,
                        create_engine, func, Index)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Blob(Base):
    __tablename__ = "blobs"
    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_type: Mapped[str] = mapped_column(String)  # MIME type served by /v1/media
    bytes: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = _now()


class AssetVersion(Base):
    __tablename__ = "asset_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "asset_id", "revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    asset_id: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    media_type: Mapped[str] = mapped_column(String)  # category: video|audio|image|...
    mime: Mapped[str] = mapped_column(String)
    bytes: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _now()


class ContractRow(Base):
    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("tenant_id", "contract_id", "revision"),
                      UniqueConstraint("tenant_id", "sha256"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    contract_id: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),
                      Index("ix_runs_claim", "status", "lease_expires_at"))
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    run_mode: Mapped[str] = mapped_column(String)
    contract_sha256: Mapped[str] = mapped_column(String(64))
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # [{asset_id, revision, sha256}]
    assertion_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    previous_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String(64))
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    cost_usd_estimated: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = _now()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Envelope(Base):
    __tablename__ = "envelopes"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _now()


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("tenant_id", "run_id", "sha256"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    media_type: Mapped[str] = mapped_column(String)
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now()


class BudgetState(Base):
    """One row per tenant-agnostic project budget; locked FOR UPDATE to serialise reservations."""
    __tablename__ = "budget_state"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, default="*")
    created_at: Mapped[datetime] = _now()


class BudgetLedger(Base):
    __tablename__ = "budget_ledger"
    reservation_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    purpose: Mapped[str] = mapped_column(String)
    reserved_usd: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String)  # open | settled | seed
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)  # None when unknown
    cost_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    remote_request_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = _now()
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepairRequestRow(Base):
    __tablename__ = "repair_requests"
    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    plan_sha256: Mapped[str] = mapped_column(String(64), index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


class RepairReceiptRow(Base):
    __tablename__ = "repair_receipts"
    receipt_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    request_id: Mapped[str] = mapped_column(String, index=True)
    new_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()


_engines: dict[str, Engine] = {}


def get_engine(url: str) -> Engine:
    if url not in _engines:
        _engines[url] = create_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True)
    return _engines[url]


def make_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """create_all guarded by an advisory lock so api and worker may start concurrently."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(727001)"))
        Base.metadata.create_all(conn)
