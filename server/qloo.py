"""Thin Qloo REST client with an on-disk cache. Every call the app makes to Qloo goes through here.

Base URL and key come from env (QLOO_BASE_URL, QLOO_API_KEY). Hackathon keys only work on
https://hackathon.api.qloo.com. Qloo silently ignores unknown params (200 + empty), so helpers
only build params the entity-type guide allows. Response parsing mirrors Qloo's own harness
(@qloo/qloo-harness 0.1.26): affinity may sit on the entity or under query, ids may be entity_id or id,
/search results may be a list or {entities: [...]}.

Every call is recorded in a per-request ledger (see `ledger()`), so the UI can show exactly which Qloo
calls produced a result.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE_URL = os.environ.get("QLOO_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/")
CACHE_PATH = os.environ.get("QLOO_CACHE", os.path.join(os.path.dirname(__file__), "..", "cache", "qloo.sqlite"))

INSIGHT_TYPES = ["artist", "book", "brand", "movie", "person", "place", "podcast", "tv_show", "videogame"]
AGE_BUCKETS = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]

_lock = threading.Lock()
_db: sqlite3.Connection | None = None
# One shared client: a fresh httpx.Client per call re-runs macOS proxy discovery and SSL setup, measured at
# 2 to 80 s on this machine. trust_env=False skips the proxy lookup entirely.
_http = httpx.Client(trust_env=False, timeout=30)
_ledger: contextvars.ContextVar[list | None] = contextvars.ContextVar("qloo_ledger", default=None)
# ponytail: one process-wide cap on concurrent live calls (threads x concurrent requests could otherwise fan out to 100+)
_live = threading.BoundedSemaphore(int(os.environ.get("QLOO_CONCURRENCY", "6")))


class QlooError(RuntimeError):
    pass


def start_ledger() -> list:
    """Begin recording Qloo calls for the current request; returns the (shared, appendable) list."""
    calls: list = []
    _ledger.set(calls)
    return calls


def degraded() -> bool:
    """True if any Qloo call in the current request failed. Results built from a degraded request must not be memoised,
    or a brief 429 would show as 'not in Qloo' until the process restarts."""
    return any(c["source"] == "error" for c in (_ledger.get() or []))


def pmap(fn, items, workers: int = 8) -> list:
    """ThreadPoolExecutor.map that carries the current context (so ledger entries from worker threads land in the request's ledger)."""
    items = list(items)
    if not items:
        return []
    with ThreadPoolExecutor(min(workers, len(items))) as ex:
        futs = [ex.submit(contextvars.copy_context().run, fn, x) for x in items]
        return [f.result() for f in futs]


def _cache() -> sqlite3.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(os.path.abspath(CACHE_PATH)), exist_ok=True)
        _db = sqlite3.connect(CACHE_PATH, check_same_thread=False, timeout=30)
        # WAL needs shared memory, which network volumes (Modal) do not reliably provide; use the default journal there
        _db.execute("pragma journal_mode=" + ("delete" if os.environ.get("MODAL_TASK_ID") else "wal"))
        _db.execute("create table if not exists q (k text primary key, v text, t real)")
    return _db


def _record(path: str, params: dict, source: str, ms: float) -> None:
    calls = _ledger.get()
    if calls is not None:
        calls.append({"endpoint": path, "params": params, "source": source, "ms": round(ms)})


def get(path: str, params: dict, ttl: float = 30 * 86400) -> dict:
    """GET a Qloo endpoint. Lists become comma-joined strings. Cached by (path, params)."""
    t0 = time.time()
    clean = {k: (",".join(map(str, v)) if isinstance(v, (list, tuple)) else v) for k, v in params.items() if v not in (None, "", [], ())}
    key = hashlib.sha1((path + json.dumps(clean, sort_keys=True)).encode()).hexdigest()
    with _lock:
        row = _cache().execute("select v, t from q where k=?", (key,)).fetchone()
    if row and time.time() - row[1] < ttl:
        _record(path, clean, "cache", (time.time() - t0) * 1000)
        return json.loads(row[0])
    if os.environ.get("QLOO_MOCK"):
        from . import mock

        try:
            data = mock.respond(path, clean)
        except QlooError as ex:  # mirror the live path: a /search miss is an empty answer, anything else is a recorded error
            if path == "/search" and "no result" in str(ex).lower():
                _record(path, clean, "mock", (time.time() - t0) * 1000)
                return {"results": []}
            _record(path, clean, "error", (time.time() - t0) * 1000)
            raise
        _record(path, clean, "mock", (time.time() - t0) * 1000)
        return data
    api_key = os.environ.get("QLOO_API_KEY")
    if not api_key:
        _record(path, clean, "error", 0)
        raise QlooError("QLOO_API_KEY is not set")
    try:
        data = _fetch(path, clean, api_key)
    except QlooError:
        if row:  # stale-on-error: an expired cached answer beats a failed demo
            _record(path, clean, "stale", (time.time() - t0) * 1000)
            return json.loads(row[0])
        _record(path, clean, "error", (time.time() - t0) * 1000)
        raise
    with _lock:
        _cache().execute("insert or replace into q values (?,?,?)", (key, json.dumps(data), time.time()))
        _cache().commit()
    _record(path, clean, "live", (time.time() - t0) * 1000)
    return data


