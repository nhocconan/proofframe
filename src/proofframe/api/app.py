"""FastAPI app implementing docs/API_CONTRACT.md. Sync routes (threadpool) over SQLAlchemy."""
from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from proofframe_contracts.models import Contract, fingerprint

from .. import jobs
from ..budget_pg import PgBudget
from ..config import Settings
from ..db import (AssetVersion, Blob, ContractRow, Envelope, Run, get_engine, init_db,
                  make_sessionmaker)
from ..storage import LocalStore
from ..verify.autocontract import build_auto_contract

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CATEGORIES = ("video", "audio", "image", "document", "composition")
_FORMAT_MIME = {"mov": "video/mp4", "matroska": "video/webm", "webm": "video/webm", "avi": "video/x-msvideo",
                "wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac", "ogg": "audio/ogg",
                "png_pipe": "image/png", "jpeg_pipe": "image/jpeg", "webp_pipe": "image/webp",
                "gif": "image/gif"}

CAPABILITIES: dict[str, Any] = {
    "source": "docs/CAPABILITY_PROBES.md (Gate 0, 2026-10-27; estimated cost, not billed)",
    "models": {
        "muse-spark-1.3": {"endpoint": "/v1/responses", "inputs": ["text", "image", "video(file_id,fps)"],
                           "structured_output": "json_schema strict", "timestamps": "hints only",
                           "video_tokens_per_second_at_fps1_640px": 117},
        "sam-3.1": {"endpoint": "stream", "inputs": ["video"], "billing": "native 24 fps; downsample first",
                    "status": "unverified negative on blue-jacket concept"},
        "muse-voice-transcribe-1.0": {"endpoint": "/asr/transcribe", "granularity": "turn-level",
                                      "word_timestamps": False},
    },
    # Vendor data handling as read from vendor documents (URL + date). Not legal advice; re-read before a client.
    "data_handling": {
        "meta_muse_spark_standard": {
            "training": "none: \"In Standard mode, your content ... is not used to train Meta models.\"",
            "retention": "uploaded files persist until deleted (\"don't expire\"); ProofFrame sends DELETE "
                         "/v1/files/{file_id} after every video call and records the outcome in the trace "
                         "(`upload_deleted`); request/response log retention: not found in the docs",
            "sources": ["https://dev.meta.ai/docs/models", "https://dev.meta.ai/docs/file-handling"],
            "read_on": "2026-10-31"},
        "meta_muse_voice_transcribe": {
            "training": "none in Standard mode; zero data retention documented for this endpoint only",
            "sources": ["https://dev.meta.ai/docs/speech-to-text", "https://dev.meta.ai/docs/pricing-rate-limits"],
            "read_on": "2026-10-31"},
        "elevenlabs_scribe_v2": {
            "training": "non-Enterprise: may train unless the workspace toggle \"Improve the models for everyone\" "
                        "is off (Enterprise: not trained by default); this deployment has not confirmed the toggle",
            "retention": "zero-retention mode (enable_logging=false) is Enterprise-only; API retention period "
                         "not found in the docs. Optional provider: disabled when ELEVENLABS_API_KEY is unset, "
                         "then dialogue checks run on Meta only with an explicit single-provider limitation",
            "sources": ["https://elevenlabs.io/docs/capabilities/speech-to-text",
                        "https://elevenlabs.io/docs/api-reference/speech-to-text/convert",
                        "https://elevenlabs.io/terms-of-use", "https://elevenlabs.io/privacy-policy"],
            "read_on": "2026-10-31"},
    },
    "not_established": ["detector accuracy", "timestamp precision", "SAM recall", "ASR accuracy on real speech"],
}


