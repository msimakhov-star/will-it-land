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
    "tower records": (0.5, -0.6, 0.5), "stormzy": (0.7, 0.6, -0.6), "spotify wrapped": (0.75, 0.6, -0.5), "bebo": (0.35, -0.3, 0.2),
    "angry birds": (0.8, 0.0, -0.1), "friends reunited": (0.3, -0.5, 0.4), "vesta curry": (0.3, -0.6, 0.6), "wimpy": (0.45, -0.5, 0.5),
    "greggs": (0.8, 0.3, 0.1), "nando's": (0.85, 0.5, -0.3), "fred again..": (0.6, 0.6, -0.6), "central cee": (0.65, 0.65, -0.6),
}
# per-place lift for the demo's market examples: name -> {place: affinity}; anything else is hashed
LOCAL = {
    "succession": {"united states": 0.9, "india": 0.1, "brazil": 0.2, "united kingdom": 0.7},
    "ted lasso": {"united kingdom": 0.95, "united states": 0.8, "india": 0.15, "brazil": 0.1, "texas": 0.6},
    "taylor swift": {"united states": 0.95, "texas": 0.9, "india": 0.35, "brazil": 0.5},
    "coldplay": {"india": 0.9, "brazil": 0.85, "united kingdom": 0.9},
    "minecraft": {},
    "greggs": {"london": 0.95, "united kingdom": 0.95, "st. louis": 0.05, "texas": 0.05},
    "manhattan": {"new york": 0.95, "london": 0.4},
}
_SEEN: dict[str, str] = {}  # entity id -> the name that was searched, so later calls know what the entity is
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
    return _SEEN.get(eid) or next((n for n in list(KNOWN) + [x.lower() for v in SUGGEST.values() for x in v] if _eid(n) == eid), eid)


def _known(name: str):
    """Exact match, or the table entry the name starts with ('domino's pizza' -> 'domino's', 'hollister co.' -> 'hollister')."""
    n = name.lower()
    return KNOWN.get(n) or next((v for k, v in KNOWN.items() if n.startswith(k + " ") or n.startswith(k + ".")), None)


def _pop(name: str) -> float:
    """Real Qloo popularity is a percentile over a huge catalogue, so famous things sit at 0.99 to 0.9999.
    Map the table's 0..1 'fame' onto that range so the mock exercises the same saturation the real data has."""
    fame = (_known(name) or (round(0.3 + 0.6 * _h(name), 2), 0, 0))[0]
    return round(1 - 10 ** (-(1 + 3 * fame)), 6)


AMBIGUOUS = {"friends": "Friends (2011 film)", "chelsea": "Chelsea (person)", "manhattan": "Manhattan (1979 film)"}


def _faults() -> dict[str, float]:
    """QLOO_MOCK_FAULTS=429:0.15,timeout:0.05,empty:0.1 injects failures so the degraded paths run offline."""
    import os

    out = {}
    for part in (os.environ.get("QLOO_MOCK_FAULTS") or "").split(","):
        k, _, v = part.partition(":")
        if k and v:
            out[k.strip()] = float(v)
    return out


def respond(path: str, params: dict) -> dict:
    import random

    f = _faults()
    if f:
        from .qloo import QlooError

        roll = random.random()
        if roll < f.get("429", 0):
            raise QlooError("Qloo rate limit (429). Try again shortly.")
        if roll < f.get("429", 0) + f.get("timeout", 0):
            raise QlooError("Qloo unreachable: ReadTimeout")
        if roll < f.get("429", 0) + f.get("timeout", 0) + f.get("empty", 0):
            return {"success": True, "results": [] if path == "/search" else {}}
    return _respond(path, params)


def _respond(path: str, params: dict) -> dict:
    if path == "/search":
        q = params["query"]
        t = (params.get("types") or "urn:entity:tv_show").split(",")[0]
        _SEEN[_eid(q)] = q.lower()
        hits = [{"name": q, "entity_id": _eid(q), "types": [t], "popularity": _pop(q), "properties": {}}]
        if q.lower() in AMBIGUOUS:  # so the disambiguation path runs offline too
            alt = AMBIGUOUS[q.lower()]
            _SEEN[_eid(alt)] = alt.lower()
            hits.append({"name": alt, "entity_id": _eid(alt), "types": [t], "popularity": round(_pop(q) - 0.009, 6), "properties": {"short_description": "a different entity with the same name"}})
        return {"success": True, "results": hits[: int(params.get("take", 8))]}
    if path == "/v2/insights":
        ftype = params.get("filter.type", "")
        ids = [i for i in (params.get("signal.interests.entities") or params.get("filter.results.entities") or "").split(",") if i]
        if ftype == "urn:demographics":
            rows = []
            for i in ids:
                name = _name(i)
                k = _known(name)
                # unknown entities get a mild deterministic skew, not a random dramatic one
                _, young, old = k if k else (0, 0.3 * (_h(name) - 0.5), 0.3 * (0.5 - _h(name)))
                age = {"24_and_younger": young, "25_to_29": young * 0.7, "30_to_34": young * 0.3, "35_to_44": 0.0, "45_to_54": old * 0.6, "55_and_older": old}
                rows.append({"entity_id": i, "query": {"age": age, "gender": {"male": 0.05, "female": -0.05}}})
            return {"success": True, "results": {"demographics": rows}}
        if ftype == "urn:heatmap":
            return {"success": True, "results": {"heatmap": []}}
        if ftype == "urn:tag":
            return {"success": True, "results": {"tags": [{"tag_id": f"urn:tag:genre:mock:{k}", "name": k, "subtype": "urn:tag:genre"} for k in ("nostalgia", "pop culture", "comedy")]}}
        etype = ftype.split(":")[-1]
        if params.get("filter.results.entities"):
            loc = (params.get("signal.location.query") or "").lower()

            def aff(i):
                local = next((v for k, v in LOCAL.items() if _name(i).startswith(k)), None)
                if local is not None and loc in local:
                    return local[loc]
                return round(_h(i + loc), 3)

            ents = [{"entity_id": i, "name": _name(i), "query": {"affinity": aff(i)}} for i in ids]
        else:
            names = SUGGEST.get(etype, [])
            ents = [{"entity_id": _eid(n), "name": n, "popularity": _pop(n), "query": {"affinity": round(_h(n), 3)}} for n in names]
        return {"success": True, "results": {"entities": ents}}
    if path == "/v2/trending":
        return {"success": True, "results": {"trending": [{"date": "2026-05-01", "population_percentile": 0.8, "population_rank_velocity": 0.0, "population_percent_delta": 0.0}, {"date": "2026-10-01", "population_percentile": 0.81, "population_rank_velocity": 0.1, "population_percent_delta": 1.2}]}}
    return {"success": True, "results": {}}