def _fetch(path: str, clean: dict, api_key: str) -> dict:
    r = None
    for attempt in range(3):
        try:
            with _live:
                r = _http.get(BASE_URL + path, params=clean, headers={"X-Api-Key": api_key})
        except httpx.HTTPError as ex:
            if attempt == 2:
                raise QlooError(f"Qloo unreachable: {type(ex).__name__}") from ex
            time.sleep(1.0 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:  # bounded backoff, as the kit's API_ACCESS.md asks
            retry = r.headers.get("retry-after")
            time.sleep(min(float(retry), 5.0) if retry and retry.replace(".", "", 1).isdigit() else 1.5 * (attempt + 1))
            continue
        break
    if r.status_code == 404 and path == "/search" and "no result" in r.text.lower():
        return {"results": []}  # documented: /search answers 404 "No results" for a miss; cache it as empty
    if r.status_code == 401:
        raise QlooError("Qloo rejected the key (401). Check QLOO_API_KEY and that QLOO_BASE_URL is the hackathon host.")
    if r.status_code == 429:
        raise QlooError("Qloo rate limit (429). Try again shortly.")
    if r.status_code >= 400:
        raise QlooError(f"Qloo {r.status_code}: {r.text[:200]}")
    return r.json()


# ---- response helpers (field fallbacks copied from Qloo's harness) -------------------------------


def eid(e: dict) -> str | None:
    return e.get("entity_id") or e.get("id")


def affinity(e: dict) -> float | None:
    v = e.get("affinity")
    if v is None:
        v = (e.get("query") or {}).get("affinity")
    return float(v) if isinstance(v, (int, float)) else None


def _entities(data: dict) -> list[dict]:
    res = data.get("results")
    if isinstance(res, list):
        return res
    return (res or {}).get("entities", []) or []


# ---- helpers: one per API capability the product uses ----------------------------------------


def search(query: str, types: list[str] | None = None, take: int = 8) -> list[dict]:
    """Resolve a name to candidate entities. Returns entity dicts (name, entity_id, types, popularity, properties...)."""
    params = {"query": query, "take": take}
    if types:
        params["types"] = [t if t.startswith("urn:") else f"urn:entity:{t}" for t in types]
    out = _entities(get("/search", params))
    for e in out:
        if "entity_id" not in e and e.get("id"):
            e["entity_id"] = e["id"]
    return out


def demographics(entity_ids: list[str]) -> dict[str, dict]:
    """Age and gender affinity per entity. Returns {entity_id: {"age": {...}, "gender": {...}}}. Values are
    relative over/under-indexing around 0 (sample range seen: -0.5 to 0.7). Batched; any id missing from a
    batched response is fetched on its own (Qloo's harness always sends one entity per call)."""
    out: dict[str, dict] = {}
    ids = list(dict.fromkeys(i for i in entity_ids if i))

    def rows(batch):
        data = get("/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": batch})
        return (data.get("results", {}) or {}).get("demographics", []) or []

    for i in range(0, len(ids), 10):
        for row in rows(ids[i : i + 10]):
            if row.get("entity_id"):
                out[row["entity_id"]] = row.get("query", {}) or {}
    missing = [i for i in ids if i not in out]
    for i, rs in zip(missing, pmap(lambda x: rows([x]), missing, workers=6)):
        for row in rs:
            out[row.get("entity_id") or i] = row.get("query", {}) or {}
    return out


