"""HTTP API + static frontend. Run locally: uvicorn server.main:app --reload"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, qloo
from .examples import EXAMPLES

app = FastAPI(title="Will It Land", version="0.1.0")


class CheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    age: str | None = None
    gender: str | None = None
    location: str | None = None
    swaps: bool = True


@app.get("/api/health")
def health():
    return {"ok": True, "qloo_key": bool(os.environ.get("QLOO_API_KEY")), "llm": f"{pipeline.llm.PROVIDER}:{pipeline.llm.MODEL}"}


@app.get("/api/examples")
def examples():
    return EXAMPLES


@app.get("/api/options")
def options():
    return {"ages": pipeline.AUDIENCE_AGES, "genders": ["male", "female"], "types": pipeline.TYPES}


@app.post("/api/check")
def check(req: CheckRequest):
    if req.age and req.age not in pipeline.AUDIENCE_AGES:
        raise HTTPException(400, "bad age bucket")
    if req.gender and req.gender not in ("male", "female"):
        raise HTTPException(400, "bad gender")
    t0 = time.time()
    try:
        out = pipeline.check(req.text, pipeline.Audience(req.age, req.gender, (req.location or "").strip() or None), swaps=req.swaps)
    except qloo.QlooError as ex:
        raise HTTPException(502, str(ex))
    out["took_s"] = round(time.time() - t0, 1)
    return out


DIST = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.join(DIST, path)
        return FileResponse(f if path and os.path.isfile(f) else os.path.join(DIST, "index.html"))
