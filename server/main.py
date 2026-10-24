"""HTTP API + static frontend. Run locally: uvicorn server.main:app --reload"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import sys
import threading
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, qloo, survey
from .examples import EXAMPLES, PRESETS
from .mcp_server import http_app, mcp

mcp_app = http_app()
MAX_AUDIENCES = 8


# ---- memo that never remembers a degraded result ------------------------------------------------------
class Memo:
    """Process-local memo for whole responses. A result built while any Qloo call failed is returned but not stored,
    so a brief rate limit cannot pin 'not in Qloo' on a reference for the rest of the process."""

    def __init__(self, maxsize: int):
        self.maxsize, self.data, self.lock = maxsize, OrderedDict(), threading.Lock()

    def get_or(self, key, fn):
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        calls = qloo.start_ledger()
        out = fn()
        out["ledger"] = _ledger_summary(calls)
        body = json.dumps(out)
        if not qloo.degraded():
            with self.lock:
                self.data[key] = body
                while len(self.data) > self.maxsize:
                    self.data.popitem(last=False)
        return body

    def clear(self):
        with self.lock:
            self.data.clear()


CHECKS, SWAPS, MATRICES, GUESSES, STANDINS, LOCALISED, LOCALISED_ALL = (Memo(n) for n in (256, 256, 128, 128, 128, 128, 64))
MEMOS = (CHECKS, SWAPS, MATRICES, GUESSES, STANDINS, LOCALISED, LOCALISED_ALL)


def _aud_key(auds) -> str:
    return json.dumps([{"age": a.age, "gender": a.gender, "location": a.location, "name": a.name} for a in auds], sort_keys=True)


def _check_body(text: str, a: pipeline.Audience, swaps: bool) -> str:
    return CHECKS.get_or(("check", text, a.age, a.gender, a.location, swaps), lambda: pipeline.check(text, a, swaps=swaps))


def _swaps_body(text: str, a: pipeline.Audience) -> str:
    """Stand-ins are computed from the server's own scored check (never from client-sent references), so the prewarm
    and a browser request share one cache entry."""
    def run():
        first = json.loads(_check_body(text, a, False))
        return {"references": pipeline.swaps_for(text, a, first["references"])}

    return SWAPS.get_or(("swaps", text, a.age, a.gender, a.location), run)


def _matrix_body(text: str, auds: list[pipeline.Audience]) -> str:
    return MATRICES.get_or(("matrix", text, _aud_key(auds)), lambda: pipeline.matrix(text, auds))


def _prewarm_examples():
    """Run the bundled examples once per process so a judge's first click is instant and the Qloo cache is populated."""
    if not os.environ.get("QLOO_API_KEY") and not os.environ.get("QLOO_MOCK"):
        return
    for ex in EXAMPLES:
        try:
            a = pipeline.Audience(**{k: v for k, v in ex["audience"].items() if k in ("age", "gender", "location")})
            _check_body(ex["text"], a, False)
            _swaps_body(ex["text"], a)
            if ex.get("matrix"):
                auds = [pipeline.Audience(x.get("age"), x.get("gender"), x.get("location"), x.get("name")) for x in ex["matrix"]]
                _matrix_body(ex["text"], auds)
        except Exception as ex_:  # pre-warming is best effort
            print("prewarm failed:", type(ex_).__name__, ex_, flush=True)
    print("prewarm done", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if sys.platform == "darwin":  # the first-call stall is a macOS proxy-discovery issue; Linux containers skip the warm-up
        pipeline.llm.warm()
    threading.Thread(target=_prewarm_examples, daemon=True).start()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Will It Land", version="0.3.0", lifespan=lifespan)


@app.middleware("http")
async def mcp_without_slash(request: Request, call_next):
    if request.scope["path"] == "/mcp":
        request.scope["path"] = "/mcp/"
    return await call_next(request)


app.mount("/mcp", mcp_app)


# ---- abuse guard: the public endpoints spend LLM and Qloo quota -------------------------------------
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()
RATE = int(os.environ.get("RATE_PER_10MIN", "60"))


def _guard(request: Request) -> None:
    # ponytail: in-process sliding window keyed on the address the platform supplies (headers are spoofable);
    # fine for the single warm container this app runs in, use a shared store if it is ever scaled out
    ip = request.client.host if request.client else "?"
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
        "cache": sum(c["source"] in ("cache", "stale") for c in calls),
        "mock": sum(c["source"] == "mock" for c in calls),
        "errors": sum(c["source"] == "error" for c in calls),
        "by_endpoint": dict(by_endpoint),
        "calls": calls[:400],
    }


