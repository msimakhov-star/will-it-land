"""Deterministic fake Qloo responses for offline UI work and tests (QLOO_MOCK=1). Never used once a key is set.
Shapes mirror the real endpoints as parsed by Qloo's own harness; numbers are hashed from the query so runs are stable.
The mock exists so the product can be built before the hackathon key arrives; nothing it returns is shown as real data."""
from __future__ import annotations

import hashlib

KNOWN = {  # name -> (popularity percentile, young skew, old skew)
    "seinfeld": (0.93, -0.35, 0.45), "blockbuster": (0.6, -0.5, 0.4), "fortnite": (0.9, 0.6, -0.5), "myspace": (0.55, -0.4, 0.1),
    "nokia": (0.8, -0.2, 0.3), "friends": (0.97, 0.1, 0.2), "taylor swift": (0.99, 0.5, -0.3), "minecraft": (0.95, 0.6, -0.5),
    "coldplay": (0.9, 0.0, 0.1), "succession": (0.7, 0.2, -0.1), "ted lasso": (0.75, 0.1, 0.0), "hollister": (0.6, 0.1, -0.4),
    "the hangover": (0.85, 0.0, -0.1), "peloton": (0.7, 0.1, -0.1), "spotify": (0.95, 0.4, -0.3), "domino's": (0.9, 0.1, 0.0),
    "lidl": (0.7, 0.0, 0.1), "le creuset": (0.6, -0.2, 0.3), "game of thrones": (0.95, 0.2, -0.2), "manhattan": (0.9, 0.0, 0.1),
    "hmv": (0.7, -0.1, 0.3), "netflix": (0.98, 0.3, 0.1), "the office": (0.94, 0.3, 0.0), "stranger things": (0.92, 0.5, -0.2),
    "tiktok": (0.97, 0.6, -0.4), "facebook": (0.98, -0.2, 0.4), "iphone": (0.98, 0.3, 0.0), "the simpsons": (0.96, 0.1, 0.2),
}
SUGGEST = {  # what the fake "recommend" returns per type
    "brand": ["Netflix", "HMV", "TikTok", "Facebook", "iPhone"],
    "tv_show": ["The Office", "Stranger Things", "The Simpsons", "Friends"],
    "videogame": ["Minecraft", "Fortnite"],
    "artist": ["Taylor Swift", "Coldplay"],
    "movie": ["The Hangover"],
    "place": ["Manhattan"],
}


def _h(s: str) -> float:
    return int(hashlib.sha1(s.lower().encode()).hexdigest()[:6], 16) / 0xFFFFFF


def _eid(name: str) -> str:
    return "mock-" + hashlib.sha1(name.lower().encode()).hexdigest()[:12]


def _name(eid: str) -> str:
    return next((n for n in list(KNOWN) + [x.lower() for v in SUGGEST.values() for x in v] if _eid(n) == eid), eid)


def _pop(name: str) -> float:
    return KNOWN.get(name.lower(), (round(0.3 + 0.6 * _h(name), 2), 0, 0))[0]


def respond(path: str, params: dict) -> dict:
    if path == "/search":
        q = params["query"]
        t = (params.get("types") or "urn:entity:tv_show").split(",")[0]
        return {"success": True, "results": [{"name": q, "entity_id": _eid(q), "types": [t], "popularity": _pop(q), "properties": {}}]}
    if path == "/v2/insights":
        ftype = params.get("filter.type", "")
        ids = [i for i in (params.get("signal.interests.entities") or params.get("filter.results.entities") or "").split(",") if i]
        if ftype == "urn:demographics":
            rows = []
            for i in ids:
                name = _name(i)
                _, young, old = KNOWN.get(name, (0, _h(i) - 0.5, 0.5 - _h(i)))
                age = {"24_and_younger": young, "25_to_29": young * 0.7, "30_to_34": young * 0.3, "35_to_44": 0.0, "45_to_54": old * 0.6, "55_and_older": old}
                rows.append({"entity_id": i, "query": {"age": age, "gender": {"male": 0.05, "female": -0.05}}})
            return {"success": True, "results": {"demographics": rows}}
        if ftype == "urn:heatmap":
            return {"success": True, "results": {"heatmap": []}}
        if ftype == "urn:tag":
            return {"success": True, "results": {"tags": [{"tag_id": f"urn:tag:genre:mock:{k}", "name": k, "subtype": "urn:tag:genre"} for k in ("nostalgia", "pop culture", "comedy")]}}
        etype = ftype.split(":")[-1]
        if params.get("filter.results.entities"):
            ents = [{"entity_id": i, "name": _name(i), "query": {"affinity": round(_h(i + (params.get("signal.location.query") or "")), 3)}} for i in ids]
        else:
            names = SUGGEST.get(etype, [])
            ents = [{"entity_id": _eid(n), "name": n, "popularity": _pop(n), "query": {"affinity": round(_h(n), 3)}} for n in names]
        return {"success": True, "results": {"entities": ents}}
    if path == "/v2/trending":
        return {"success": True, "results": {"trending": [{"date": "2026-05-01", "population_percentile": 0.8, "population_rank_velocity": 0.0, "population_percent_delta": 0.0}, {"date": "2026-10-01", "population_percentile": 0.81, "population_rank_velocity": 0.1, "population_percent_delta": 1.2}]}}
    return {"success": True, "results": {}}
