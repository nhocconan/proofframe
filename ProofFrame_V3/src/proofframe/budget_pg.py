"""Postgres-backed atomic spend ledger implementing interfaces.Budget.

Counted as spent: settled rows with a known cost (actual), open reservations (reserved amount),
and settled rows with unknown cost (reserved amount stays counted: unknown is not free).
"""
from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import Settings
from .db import BudgetLedger, BudgetState
from .interfaces import BudgetExhausted

SEED_ID = "probe-seed"
_LOCK = "project"


class PgBudget:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.s = settings
        self.seed_probe_spend()

    # -- accounting -------------------------------------------------------------------------
    @staticmethod
    def _counted():
        # actual cost when known, otherwise the reserved amount
        return func.coalesce(
            func.sum(case((BudgetLedger.state == "open", BudgetLedger.reserved_usd),
                          else_=func.coalesce(BudgetLedger.cost_usd, BudgetLedger.reserved_usd))), 0.0)

    def seed_probe_spend(self) -> None:
        if self.s.probe_spend_usd <= 0:
            return
        with Session(self.engine) as db, db.begin():
            db.execute(pg_insert(BudgetState).values(name=_LOCK).on_conflict_do_nothing())
            db.execute(pg_insert(BudgetLedger).values(
                reservation_id=SEED_ID, tenant_id=self.s.tenant_id, run_id="gate0-probes",
                provider="meta", model="gate0-probes", purpose="prior probe spend",
                reserved_usd=self.s.probe_spend_usd, state="seed", cost_usd=self.s.probe_spend_usd,
                cost_basis="usage*list_price",
            ).on_conflict_do_nothing(index_elements=["reservation_id"]))

    def summary(self) -> dict[str, Any]:
        with Session(self.engine) as db:
            settled = db.scalar(select(func.coalesce(func.sum(
                case((BudgetLedger.state.in_(("settled", "seed")),
                      func.coalesce(BudgetLedger.cost_usd, BudgetLedger.reserved_usd)), else_=0.0)), 0.0)))
            opened = db.scalar(select(func.coalesce(func.sum(
                case((BudgetLedger.state == "open", BudgetLedger.reserved_usd), else_=0.0)), 0.0)))
            unknown = db.scalar(select(func.count()).where(
                BudgetLedger.state == "settled", BudgetLedger.cost_usd.is_(None)))
        return {"cap_project_usd": self.s.max_project_cost_usd, "cap_run_usd": self.s.max_run_cost_usd,
                "spent_settled_usd": float(settled), "reserved_open_usd": float(opened),
                "unknown_cost_calls": int(unknown)}

    # -- Budget protocol --------------------------------------------------------------------
    def reserve(self, *, run_id: str, provider: str, model: str, amount_usd: float,
                purpose: str) -> str:
        if not self.s.allow_paid_calls:
            raise BudgetExhausted("paid calls disabled (PROOFFRAME_ALLOW_PAID_CALLS != true)")
        if not (isinstance(amount_usd, (int, float)) and math.isfinite(amount_usd) and amount_usd > 0):
            raise BudgetExhausted(f"invalid reservation amount: {amount_usd!r}")
        if self.s.max_project_cost_usd is None or self.s.max_run_cost_usd is None:
            raise BudgetExhausted("cost caps not configured")
        rid = "rsv-" + uuid.uuid4().hex
        with Session(self.engine) as db, db.begin():
            db.execute(pg_insert(BudgetState).values(name=_LOCK).on_conflict_do_nothing())
            db.execute(select(BudgetState).where(BudgetState.name == _LOCK).with_for_update())
            project = float(db.scalar(select(self._counted())) or 0.0)
            run = float(db.scalar(select(self._counted()).where(BudgetLedger.run_id == run_id)) or 0.0)
            if project + amount_usd > self.s.max_project_cost_usd + 1e-12:
                raise BudgetExhausted(
                    f"project cap ${self.s.max_project_cost_usd} would be exceeded "
                    f"(counted ${project:.5f} + ${amount_usd:.5f})")
            if run + amount_usd > self.s.max_run_cost_usd + 1e-12:
                raise BudgetExhausted(
                    f"run cap ${self.s.max_run_cost_usd} would be exceeded "
                    f"(counted ${run:.5f} + ${amount_usd:.5f})")
            db.add(BudgetLedger(reservation_id=rid, tenant_id=self.s.tenant_id, run_id=run_id,
                                provider=provider, model=model, purpose=purpose,
                                reserved_usd=float(amount_usd), state="open"))
        return rid

    def settle(self, reservation_id: str, *, cost_usd: float | None, cost_basis: str,
               usage: dict[str, Any] | None, remote_request_id: str | None, outcome: str) -> None:
        if cost_usd is not None and not (math.isfinite(cost_usd) and cost_usd >= 0):
            cost_usd = None  # unpriceable -> keep reservation counted
        with Session(self.engine) as db, db.begin():
            row = db.scalar(select(BudgetLedger).where(
                BudgetLedger.reservation_id == reservation_id).with_for_update())
            if row is None:
                raise KeyError(f"unknown reservation {reservation_id}")
            if row.state != "open":
                return  # idempotent: first settlement wins
            row.state = "settled"
            row.cost_usd = cost_usd
            row.cost_basis = cost_basis
            row.usage = usage
            row.remote_request_id = remote_request_id
            row.outcome = outcome
            row.settled_at = func.now()
