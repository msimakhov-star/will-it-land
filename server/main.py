"""HTTP API + static frontend. Run locally: uvicorn server.main:app --reload"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, qloo
from .examples import EXAMPLES, PRESETS
from .mcp_server import http_app, mcp

mcp_app = http_app()
MAX_AUDIENCES = 8


def _prewarm_examples():
    """Run the bundled examples once per process so a judge's first click is instant and the Qloo cache is populated."""
    if not os.environ.get("QLOO_API_KEY") and not os.environ.get("QLOO_MOCK"):
        return
    for ex in EXAMPLES:
        try:
            a = ex["audience"]
            first = json.loads(_check_cached(ex["text"], a["age"], a["gender"], a["location"], False))
            _swaps_cached(ex["text"], a["age"], a["gender"], a["location"], json.dumps(first["references"], sort_keys=True))
            if ex.get("matrix"):
                _matrix_cached(ex["text"], json.dumps(ex["matrix"], sort_keys=True))
        except Exception as ex_:  # pre-warming is best effort
            print("prewarm failed:", ex_, flush=True)
    print("prewarm done", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    pipeline.llm.warm()
    threading.Thread(target=_prewarm_examples, daemon=True).start()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Will It Land", version="0.2.0", lifespan=lifespan)
app.mount("/mcp", mcp_app)


# ---- abuse guard: the public endpoints spend LLM and Qloo quota -------------------------------------
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()
RATE = int(os.environ.get("RATE_PER_10MIN", "40"))


def _guard(request: Request) -> None:
    # ponytail: in-process sliding window per client IP; fine for one warm container, use a shared store if scaled out
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    now = time.time()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= RATE:
            raise HTTPException(429, "Too many checks from this address in 10 minutes. Try again shortly.")
        q.append(now)


def _ledger_summary(calls: list) -> dict:
    by_endpoint: dict[str, int] = defaultdict(int)
    for c in calls:
        by_endpoint[c["endpoint"]] += 1
    return {
        "total": len(calls),
        "live": sum(c["source"] == "live" for c in calls),
        "cache": sum(c["source"] == "cache" for c in calls),
        "mock": sum(c["source"] == "mock" for c in calls),
        "by_endpoint": dict(by_endpoint),
        "calls": calls[:400],
    }


# ---- models --------------------------------------------------------------------------------------------


class AudienceIn(BaseModel):
    age: str | None = None
    gender: str | None = None
    location: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=60)

    def to(self) -> pipeline.Audience:
        if self.age and self.age not in pipeline.AUDIENCE_AGES:
            raise HTTPException(400, "bad age bucket")
        if self.gender and self.gender not in ("male", "female"):
            raise HTTPException(400, "bad gender")
        return pipeline.Audience(self.age or None, self.gender or None, (self.location or "").strip() or None, (self.name or "").strip() or None)


class CheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    age: str | None = None
    gender: str | None = None
    location: str | None = Field(default=None, max_length=80)
    swaps: bool = True


class SwapsRequest(CheckRequest):
    references: list[dict] = Field(max_length=80)


class MatrixRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    audiences: list[AudienceIn] = Field(min_length=1, max_length=MAX_AUDIENCES)


class LocaliseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    audience: AudienceIn


class ReportIn(BaseModel):
    kind: str = Field(pattern="^(check|matrix|localise)$")
    payload: dict


# ---- memoised work (the Qloo layer has its own on-disk cache underneath) --------------------------------


def _with_ledger(fn):
    calls = qloo.start_ledger()
    out = fn()
    out["ledger"] = _ledger_summary(calls)
    return out


@lru_cache(maxsize=256)
def _check_cached(text: str, age: str | None, gender: str | None, location: str | None, swaps: bool) -> str:
    return json.dumps(_with_ledger(lambda: pipeline.check(text, pipeline.Audience(age, gender, location), swaps=swaps)))


@lru_cache(maxsize=256)
def _swaps_cached(text: str, age: str | None, gender: str | None, location: str | None, references: str) -> str:
    return json.dumps(_with_ledger(lambda: {"references": pipeline.swaps_for(text, pipeline.Audience(age, gender, location), json.loads(references))}))


@lru_cache(maxsize=128)
def _matrix_cached(text: str, audiences: str) -> str:
    auds = [pipeline.Audience(a.get("age"), a.get("gender"), a.get("location"), a.get("name")) for a in json.loads(audiences)]
    return json.dumps(_with_ledger(lambda: pipeline.matrix(text, auds)))