def rank_for_audience(entity_ids: list[str], entity_type: str, age: str | None = None, gender: str | None = None, location: str | None = None) -> dict[str, float]:
    """Affinity of the given entities for an audience, in ONE call so scores are comparable.
    Uses filter.results.entities so Qloo scores exactly our list (same shape as the harness's rank workflow)."""
    ids = list(dict.fromkeys(i for i in entity_ids if i))
    params = {"filter.type": f"urn:entity:{entity_type}", "filter.results.entities": ids, "take": len(ids)}
    if age:
        params["signal.demographics.age"] = age
    if gender:
        params["signal.demographics.gender"] = gender
    if location:
        params["signal.location.query"] = location
    out = {}
    for e in _entities(get("/v2/insights", params)):
        a = affinity(e)
        if eid(e) and a is not None:
            out[eid(e)] = a
    return out


def where_popular(entity_id: str, location: str, boundary: str | None = None) -> list[dict]:
    """Heatmap cells (or localities when boundary='urn:entity:locality') for one entity within a place."""
    params = {"filter.type": "urn:heatmap", "signal.interests.entities": [entity_id], "filter.location.query": location}
    if boundary:
        params["output.heatmap.boundary"] = boundary
    data = get("/v2/insights", params)
    return (data.get("results", {}) or {}).get("heatmap", []) or []


def trending(entity_id: str, entity_type: str, start: str, end: str) -> list[dict]:
    """Weekly popularity percentile / rank velocity for one entity between ISO dates."""
    data = get("/v2/trending", {"signal.interests.entities": [entity_id], "filter.type": f"urn:entity:{entity_type}", "filter.start_date": start, "filter.end_date": end, "take": 50})
    return (data.get("results", {}) or {}).get("trending", []) or []


def entity_tags(entity_ids: list[str], take: int = 12) -> list[dict]:
    """Tags that characterise the given entities (urn:tag insights): [{tag_id, name, type, affinity}]."""
    data = get("/v2/insights", {"filter.type": "urn:tag", "signal.interests.entities": entity_ids, "take": take})
    out = []
    for t in (data.get("results", {}) or {}).get("tags", []) or []:
        tid = t.get("tag_id") or t.get("id")
        if tid and t.get("name"):
            out.append({"tag_id": tid, "name": t["name"], "type": t.get("type") or t.get("subtype"), "affinity": affinity(t)})
    return out


def recommend(entity_type: str, signal_entities: list[str] | None = None, signal_tags: list[str] | None = None, tags_operator: str = "union", age: str | None = None, gender: str | None = None, location: str | None = None, min_popularity: float | None = None, take: int = 15) -> list[dict]:
    """Entities of one type that an audience over-indexes on, optionally steered by seed entities/tags."""
    params = {"filter.type": f"urn:entity:{entity_type}", "take": take}
    if signal_entities:
        params["signal.interests.entities"] = signal_entities
    if signal_tags:
        params["signal.interests.tags"] = signal_tags
        params["operator.signal.interests.tags"] = tags_operator
    if age:
        params["signal.demographics.age"] = age
    if gender:
        params["signal.demographics.gender"] = gender
    if location:
        params["signal.location.query"] = location
    if min_popularity is not None:
        params["filter.popularity.min"] = min_popularity
    out = _entities(get("/v2/insights", params))
    for e in out:
        if "entity_id" not in e and e.get("id"):
            e["entity_id"] = e["id"]
    return out


if __name__ == "__main__":
    # Self-checks without a key: cache hit with no key set, harness-style field fallbacks, ledger recording.
    CACHE_PATH = "/tmp/qloo-selftest.sqlite"
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)
    _db = None
    k = hashlib.sha1(("/search" + json.dumps({"query": "x", "take": 8}, sort_keys=True)).encode()).hexdigest()
    _cache().execute("insert or replace into q values (?,?,?)", (k, json.dumps({"results": {"entities": [{"name": "x", "id": "e1"}]}}), time.time()))
    _cache().commit()
    os.environ.pop("QLOO_API_KEY", None)
    os.environ.pop("QLOO_MOCK", None)
    calls = start_ledger()
    assert search("x") == [{"name": "x", "id": "e1", "entity_id": "e1"}]
    assert calls and calls[0]["source"] == "cache"
    assert affinity({"query": {"affinity": 0.4}}) == 0.4 and affinity({"affinity": 0.2, "query": {"affinity": 0.9}}) == 0.2 and affinity({}) is None
    got = pmap(lambda x: (_ledger.get() is calls), [1, 2, 3])
    assert got == [True, True, True]
    print("ok")