def probe_media(path: Path) -> dict[str, Any]:
    cmd = ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries",
           "format=duration,format_name:stream=codec_type,width,height", "-of", "json", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60, check=True, text=True).stdout
        data = json.loads(out)
    except (subprocess.SubprocessError, ValueError, OSError):
        raise HTTPException(422, "file is not readable media (ffprobe failed)")
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    if not streams:
        raise HTTPException(422, "file has no media streams")
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    try:
        duration_ms = int(round(float(fmt["duration"]) * 1000))
    except (KeyError, ValueError, TypeError):
        duration_ms = None
    if duration_ms is not None and duration_ms <= 0:
        duration_ms = None
    return {"duration_ms": duration_ms, "width": video.get("width") if video else None,
            "height": video.get("height") if video else None,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "format_name": str(fmt.get("format_name", ""))}


def pick_mime(filename: str, format_name: str) -> str:
    first = format_name.split(",")[0]
    mime = _FORMAT_MIME.get(first)
    if mime is None:
        mime = mimetypes.guess_type(filename or "")[0]
    if mime and mime.split("/")[0] in ("video", "audio", "image") and "svg" not in mime:
        return mime
    return "application/octet-stream"  # never serve active content types


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    engine = get_engine(cfg.database_url)
    Session = make_sessionmaker(engine)
    store = LocalStore(cfg.data_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        last: Exception | None = None
        for _i in range(30):
            try:
                init_db(engine)
                break
            except Exception as e:  # db not ready yet
                last = e
                time.sleep(1)
        else:
            raise RuntimeError(f"database unavailable: {last}")
        yield

    app = FastAPI(title="ProofFrame API", version="0.1.0", lifespan=lifespan)
    app.state.settings, app.state.Session, app.state.store, app.state.engine = cfg, Session, store, engine

    def _check_token(token: str | None) -> None:
        if not cfg.api_token or not token or not hmac.compare_digest(token, cfg.api_token):
            raise HTTPException(401, "invalid or missing bearer token",
                                headers={"WWW-Authenticate": "Bearer"})

    def auth(authorization: str | None = Header(default=None)) -> str:
        scheme, _, tok = (authorization or "").partition(" ")
        _check_token(tok if scheme.lower() == "bearer" else None)
        return cfg.tenant_id

    def media_auth(request: Request, token: str | None = Query(default=None)) -> str:
        # ?token= is accepted ONLY here: browser <video> cannot send headers.
        header = request.headers.get("authorization")
        if header:
            scheme, _, tok = header.partition(" ")
            _check_token(tok if scheme.lower() == "bearer" else None)
        else:
            _check_token(token)
        return cfg.tenant_id

    # -- health / static --------------------------------------------------------------------
    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/v1/capabilities")
    def capabilities(_t: str = Depends(auth)):
        return CAPABILITIES

    @app.get("/v1/budget")
    def budget(_t: str = Depends(auth)):
        return PgBudget(engine, cfg).summary()

    # -- assets -----------------------------------------------------------------------------
    @app.post("/v1/assets")
    def upload_asset(file: UploadFile = File(...), asset_id: str = Form(...),
                     media_type: str = Form(...), tenant: str = Depends(auth)):
        if not _ID.match(asset_id):
            raise HTTPException(422, "invalid asset_id")
        if media_type not in _CATEGORIES:
            raise HTTPException(422, f"media_type must be one of {_CATEGORIES}")
        import hashlib
        tmp = store.tmp / f"up-{uuid.uuid4().hex}"
        h, size = hashlib.sha256(), 0
        try:
            with open(tmp, "wb") as out:
                while chunk := file.file.read(1 << 20):
                    size += len(chunk)
                    if size > cfg.max_upload_bytes:
                        raise HTTPException(413, "file exceeds 1 GiB cap")
                    h.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise HTTPException(422, "empty file")
            sha = h.hexdigest()
            with Session() as db:
                existing = db.scalar(select(AssetVersion).where(
                    AssetVersion.tenant_id == tenant, AssetVersion.asset_id == asset_id,
                    AssetVersion.sha256 == sha))
                if existing:
                    return JSONResponse(jobs.asset_dict(existing), status_code=200)
            info = probe_media(tmp)
            mime = pick_mime(file.filename or "", info["format_name"])
            store.put_tmp(tmp, sha, media_type=mime)
            with Session() as db, db.begin():
                db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                           {"k": f"{tenant}/{asset_id}"})
                existing = db.scalar(select(AssetVersion).where(
                    AssetVersion.tenant_id == tenant, AssetVersion.asset_id == asset_id,
                    AssetVersion.sha256 == sha))
                if existing:
                    return JSONResponse(jobs.asset_dict(existing), status_code=200)
                prev = db.scalar(select(AssetVersion.revision).where(
                    AssetVersion.tenant_id == tenant, AssetVersion.asset_id == asset_id
                ).order_by(AssetVersion.revision.desc()).limit(1)) or 0
                db.execute(pg_insert(Blob).values(tenant_id=tenant, sha256=sha, media_type=mime,
                                                  bytes=size).on_conflict_do_nothing())
                av = AssetVersion(tenant_id=tenant, asset_id=asset_id, revision=prev + 1, sha256=sha,
                                  media_type=media_type, mime=mime, bytes=size,
                                  duration_ms=info["duration_ms"], width=info["width"],
                                  height=info["height"], has_audio=info["has_audio"])
                db.add(av)
                db.flush()
                db.refresh(av)
                return JSONResponse(jobs.asset_dict(av), status_code=201)
        finally:
            if tmp.exists():
                tmp.unlink()

    @app.get("/v1/assets")
    def list_assets(tenant: str = Depends(auth)):
        with Session() as db:
            rows = db.scalars(select(AssetVersion).where(AssetVersion.tenant_id == tenant)
                              .order_by(AssetVersion.asset_id, AssetVersion.revision)).all()
            return [jobs.asset_dict(a) for a in rows]

    # -- media (Range) ----------------------------------------------------------------------
    def _parse_range(header: str, size: int) -> tuple[int, int] | None | str:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
        if not m or (m.group(1) == "" and m.group(2) == ""):
            return "bad"
        a, b = m.groups()
        if a == "":
            n = int(b)
            if n == 0:
                return "bad"
            return max(0, size - n), size - 1
        start = int(a)
        end = int(b) if b else size - 1
        if start >= size or end < start:
            return "bad"
        return start, min(end, size - 1)

    @app.api_route("/v1/media/{sha256}", methods=["GET", "HEAD"])
    def media(sha256: str, request: Request, tenant: str = Depends(media_auth)):
        if not _SHA.match(sha256):
            raise HTTPException(404, "not found")
        with Session() as db:
            blob = db.get(Blob, (tenant, sha256))
        path = store.path_for(sha256)
        if blob is None or not path.is_file():
            raise HTTPException(404, "not found")
        size = path.stat().st_size
        ctype = blob.media_type if "/" in (blob.media_type or "") else "application/octet-stream"
        headers = {"Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff",
                   "Cache-Control": "private, max-age=3600", "ETag": f'"{sha256}"'}
        rng = request.headers.get("range")
        status, start, end = 200, 0, size - 1
        if rng and rng.lower().startswith("bytes=") and "," not in rng:
            parsed = _parse_range(rng, size)
            if parsed == "bad":
                return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
            status, (start, end) = 206, parsed  # type: ignore[misc]
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        length = end - start + 1
        headers["Content-Length"] = str(length)
        if request.method == "HEAD":
            return Response(status_code=status, headers=headers, media_type=ctype)

        def body():
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                    yield chunk

        return StreamingResponse(body(), status_code=status, headers=headers, media_type=ctype)

    # -- contracts --------------------------------------------------------------------------
    @app.post("/v1/contracts")
    async def post_contract(request: Request, tenant: str = Depends(auth)):
        try:
            raw = await request.json()
            model = Contract.model_validate(raw)
        except (ValidationError, ValueError) as e:
            raise HTTPException(422, f"invalid contract: {str(e)[:2000]}")
        if model.tenant_id != tenant:
            raise HTTPException(403, "contract tenant_id does not match token tenant")
        sha = fingerprint(model)
        body = model.model_dump(mode="json")
        return _store_contract(tenant, model.contract_id, model.revision, sha, body)

    def _store_contract(tenant, cid, rev, sha, body):
        out = {"contract_id": cid, "revision": rev, "contract_sha256": sha}
        for attempt in (1, 2):
            with Session() as db:
                existing = db.scalar(select(ContractRow).where(
                    ContractRow.tenant_id == tenant, ContractRow.contract_id == cid,
                    ContractRow.revision == rev))
                if existing:
                    if existing.sha256 == sha:
                        return JSONResponse(out, status_code=200)
                    raise HTTPException(409, "contract_id+revision already exists with different content")
                try:
                    db.add(ContractRow(tenant_id=tenant, contract_id=cid, revision=rev,
                                       sha256=sha, body=body))
                    db.commit()
                    return JSONResponse(out, status_code=201)
                except IntegrityError:
                    db.rollback()
                    continue  # lost a race or identical sha under another id/revision
        raise HTTPException(409, "contract conflicts with an existing contract")

    @app.get("/v1/contracts/{sha}")
    def get_contract(sha: str, tenant: str = Depends(auth)):
        with Session() as db:
            row = db.scalar(select(ContractRow).where(
                ContractRow.tenant_id == tenant, ContractRow.sha256 == sha))
            if row is None:
                raise HTTPException(404, "not found")
            return row.body

    # -- verifications ----------------------------------------------------------------------
    @app.post("/v1/verifications")
    async def post_verification(request: Request, tenant: str = Depends(auth),
                                idempotency_key: str | None = Header(default=None)):
        if not idempotency_key or not _ID.match(idempotency_key):
            raise HTTPException(400, "Idempotency-Key header required (1-200 chars [A-Za-z0-9_.:-])")
        body = await request.json()
        video_only = isinstance(body, dict) and body.get("mode") == "video_only"
        try:
            assets = [{"asset_id": a["asset_id"], "sha256": a["sha256"]} for a in body["assets"]]
            if not assets or not all(_SHA.match(a["sha256"]) for a in assets):
                raise ValueError
            if video_only:
                if ("contract_sha256" in body or len(assets) not in (1, 2)
                        or len({a["asset_id"] for a in assets}) != len(assets)):
                    raise ValueError
                with Session() as db:
                    rows = [db.scalar(select(AssetVersion).where(
                        AssetVersion.tenant_id == tenant, AssetVersion.asset_id == a["asset_id"],
                        AssetVersion.sha256 == a["sha256"])) for a in assets]
                if any(r is None for r in rows):
                    raise ValueError
                videos = [r for r in rows if r.media_type == "video"]
                stills = [r for r in rows if r.media_type == "image"]
                if len(videos) != 1 or len(stills) != len(rows) - 1:
                    raise ValueError  # one video, plus at most one image reference
                av = videos[0]
                auto_body = build_auto_contract(av.asset_id, {
                    "sha256": av.sha256, "duration_ms": av.duration_ms, "has_audio": av.has_audio,
                }, tenant, reference=({"asset_id": stills[0].asset_id, "sha256": stills[0].sha256}
                                      if stills else None))
                auto_model = Contract.model_validate(auto_body)
                csha = fingerprint(auto_model)
                _store_contract(tenant, auto_model.contract_id, auto_model.revision, csha, auto_body)
            else:
                csha = body["contract_sha256"]
                if not _SHA.match(csha):
                    raise ValueError
            ids = body.get("assertion_ids")
            if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
                raise ValueError
            mode = body.get("run_mode", "live")
            prev = body.get("previous_run_id")
        except (KeyError, TypeError, ValueError):
            detail = ("body needs mode=video_only, one video asset and optionally one image reference "
                      "asset[{asset_id,sha256}], run_mode"
                      if video_only else
                      "body needs contract_sha256, assets[{asset_id,sha256}], run_mode")
            raise HTTPException(422, detail)
        try:
            with Session() as db, db.begin():
                run, created = jobs.create_run(
                    db, tenant=tenant, idempotency_key=idempotency_key, contract_sha256=csha,
                    assets=assets, assertion_ids=ids, run_mode=mode, previous_run_id=prev)
                out = jobs.run_dict(db, run)
        except jobs.Conflict as e:
            raise HTTPException(409, str(e))
        except jobs.Invalid as e:
            raise HTTPException(422, str(e))
        return JSONResponse(out, status_code=202 if created else 200)

    def _get_run(db, tenant, run_id) -> Run:
        run = db.scalar(select(Run).where(Run.tenant_id == tenant, Run.run_id == run_id))
        if run is None:
            raise HTTPException(404, "not found")
        return run

    @app.get("/v1/verifications")
    def list_runs(tenant: str = Depends(auth)):
        with Session() as db:
            runs = db.scalars(select(Run).where(Run.tenant_id == tenant)
                              .order_by(Run.created_at.desc())).all()
            return [jobs.run_dict(db, r) for r in runs]

    @app.get("/v1/verifications/{run_id}")
    def get_run(run_id: str, tenant: str = Depends(auth)):
        with Session() as db:
            return jobs.run_dict(db, _get_run(db, tenant, run_id))

    @app.get("/v1/verifications/{run_id}/report")
    def get_report(run_id: str, tenant: str = Depends(auth)):
        with Session() as db:
            run = _get_run(db, tenant, run_id)
            env = db.get(Envelope, run_id)
            if run.status != "succeeded" or env is None or env.tenant_id != tenant:
                raise HTTPException(404, f"no report (run status: {run.status})")
            return env.envelope

    @app.post("/v1/verifications/{run_id}/cancel")
    def cancel(run_id: str, tenant: str = Depends(auth)):
        with Session() as db, db.begin():
            run = _get_run(db, tenant, run_id)
            if run.status in ("succeeded", "failed", "cancelled"):
                raise HTTPException(409, f"run already {run.status}")
            run.cancel_requested = True
            if run.status == "queued":
                run.status = "cancelled"
                run.finished_at = func.now()
            db.flush()
            db.refresh(run)
            return jobs.run_dict(db, run)

    # -- repair -----------------------------------------------------------------------------
    @app.post("/v1/repair-requests")
    async def repair_request(request: Request, tenant: str = Depends(auth)):
        from ..repair import api_glue
        body = await request.json()
        rid = body.get("run_id") if isinstance(body, dict) else None
        if not isinstance(rid, str):
            raise HTTPException(422, "body needs run_id")
        return _glue(lambda db: api_glue.create_repair_request(db, cfg, tenant, rid), 201)

    @app.post("/v1/repair-receipts")
    async def repair_receipt(request: Request, tenant: str = Depends(auth),
                             idempotency_key: str | None = Header(default=None)):
        from ..repair import api_glue
        body = await request.json()
        return _glue(lambda db: api_glue.accept_repair_receipt(
            db, cfg, tenant, body, idempotency_key), 202)

    def _glue(fn, ok_status):
        try:
            with Session() as db, db.begin():
                out = fn(db)
            return JSONResponse(out, status_code=ok_status)
        except NotImplementedError as e:
            raise HTTPException(501, str(e))
        except LookupError as e:
            raise HTTPException(404, str(e))
        except jobs.Conflict as e:
            raise HTTPException(409, str(e))
        except (jobs.Invalid, ValueError) as e:
            raise HTTPException(422, str(e))

    return app


def __getattr__(name: str):  # lazy: uvicorn "proofframe.api.app:app" builds it on first access
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)


_app: FastAPI | None = None
