"""Thin Qloo REST client with an on-disk cache. Every call the app makes to Qloo goes through here.

Base URL and key come from env (QLOO_BASE_URL, QLOO_API_KEY). Hackathon keys only work on
https://hackathon.api.qloo.com. Qloo silently ignores unknown params (200 + empty), so helpers
only build params the entity-type guide allows.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time

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


class QlooError(RuntimeError):
    pass


def _cache() -> sqlite3.Connection:
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(os.path.abspath(CACHE_PATH)), exist_ok=True)
        _db = sqlite3.connect(CACHE_PATH, check_same_thread=False)
        _db.execute("create table if not exists q (k text primary key, v text, t real)")
    return _db


def get(path: str, params: dict, ttl: float = 7 * 86400) -> dict:
    """GET a Qloo endpoint. Lists become comma-joined strings. Cached by (path, params)."""
    clean = {k: (",".join(map(str, v)) if isinstance(v, (list, tuple)) else v) for k, v in params.items() if v not in (None, "", [], ())}
    key = hashlib.sha1((path + json.dumps(clean, sort_keys=True)).encode()).hexdigest()
    with _lock:
        row = _cache().execute("select v, t from q where k=?", (key,)).fetchone()
    if row and time.time() - row[1] < ttl:
        return json.loads(row[0])
    if os.environ.get("QLOO_MOCK"):
        from . import mock

        return mock.respond(path, clean)
    api_key = os.environ.get("QLOO_API_KEY")
    if not api_key:
        raise QlooError("QLOO_API_KEY is not set")
    r = _http.get(BASE_URL + path, params=clean, headers={"X-Api-Key": api_key})
    if r.status_code == 401:
        raise QlooError("Qloo rejected the key (401). Check QLOO_API_KEY and that QLOO_BASE_URL is the hackathon host.")
    if r.status_code == 429:
        raise QlooError("Qloo rate limit (429). Try again shortly.")
    if r.status_code >= 400:
        raise QlooError(f"Qloo {r.status_code}: {r.text[:200]}")
    data = r.json()
    with _lock:
        _cache().execute("insert or replace into q values (?,?,?)", (key, json.dumps(data), time.time()))
        _cache().commit()
    return data


# ---- helpers: one per API capability the product uses ----------------------------------------


def search(query: str, types: list[str] | None = None, take: int = 8) -> list[dict]:
    """Resolve a name to candidate entities. Returns entity dicts (name, entity_id, types, popularity, properties...)."""
    params = {"query": query, "take": take}
    if types:
        params["types"] = [t if t.startswith("urn:") else f"urn:entity:{t}" for t in types]
    return get("/search", params).get("results", []) or []


def demographics(entity_ids: list[str]) -> dict[str, dict]:
    """Age and gender affinity per entity. Returns {entity_id: {"age": {...}, "gender": {...}}}. Values are
    relative over/under-indexing around 0 (sample range seen: -0.5 to 0.7)."""
    out: dict[str, dict] = {}
    for i in range(0, len(entity_ids), 10):  # keep requests small
        data = get("/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": entity_ids[i : i + 10]})
        for row in (data.get("results", {}) or {}).get("demographics", []) or []:
            out[row.get("entity_id")] = row.get("query", {})
    return out


def rank_for_audience(entity_ids: list[str], entity_type: str, age: str | None = None, gender: str | None = None, location: str | None = None) -> dict[str, float]:
    """Affinity of the given entities for an audience, in ONE call so scores are comparable.
    Uses filter.results.entities so Qloo scores exactly our list."""
    params = {
        "filter.type": f"urn:entity:{entity_type}",
        "filter.results.entities": entity_ids,
        "take": max(len(entity_ids), 20),
    }
    if age:
        params["signal.demographics.age"] = age
    if gender:
        params["signal.demographics.gender"] = gender
    if location:
        params["signal.location.query"] = location
    data = get("/v2/insights", params)
    return {e.get("entity_id"): float((e.get("query") or {}).get("affinity", 0)) for e in (data.get("results", {}) or {}).get("entities", []) or []}


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


def entity_tags(entity_ids: list[str], take: int = 20) -> list[dict]:
    """Tags that characterise the given entities (urn:tag insights)."""
    data = get("/v2/insights", {"filter.type": "urn:tag", "signal.interests.entities": entity_ids, "take": take})
    return (data.get("results", {}) or {}).get("tags", []) or []


def recommend(entity_type: str, signal_entities: list[str] | None = None, signal_tags: list[str] | None = None, age: str | None = None, gender: str | None = None, location: str | None = None, min_popularity: float | None = None, take: int = 15) -> list[dict]:
    """Entities of one type that an audience over-indexes on, optionally steered by seed entities/tags."""
    params = {"filter.type": f"urn:entity:{entity_type}", "take": take}
    if signal_entities:
        params["signal.interests.entities"] = signal_entities
    if signal_tags:
        params["signal.interests.tags"] = signal_tags
    if age:
        params["signal.demographics.age"] = age
    if gender:
        params["signal.demographics.gender"] = gender
    if location:
        params["signal.location.query"] = location
    if min_popularity is not None:
        params["filter.popularity.min"] = min_popularity
    data = get("/v2/insights", params)
    return (data.get("results", {}) or {}).get("entities", []) or []


if __name__ == "__main__":
    # Self-check of the cache layer without a key: a cached row must be served even when QLOO_API_KEY is unset.
    os.environ["QLOO_CACHE"] = CACHE_PATH = "/tmp/qloo-selftest.sqlite"
    _db = None
    k = hashlib.sha1(("/search" + json.dumps({"query": "x", "take": 8}, sort_keys=True)).encode()).hexdigest()
    _cache().execute("insert or replace into q values (?,?,?)", (k, json.dumps({"results": [{"name": "x"}]}), time.time()))
    _cache().commit()
    os.environ.pop("QLOO_API_KEY", None)
    assert search("x") == [{"name": "x"}]
    print("ok")
