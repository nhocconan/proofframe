"""Environment-driven settings (see docker-compose.yml)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    dropbox_dir: Path
    tenant_id: str
    api_token: str
    allow_paid_calls: bool
    max_project_cost_usd: float | None  # None = unconfigured -> every paid call refused
    max_run_cost_usd: float | None
    probe_spend_usd: float
    max_upload_bytes: int = 1 << 30
    lease_seconds: int = 300
    max_attempts: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL", "postgresql+psycopg://proofframe:proofframe@db:5432/proofframe"),
            data_dir=Path(os.environ.get("PROOFFRAME_DATA_DIR", "/data")),
            dropbox_dir=Path(os.environ.get("PROOFFRAME_DROPBOX_DIR", "/dropbox")),
            tenant_id=os.environ.get("PROOFFRAME_TENANT_ID", "demo-tenant"),
            api_token=os.environ.get("PROOFFRAME_API_TOKEN", ""),
            allow_paid_calls=os.environ.get("PROOFFRAME_ALLOW_PAID_CALLS", "") == "true",
            max_project_cost_usd=_float("PROOFFRAME_MAX_PROJECT_COST_USD"),
            max_run_cost_usd=_float("PROOFFRAME_MAX_RUN_COST_USD"),
            probe_spend_usd=_float("PROOFFRAME_PROBE_SPEND_USD") or 0.0,
        )