@lru_cache(maxsize=128)
def _localise_cached(text: str, audience: str) -> str:
    a = json.loads(audience)
    return json.dumps(_with_ledger(lambda: pipeline.localise(text, pipeline.Audience(a.get("age"), a.get("gender"), a.get("location"), a.get("name")))))


def _run(fn, label: str):
    t0 = time.time()
    try:
        out = json.loads(fn())
    except qloo.QlooError as ex:
        raise HTTPException(502, str(ex))
    except HTTPException:
        raise
    except Exception as ex:  # an LLM outage must read as a clear error, not a blank screen
        print(f"{label} failed: {type(ex).__name__}: {ex}", flush=True)
        raise HTTPException(503, "The language model did not answer in time. Please try again.")
    out["took_s"] = round(time.time() - t0, 1)
    print(f"{label} took={out['took_s']}s timings={out.get('timings')} qloo_calls={out.get('ledger', {}).get('total')}", flush=True)
    return out


# ---- endpoints --------------------------------------------------------------------------------------------


@app.get("/api/health")
def health():
    return {"ok": True, "qloo_key": bool(os.environ.get("QLOO_API_KEY")), "mock": bool(os.environ.get("QLOO_MOCK")), "llm": f"{pipeline.llm.PROVIDER}:{pipeline.llm.MODEL}"}


@app.get("/api/examples")
def examples():
    return EXAMPLES


@app.get("/api/presets")
def presets():
    return PRESETS


@app.get("/api/options")
def options():
    return {"ages": [{"value": a, "label": pipeline.AGE_LABELS[a]} for a in pipeline.AUDIENCE_AGES], "genders": ["male", "female"], "types": pipeline.TYPES, "max_audiences": MAX_AUDIENCES}


@app.post("/api/check")
def check(req: CheckRequest, request: Request):
    a = AudienceIn(age=req.age, gender=req.gender, location=req.location).to()
    _guard(request)
    return _run(lambda: _check_cached(req.text, a.age, a.gender, a.location, req.swaps), f"check {len(req.text)}ch [{a.label()}]")


@app.post("/api/swaps")
def swaps(req: SwapsRequest, request: Request):
    """Second phase of a check: stand-ins for the weak references. Split out so the UI shows scores first."""
    a = AudienceIn(age=req.age, gender=req.gender, location=req.location).to()
    return _run(lambda: _swaps_cached(req.text, a.age, a.gender, a.location, json.dumps(req.references, sort_keys=True)), f"swaps [{a.label()}]")


@app.post("/api/matrix")
def matrix(req: MatrixRequest, request: Request):
    _guard(request)
    auds = [x.to() for x in req.audiences]
    key = json.dumps([{"age": a.age, "gender": a.gender, "location": a.location, "name": a.name} for a in auds], sort_keys=True)
    return _run(lambda: _matrix_cached(req.text, key), f"matrix {len(req.text)}ch x{len(auds)}")


@app.post("/api/localise")
def localise(req: LocaliseRequest, request: Request):
    _guard(request)
    a = req.audience.to()
    key = json.dumps({"age": a.age, "gender": a.gender, "location": a.location, "name": a.name}, sort_keys=True)
    return _run(lambda: _localise_cached(req.text, key), f"localise [{a.label()}]")


# ---- shareable reports ------------------------------------------------------------------------------------
_reports_lock = threading.Lock()


def _reports() -> sqlite3.Connection:
    path = os.path.join(os.path.dirname(os.path.abspath(qloo.CACHE_PATH)), "reports.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("create table if not exists r (id text primary key, kind text, payload text, t real)")
    return db


@app.post("/api/report")
def save_report(rep: ReportIn, request: Request):
    _guard(request)
    body = json.dumps(rep.payload)
    if len(body) > 2_000_000:
        raise HTTPException(413, "report too large")
    rid = secrets.token_urlsafe(6)
    with _reports_lock:
        db = _reports()
        db.execute("insert into r values (?,?,?,?)", (rid, rep.kind, body, time.time()))
        db.commit()
        db.close()
    return {"id": rid, "url": f"/r/{rid}"}


@app.get("/api/report/{rid}")
def get_report(rid: str):
    with _reports_lock:
        db = _reports()
        row = db.execute("select kind, payload, t from r where id=?", (rid,)).fetchone()
        db.close()
    if not row:
        raise HTTPException(404, "report not found")
    return {"id": rid, "kind": row[0], "payload": json.loads(row[1]), "created": row[2]}


DIST = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.join(DIST, path)
        return FileResponse(f if path and os.path.isfile(f) else os.path.join(DIST, "index.html"))
