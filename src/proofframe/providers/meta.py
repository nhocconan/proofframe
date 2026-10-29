"""Meta developer API adapter: native video + image observation via the Responses API.

Capabilities implemented: `video_observation` (muse-spark-1.3, Files API upload, input_video fps)
and `image_observation` (input_image data URLs). The domain layer does not import this module;
the pipeline receives an `Observer` built here.

Every call: budget reservation first (conservative upper bound) -> request -> settle with
usage × list price, or cost=None (unknown; reservation stays counted).
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from jsonschema import Draft202012Validator, SchemaError, ValidationError

from ..interfaces import Budget, BudgetExhausted

PRICES_USD_PER_MTOK = {"muse-spark-1.3": (1.25, 4.25)}  # dev.meta.ai pricing page, 2026-10-27
VIDEO_TOKENS_PER_FRAME_EST = 160   # measured ~117/s at fps=1, 640px (CAPABILITY_PROBES.md) + margin
IMAGE_TOKENS_EST = 2500            # not documented; conservative reservation only
PROMPT_TOKENS_EST = 1500


class _WaitingBudget:
    """Reservations are conservative upper bounds (~4x the real cost of a frame call). With parallel calls,
    open reservations can make the cap refuse a call although real spend leaves room. On refusal, wait for
    this observer's in-flight calls to settle and retry; refuse for real only when nothing is in flight."""

    def __init__(self, inner: Budget):
        self.inner = inner
        self._cv = threading.Condition()
        self._open: set[str] = set()

    def __getattr__(self, name):  # remaining(), summary() etc. pass through
        return getattr(self.inner, name)

    def reserve(self, **kw) -> str:
        with self._cv:
            while True:
                try:
                    rid = self.inner.reserve(**kw)
                except BudgetExhausted:
                    if not self._open:
                        raise
                    self._cv.wait(timeout=30)
                    continue
                self._open.add(rid)
                return rid

    def settle(self, reservation_id: str, **kw) -> None:
        try:
            self.inner.settle(reservation_id, **kw)
        finally:
            with self._cv:
                self._open.discard(reservation_id)
                self._cv.notify_all()


@dataclass
class CallResult:
    ok: bool
    parsed: dict | None
    trace: dict[str, Any]
    outcome: str  # ok | http_error | timeout | invalid_output | incomplete | budget_exhausted | refused


