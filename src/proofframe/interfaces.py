"""Seams between the verification core (lead-owned) and persistence/transport (worker-owned).

The core never imports SQLAlchemy/FastAPI; the API never imports provider code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class BudgetExhausted(Exception):
    """Reservation refused: the paid call must not be made (check -> NOT_CHECKED)."""


class Budget(Protocol):
    """Atomic spend ledger. Reserve a conservative upper bound BEFORE a paid call.

    settle(cost_usd=None) means usage could not be priced: the reservation stays
    counted as spent (unknown is not free).
    """

    def reserve(self, *, run_id: str, provider: str, model: str, amount_usd: float,
                purpose: str) -> str: ...  # returns reservation_id or raises BudgetExhausted

    def settle(self, reservation_id: str, *, cost_usd: float | None, cost_basis: str,
               usage: dict[str, Any] | None, remote_request_id: str | None,
               outcome: str) -> None: ...

    # Optional: remaining(*, run_id) -> float | None — headroom under the caps. When present, the pipeline
    # plans the run to fit it before any paid call (verify/plan.py); when absent the full plan runs.


class Store(Protocol):
    """Content-addressed immutable blob store (sha256)."""

    def put_file(self, src: Path, *, media_type: str) -> str: ...  # returns sha256
    def path_for(self, sha256: str) -> Path: ...


@dataclass(frozen=True)
class AssetInput:
    """A concrete output revision bound to a logical asset slot for one run."""
    asset_id: str
    revision: int
    sha256: str  # must already be in the Store; core re-hashes before use
    media_type: str


@dataclass
class RunOutcome:
    """Everything the core produces for one verification run.

    envelope: dict matching docs/API_CONTRACT.md "ReportEnvelope" (JSON-serialisable).
    artifacts: derived files (frames, proxies) already put into the Store.
    """
    envelope: dict[str, Any]
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class Verifier(Protocol):
    def __call__(self, *, run_id: str, run_mode: str, contract_json: dict[str, Any],
                 assets: list[AssetInput], store: Store, budget: Budget,
                 assertion_ids: list[str] | None = None) -> RunOutcome: ...
    # Implemented by proofframe.verify.pipeline.run_verification.
    # assertion_ids limits a regression rerun; None = all assertions.