# ---- models --------------------------------------------------------------------------------------------


def _audience(age=None, gender=None, location=None, name=None) -> pipeline.Audience:
    try:
        return pipeline.Audience(age, gender, location, name)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


class AudienceIn(BaseModel):
    age: str | None = None
    gender: str | None = None
    location: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=60)

    def to(self) -> pipeline.Audience:
        return _audience(self.age, self.gender, self.location, self.name)


class CheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    age: str | None = None
    gender: str | None = None
    location: str | None = Field(default=None, max_length=80)
    swaps: bool = True


class SwapsRequest(CheckRequest):
    references: list[dict] | None = Field(default=None, max_length=80)  # accepted for compatibility, ignored


class MatrixRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    audiences: list[AudienceIn] = Field(min_length=1, max_length=MAX_AUDIENCES)


class StandinRequest(MatrixRequest):
    ref_start: int


class LocaliseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    audience: AudienceIn


class ReportIn(BaseModel):
    kind: str = Field(pattern="^(check|matrix|localise|localise_all)$")
    payload: dict


def _run(fn, label: str):
    t0 = time.time()
    try:
        out = json.loads(fn())
    except qloo.QlooError as ex:
        raise HTTPException(502, str(ex))
    except HTTPException:
        raise
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    except Exception as ex:  # an LLM outage must read as a clear error, not a blank screen
        print(f"{label} failed: {type(ex).__name__}: {ex}", flush=True)
        raise HTTPException(503, "The language model did not answer in time. Please try again.")
    out["took_s"] = round(time.time() - t0, 1)
    led = out.get("ledger", {})
    print(f"{label} took={out['took_s']}s timings={out.get('timings')} qloo_calls={led.get('total')} errors={led.get('errors')}", flush=True)
    return out


# ---- endpoints --------------------------------------------------------------------------------------------


@app.get("/api/health")
def health():
    return {"ok": True, "qloo_key": bool(os.environ.get("QLOO_API_KEY")), "mock": bool(os.environ.get("QLOO_MOCK")), "llm": f"{pipeline.llm.PROVIDER}:{pipeline.llm.MODEL}", "model": pipeline.scoring.P.get("source")}


@app.get("/api/examples")
def examples():
    return EXAMPLES


@app.get("/api/presets")
def presets():
    return PRESETS


@app.get("/api/options")
def options():
    return {"ages": [{"value": a, "label": pipeline.AGE_LABELS[a]} for a in pipeline.AUDIENCE_AGES], "genders": ["male", "female"], "types": pipeline.TYPES, "max_audiences": MAX_AUDIENCES,
            "location_weight": pipeline.scoring.P.get("k_loc"), "calibrated": pipeline.scoring.P.get("calibrated")}


@app.post("/api/check")
def check(req: CheckRequest, request: Request):
    a = _audience(req.age, req.gender, req.location)
    _guard(request)
    return _run(lambda: _check_body(req.text, a, req.swaps), f"check {len(req.text)}ch [{a.label()}]")


@app.post("/api/swaps")
def swaps(req: SwapsRequest, request: Request):
    """Second phase of a check: stand-ins for the weak references. Split out so the UI shows scores first."""
    a = _audience(req.age, req.gender, req.location)
    return _run(lambda: _swaps_body(req.text, a), f"swaps [{a.label()}]")