@dataclass
class MetaObserver:
    api_key: str
    budget: Budget
    run_id: str
    base_url: str = "https://api.meta.ai/v1"
    model: str = "muse-spark-1.3"
    reasoning_effort: str = "low"
    max_output_tokens: int = 6000
    timeout_s: float = 300.0
    max_attempts: int = 2
    traces: list[dict[str, Any]] = field(default_factory=list)
    client: httpx.Client | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout_s)
        if not isinstance(self.budget, _WaitingBudget):
            self.budget = _WaitingBudget(self.budget)
        self._h = {"Authorization": f"Bearer {self.api_key}"}

    # ---------- cost helpers
    def _upper_bound(self, input_tokens: int) -> float:
        pin, pout = PRICES_USD_PER_MTOK[self.model]
        return (input_tokens * pin + self.max_output_tokens * pout) / 1e6 * 1.25

    def _cost(self, usage: dict | None) -> float | None:
        if not usage or "input_tokens" not in usage:
            return None
        pin, pout = PRICES_USD_PER_MTOK[self.model]
        return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout) / 1e6

    # ---------- public capabilities
    def observe_video(self, *, video: Path, question: str, schema: dict, schema_name: str,
                      fps: float, duration_s: float, purpose: str) -> CallResult:
        est_tokens = int(duration_s * fps * VIDEO_TOKENS_PER_FRAME_EST) + PROMPT_TOKENS_EST
        try:
            res_id = self.budget.reserve(run_id=self.run_id, provider="meta", model=self.model,
                                         amount_usd=self._upper_bound(est_tokens), purpose=purpose)
        except BudgetExhausted as exc:
            return self._skipped(purpose, str(exc))
        file_id = None
        try:
            file_id = self._upload(video)
        except Exception as exc:  # upload is free; no billing to settle beyond reservation release
            self.budget.settle(res_id, cost_usd=0.0, cost_basis="no_model_call(upload_failed)", usage=None,
                               remote_request_id=None, outcome="http_error")
            return self._failed(purpose, "http_error", f"upload failed: {type(exc).__name__}: {exc}")
        try:
            content = [{"type": "input_text", "text": question},
                       {"type": "input_video", "file_id": file_id, "fps": fps}]
            return self._respond(content, schema, schema_name, purpose, res_id)
        finally:
            try:
                self.client.delete(f"{self.base_url}/files/{file_id}", headers=self._h, timeout=60)
            except Exception:
                pass

    def observe_images(self, *, images: list[tuple[str, Path]], question: str, schema: dict,
                       schema_name: str, purpose: str) -> CallResult:
        est_tokens = len(images) * IMAGE_TOKENS_EST + PROMPT_TOKENS_EST
        try:
            res_id = self.budget.reserve(run_id=self.run_id, provider="meta", model=self.model,
                                         amount_usd=self._upper_bound(est_tokens), purpose=purpose)
        except BudgetExhausted as exc:
            return self._skipped(purpose, str(exc))
        content: list[dict] = [{"type": "input_text", "text": question}]
        for label, path in images:
            b64 = base64.b64encode(path.read_bytes()).decode()
            content.append({"type": "input_text", "text": f"Image {label}:"})
            content.append({"type": "input_image", "image_url": f"data:image/png;base64,{b64}"})
        return self._respond(content, schema, schema_name, purpose, res_id)

    # ---------- internals
    def _upload(self, path: Path) -> str:
        with open(path, "rb") as fh:
            r = self.client.post(f"{self.base_url}/files", headers=self._h, data={"purpose": "user_data"},
                                 files={"file": (path.name, fh, "video/mp4")}, timeout=600)
        r.raise_for_status()
        return r.json()["id"]

    def _respond(self, content: list[dict], schema: dict, schema_name: str, purpose: str,
                 res_id: str) -> CallResult:
        body = {"model": self.model, "max_output_tokens": self.max_output_tokens,
                "reasoning": {"effort": self.reasoning_effort}, "store": False,
                "input": [{"type": "message", "role": "user", "content": content}],
                "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True,
                                    "schema": schema}}}
        digest = _digest_without_media(body)
        trace = {"trace_id": f"tr-{uuid.uuid4().hex[:12]}", "provider": "meta", "model": self.model,
                 "endpoint": "/v1/responses", "purpose": purpose, "request_digest": digest,
                 "reasoning_effort": self.reasoning_effort, "max_output_tokens": self.max_output_tokens,
                 "media": [p.get("type") for p in content if p.get("type") != "input_text"],
                 "question": next((p["text"] for p in content if p.get("type") == "input_text"), None)}
        last_exc = None
        for attempt in range(1, self.max_attempts + 1):
            t0 = time.monotonic()
            try:
                r = self.client.post(f"{self.base_url}/responses", headers=self._h, json=body)
            except httpx.TimeoutException as exc:
                # Ambiguous: the provider may still bill. Do not retry a chargeable call blindly.
                trace.update(latency_s=round(time.monotonic() - t0, 2), http_status=None, attempt=attempt)
                self.budget.settle(res_id, cost_usd=None, cost_basis="unknown(timeout; reservation held)",
                                   usage=None, remote_request_id=None, outcome="timeout")
                return self._finish(trace, "timeout", None, None, f"timeout: {exc}")
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(1 + random.random())
                continue
            dt = round(time.monotonic() - t0, 2)
            trace.update(latency_s=dt, http_status=r.status_code, attempt=attempt)
            if r.status_code in (429, 500, 502, 503) and attempt < self.max_attempts:
                time.sleep(2 * attempt + random.random())
                continue
            try:
                data = r.json()
            except ValueError:
                data = {}
            usage = data.get("usage")
            cost = self._cost(usage)
            remote = data.get("id")
            if r.status_code != 200:
                self.budget.settle(res_id, cost_usd=cost if cost is not None else 0.0,
                                   cost_basis="usage*list_price" if cost is not None else "http_error_no_usage",
                                   usage=usage, remote_request_id=remote, outcome="http_error")
                err = (data.get("error") or {}) if isinstance(data, dict) else {}
                msg = err.get("message") if isinstance(err, dict) else str(err)
                return self._finish(trace, "http_error", usage, cost, f"HTTP {r.status_code}: {msg or r.text[:300]}",
                                    remote)
            self.budget.settle(res_id, cost_usd=cost, cost_basis="usage*list_price" if cost is not None
                               else "unknown(no usage)", usage=usage, remote_request_id=remote, outcome="ok")
            if data.get("status") != "completed":
                return self._finish(trace, "incomplete", usage, cost,
                                    f"status={data.get('status')} details={data.get('incomplete_details')}", remote)
            text = "".join(part.get("text", "") for item in data.get("output", [])
                           for part in (item.get("content") or []) if part.get("type") == "output_text")
            refusal = any(part.get("type") == "refusal" for item in data.get("output", [])
                          for part in (item.get("content") or []))
            if refusal:
                return self._finish(trace, "refused", usage, cost, "model refusal", remote)
            try:
                def invalid_constant(value):
                    raise ValueError("non-finite JSON number")
                def finite_float(value):
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("non-finite JSON number")
                    return number
                parsed = json.loads(text, parse_constant=invalid_constant, parse_float=finite_float)
                if not isinstance(parsed, dict):
                    raise ValueError("observation output must be an object")
                Draft202012Validator(schema).validate(parsed)
            except (ValueError, ValidationError, SchemaError):
                return self._finish(trace, "invalid_output", usage, cost,
                                    "output does not satisfy the requested JSON object schema", remote)
            trace["raw_output"] = parsed
            return self._finish(trace, "ok", usage, cost, None, remote, parsed)
        self.budget.settle(res_id, cost_usd=0.0, cost_basis="no_response(connection_error)", usage=None,
                           remote_request_id=None, outcome="http_error")
        return self._finish(trace, "http_error", None, None, f"connection error: {last_exc}")

    def _finish(self, trace: dict, outcome: str, usage, cost, error, remote=None, parsed=None) -> CallResult:
        trace.update(outcome=outcome, usage=usage, cost_usd=cost,
                     cost_basis="usage*list_price" if cost is not None else "unknown",
                     remote_request_id=remote, error=error)
        self.traces.append(trace)
        return CallResult(ok=outcome == "ok", parsed=parsed, trace=trace, outcome=outcome)

    def _skipped(self, purpose: str, why: str) -> CallResult:
        trace = {"trace_id": f"tr-{uuid.uuid4().hex[:12]}", "provider": "meta", "model": self.model,
                 "endpoint": "/v1/responses", "purpose": purpose, "http_status": None, "latency_s": 0,
                 "usage": None, "cost_usd": 0.0, "cost_basis": "not_called", "outcome": "budget_exhausted",
                 "error": why, "remote_request_id": None}
        self.traces.append(trace)
        return CallResult(ok=False, parsed=None, trace=trace, outcome="budget_exhausted")

    def _failed(self, purpose: str, outcome: str, why: str) -> CallResult:
        trace = {"trace_id": f"tr-{uuid.uuid4().hex[:12]}", "provider": "meta", "model": self.model,
                 "endpoint": "/v1/files", "purpose": purpose, "http_status": None, "latency_s": 0,
                 "usage": None, "cost_usd": 0.0, "cost_basis": "not_called", "outcome": outcome,
                 "error": why, "remote_request_id": None}
        self.traces.append(trace)
        return CallResult(ok=False, parsed=None, trace=trace, outcome=outcome)


def _digest_without_media(body: dict) -> str:
    def strip(o):
        if isinstance(o, dict):
            return {k: ("<media>" if k in ("image_url", "file_id") else strip(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    return hashlib.sha256(json.dumps(strip(body), sort_keys=True).encode()).hexdigest()