@app.post("/api/matrix")
def matrix(req: MatrixRequest, request: Request):
    _guard(request)
    auds = [x.to() for x in req.audiences]
    return _run(lambda: _matrix_body(req.text, auds), f"matrix {len(req.text)}ch x{len(auds)}")


@app.post("/api/guesses")
def matrix_guesses(req: MatrixRequest, request: Request):
    """What the language model alone guesses for each reference x audience (no data). Fetched after the Qloo matrix paints."""
    auds = [x.to() for x in req.audiences]
    return _run(lambda: GUESSES.get_or(("guesses", req.text, _aud_key(auds)), lambda: {"guesses": pipeline.matrix_guesses(req.text, auds)}), f"guesses x{len(auds)}")


@app.post("/api/standin")
def standin(req: StandinRequest, request: Request):
    """One stand-in for every room: the candidate whose worst room scores highest."""
    _guard(request)
    auds = [x.to() for x in req.audiences]

    def run():
        refs = json.loads(_matrix_body(req.text, auds))["references"]
        return pipeline.common_standin(req.text, refs, req.ref_start, auds)

    return _run(lambda: STANDINS.get_or(("standin", req.text, _aud_key(auds), req.ref_start), run), f"standin x{len(auds)}")


@app.post("/api/localise_all")
def localise_all(req: MatrixRequest, request: Request):
    """Make it land in every room: one stand-in per weak reference, chosen so its worst room scores best."""
    _guard(request)
    auds = [x.to() for x in req.audiences]
    return _run(lambda: LOCALISED_ALL.get_or(("lall", req.text, _aud_key(auds)), lambda: pipeline.localise_all(req.text, auds)), f"localise_all x{len(auds)}")


@app.post("/api/localise")
def localise(req: LocaliseRequest, request: Request):
    _guard(request)
    a = req.audience.to()
    return _run(lambda: LOCALISED.get_or(("loc", req.text, _aud_key([a])), lambda: pipeline.localise(req.text, a)), f"localise [{a.label()}]")


# ---- recognition survey (anonymous ground truth for the youngest room) ------------------------------------


class SurveyIn(BaseModel):
    age: str
    city: str | None = Field(default=None, max_length=40)
    answers: dict[str, bool]


@app.get("/api/survey")
def survey_items():
    return {"items": survey.items(), "ages": survey.AGES}


@app.post("/api/survey")
def survey_submit(s: SurveyIn, request: Request):
    _guard(request)
    try:
        n = survey.save(s.age, s.city or "", s.answers)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    threading.Thread(target=_persist_volume, daemon=True).start()
    return {"ok": True, "responses": n}


@app.get("/api/survey/export")
def survey_export(token: str = ""):
    """Aggregate export for eval/survey_report.py; protected by a token from the environment."""
    want = os.environ.get("SURVEY_TOKEN")
    if not want or token != want:
        raise HTTPException(404, "not found")
    return {"items": survey.items(), "responses": survey.responses()}


# ---- shareable reports ------------------------------------------------------------------------------------
_reports_lock = threading.Lock()


def _reports() -> sqlite3.Connection:
    path = os.path.join(os.path.dirname(os.path.abspath(qloo.CACHE_PATH)), "reports.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("create table if not exists r (id text primary key, kind text, payload text, t real)")
    return db


def _persist_volume():
    """On Modal, flush the cache/report volume so a saved report survives a container restart (best effort)."""
    name = os.environ.get("WIL_VOLUME")
    if not name:
        return
    try:
        import modal

        modal.Volume.from_name(name).commit()
    except Exception as ex:
        print("volume commit skipped:", type(ex).__name__, ex, flush=True)


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
    threading.Thread(target=_persist_volume, daemon=True).start()
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


DIST = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "web", "dist"))
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.realpath(os.path.join(DIST, path))
        ok = bool(path) and f.startswith(DIST + os.sep) and os.path.isfile(f)  # never serve anything outside web/dist
        return FileResponse(f if ok else os.path.join(DIST, "index.html"))
