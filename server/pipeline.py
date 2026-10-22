"""The agent loop: extract -> resolve -> score -> swap -> rewrite -> re-score.

Everything Qloo-related is aggregate audience data. The text is the user's own; only entity names go to Qloo.
"""
from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from . import llm, qloo

# Qloo age buckets the UI offers. "35_and_younger" / "36_to_55" are coarse signal-only values; we use the fine ones.
AUDIENCE_AGES = qloo.AGE_BUCKETS
TYPES = qloo.INSIGHT_TYPES

# Fixed anchors per type so a rank call always has known points: one near-universal, one niche.
# Chosen by name; resolved once per process through /search and cached like everything else.
ANCHORS = {
    "tv_show": ["Friends", "Twin Peaks"],
    "movie": ["Titanic", "Primer"],
    "artist": ["Taylor Swift", "Boards of Canada"],
    "brand": ["Coca-Cola", "Allbirds"],
    "person": ["Barack Obama", "Werner Herzog"],
    "book": ["Harry Potter and the Philosopher's Stone", "Infinite Jest"],
    "videogame": ["Minecraft", "Disco Elysium"],
    "podcast": ["The Joe Rogan Experience", "Reply All"],
    "place": ["Times Square", "Sultan Ahmed Mosque"],
}

EXTRACT_SYSTEM = """You find cultural references in text for a reference-checker.
A cultural reference is a named thing an audience has to recognise for the line to work: TV shows, films, musicians or bands,
brands or products, famous people, books, video games, podcasts, specific places or venues. Not generic nouns, not slang, not memes.
For each reference give:
- "surface": the exact text as written (must appear verbatim in the input)
- "type": one of tv_show, movie, artist, brand, person, book, videogame, podcast, place
- "query": the canonical name to look it up by (e.g. "Seinfeld", "The Sopranos", "Blockbuster")
- "role": what the reference is doing in the line, so a stand-in could play the same part (e.g. "a famously cancelled 90s sitcom", "a dead video-rental chain", "a luxury car brand that signals new money")
- "era": approximate decade or year the reference belongs to, if evident, else null
- "guess": your own estimate, 0-100, of how likely the TARGET AUDIENCE is to know this reference, with no data
Return {"references": [...]}. Keep duplicates: each occurrence is its own entry."""

PICK_SYSTEM = """You disambiguate a reference against candidate entities from a knowledge graph.
Given the line, the reference, its intended type and role, and candidates (name, type, year/disambiguation, popularity), return
{"pick": <index of best candidate or -1 if none fits>, "why": "<one short clause>"}."""

SWAP_SYSTEM = """You propose stand-in references for a line whose current reference will not land with the target audience.
Each stand-in must play the same ROLE in the joke or sentence, be the same type of thing, and be something the target audience
is likely to know. Prefer things that are at least as famous with that audience. Return {"candidates": ["Name", ...]} with 6 names,
most promising first. No explanations."""

REWRITE_SYSTEM = """You rewrite one line of a script so that a named reference is replaced by each stand-in in turn, keeping rhythm,
tone, tense and length, changing nothing else (fix articles like a/an if needed). Return {"lines": ["<line with stand-in 1>", ...]}
in the same order as the stand-ins."""


@dataclass
class Audience:
    age: str | None = None  # one of AUDIENCE_AGES
    gender: str | None = None  # male | female | None
    location: str | None = None  # free text locality, e.g. "London", "Texas", "United Kingdom"

    def label(self) -> str:
        bits = []
        if self.age:
            bits.append(self.age.replace("_", " "))
        if self.gender:
            bits.append(self.gender)
        if self.location:
            bits.append(self.location)
        return ", ".join(bits) or "general audience"


@dataclass
class Swap:
    name: str
    entity_id: str
    score: float
    line: str | None = None


@dataclass
class Reference:
    surface: str
    start: int
    end: int
    type: str
    query: str
    role: str
    era: str | None
    llm_guess: float
    entity_id: str | None = None
    name: str | None = None
    disambiguation: str | None = None
    candidates: list[dict] = field(default_factory=list)
    popularity: float | None = None
    affinity: float | None = None
    age_skew: dict | None = None
    gender_skew: dict | None = None
    trend: dict | None = None
    score: float | None = None
    verdict: str = "unknown"  # lands | risky | misses | unknown
    why: str = ""
    swaps: list[Swap] = field(default_factory=list)


def _similar(a: str, b: str) -> bool:
    import difflib

    a, b = a.lower().strip(), b.lower().strip()
    return a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def _locate(text: str, surface: str, used: list[tuple[int, int]]) -> tuple[int, int] | None:
    pos = 0
    while True:
        i = text.find(surface, pos)
        if i < 0:
            return None
        span = (i, i + len(surface))
        if not any(a < span[1] and span[0] < b for a, b in used):
            used.append(span)
            return span
        pos = i + 1


def extract(text: str, audience: Audience) -> list[Reference]:
    out = llm.complete_json(EXTRACT_SYSTEM, f"TARGET AUDIENCE: {audience.label()}\n\nTEXT:\n{text}")
    refs, used = [], []
    for r in out.get("references", []):
        if r.get("type") not in TYPES or not r.get("surface"):
            continue
        span = _locate(text, r["surface"], used)
        if not span:
            continue
        refs.append(
            Reference(
                surface=r["surface"], start=span[0], end=span[1], type=r["type"], query=r.get("query") or r["surface"],
                role=r.get("role") or "", era=r.get("era"), llm_guess=float(r.get("guess") or 50),
            )
        )
    return refs


def _line_of(text: str, ref: Reference) -> str:
    a = text.rfind("\n", 0, ref.start) + 1
    b = text.find("\n", ref.end)
    return text[a : b if b >= 0 else len(text)]


def _summ(e: dict) -> dict:
    p = e.get("properties") or {}
    return {
        "entity_id": e.get("entity_id"),
        "name": e.get("name"),
        "type": (e.get("types") or [e.get("type") or ""])[0].split(":")[-1] if (e.get("types") or e.get("type")) else None,
        "popularity": e.get("popularity"),
        "year": p.get("release_year") or p.get("publication_year") or p.get("date_of_birth") or p.get("release_date"),
        "disambiguation": e.get("disambiguation") or p.get("short_description") or p.get("description", "")[:80],
    }


def resolve(text: str, refs: list[Reference]) -> None:
    def one(ref: Reference):
        try:
            hits = qloo.search(ref.query, types=[ref.type], take=6)
        except qloo.QlooError as ex:
            ref.why = str(ex)
            return
        ref.candidates = [_summ(h) for h in hits][:6]
        if not ref.candidates:
            ref.verdict = "unknown"
            ref.why = "not in Qloo"
            return
        pick = 0
        exact = [i for i, c in enumerate(ref.candidates) if (c["name"] or "").lower() == ref.query.lower()]
        if len(ref.candidates) > 1 and (len(exact) != 1 or exact[0] != 0):
            try:
                res = llm.complete_json(
                    PICK_SYSTEM,
                    json.dumps({"line": _line_of(text, ref), "reference": ref.surface, "type": ref.type, "role": ref.role, "era": ref.era, "candidates": ref.candidates}),
                    fast=True,
                )
                pick = int(res.get("pick", 0))
            except Exception:
                pick = exact[0] if exact else 0
        if pick < 0 or pick >= len(ref.candidates):
            ref.verdict = "unknown"
            ref.why = "no candidate matched"
            return
        c = ref.candidates[pick]
        ref.entity_id, ref.name, ref.popularity, ref.disambiguation = c["entity_id"], c["name"], c.get("popularity"), c.get("disambiguation")

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, refs))


def _bucket_aff(skew: dict | None, age: str | None) -> float:
    if not skew or not age:
        return 0.0
    return float(skew.get(age, 0) or 0)


def land_score(popularity: float | None, age_aff: float, gender_aff: float, loc_aff: float | None) -> float:
    """0-100 'likely to land'. Base is Qloo popularity percentile (how widely known); demographic and location
    affinity shift it. Weights are a first guess; eval/ calibrates them against YouGov fame."""
    base = 100 * (popularity if popularity is not None else 0.5)
    s = base + 35 * age_aff + 15 * gender_aff + (25 * loc_aff if loc_aff is not None else 0)
    return max(0.0, min(100.0, s))


def verdict_for(score: float) -> str:
    return "lands" if score >= 65 else "risky" if score >= 40 else "misses"


def score(refs: list[Reference], audience: Audience) -> None:
    live = [r for r in refs if r.entity_id]
    if not live:
        return
    ids = sorted({r.entity_id for r in live})
    demo = qloo.demographics(ids)
    # one rank call per entity type, with anchors, so affinities are comparable within the type
    aff: dict[str, float] = {}
    anchor_aff: dict[str, dict[str, float]] = {}
    if audience.age or audience.gender or audience.location:
        for t in sorted({r.type for r in live}):
            tids = sorted({r.entity_id for r in live if r.type == t})
            anchors = [h[0]["entity_id"] for n in ANCHORS.get(t, []) if (h := qloo.search(n, types=[t], take=1))]
            try:
                res = qloo.rank_for_audience(tids + anchors, t, audience.age, audience.gender, audience.location)
            except qloo.QlooError:
                res = {}
            aff.update({k: v for k, v in res.items() if k in tids})
            anchor_aff[t] = {k: v for k, v in res.items() if k in anchors}
    end = dt.date.today()
    start = end - dt.timedelta(days=180)

    def trend(ref: Reference):
        try:
            rows = qloo.trending(ref.entity_id, ref.type, start.isoformat(), end.isoformat())
        except qloo.QlooError:
            return
        if len(rows) >= 2:
            first, last = rows[0], rows[-1]
            ref.trend = {"percentile": last.get("population_percentile"), "delta": last.get("population_percent_delta"), "weeks": len(rows),
                         "direction": "rising" if (last.get("population_rank_velocity") or 0) > 0 else "fading" if (last.get("population_rank_velocity") or 0) < 0 else "flat"}

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(trend, live))

    for r in live:
        d = demo.get(r.entity_id) or {}
        r.age_skew, r.gender_skew = d.get("age"), d.get("gender")
        a = _bucket_aff(r.age_skew, audience.age)
        g = float((r.gender_skew or {}).get(audience.gender, 0) or 0) if audience.gender else 0.0
        loc = None
        if audience.location and r.entity_id in aff and anchor_aff.get(r.type):
            vals = list(anchor_aff[r.type].values())
            lo, hi = min(vals), max(vals)
            loc = max(-0.5, min(0.5, (aff[r.entity_id] - lo) / (hi - lo) - 0.5)) if hi > lo else 0.0  # -0.5..0.5 relative to anchors
        r.affinity = aff.get(r.entity_id)
        r.score = round(land_score(r.popularity, a, g, loc), 1)
        r.verdict = verdict_for(r.score)
        bits = [f"popularity {int(100 * (r.popularity or 0))}th pct"]
        if audience.age and r.age_skew:
            bits.append(f"{'over' if a >= 0 else 'under'}-indexes with {audience.age.replace('_', ' ')} ({a:+.2f})")
        if loc is not None:
            bits.append(f"{'strong' if loc > 0 else 'weak'} in {audience.location}")
        if r.trend and r.trend["direction"] != "flat":
            bits.append(r.trend["direction"])
        r.why = "; ".join(bits)


def propose_swaps(text: str, refs: list[Reference], audience: Audience, max_refs: int = 6) -> None:
    weak = [r for r in refs if r.verdict in ("risky", "misses")][:max_refs]

    def one(ref: Reference):
        line = _line_of(text, ref)
        try:
            cands = llm.complete_json(SWAP_SYSTEM, json.dumps({"audience": audience.label(), "line": line, "reference": ref.surface, "type": ref.type, "role": ref.role})).get("candidates", [])
        except Exception:
            return
        found = []
        for n in cands[:6]:
            hits = qloo.search(n, types=[ref.type], take=1)
            # keep only real entities whose name is what the model proposed (Qloo search is fuzzy)
            if hits and hits[0].get("entity_id") != ref.entity_id and _similar(n, hits[0].get("name", "")):
                found.append(hits[0])
        if not found:
            return
        ids = [h["entity_id"] for h in found]
        demo = qloo.demographics(ids)
        aff = {}
        if audience.location:
            try:
                aff = qloo.rank_for_audience(ids + [ref.entity_id], ref.type, audience.age, audience.gender, audience.location)
            except qloo.QlooError:
                aff = {}
        scored = []
        for h in found:
            d = demo.get(h["entity_id"]) or {}
            a = _bucket_aff(d.get("age"), audience.age)
            g = float((d.get("gender") or {}).get(audience.gender, 0) or 0) if audience.gender else 0.0
            loc = None
            if aff and ref.entity_id in aff:
                loc = 0.5 if aff.get(h["entity_id"], 0) > aff[ref.entity_id] else -0.2
            scored.append(Swap(h["name"], h["entity_id"], round(land_score(h.get("popularity"), a, g, loc), 1)))
        scored = [s for s in sorted(scored, key=lambda s: -s.score) if s.score > (ref.score or 0)][:3]
        if scored:
            try:
                lines = llm.complete_json(REWRITE_SYSTEM, json.dumps({"line": line, "replace": ref.surface, "with": [s.name for s in scored]}), fast=True).get("lines", [])
                for s, l in zip(scored, lines):
                    s.line = l
            except Exception:
                pass
        ref.swaps = scored

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, weak))


def swaps_for(text: str, audience: Audience, references: list[dict]) -> list[dict]:
    """Second phase: given scored references (as returned by check(..., swaps=False)), find stand-ins."""
    refs = [Reference(**{k: v for k, v in r.items() if k != "swaps"}) for r in references]
    propose_swaps(text, refs, audience)
    return [asdict(r) for r in refs]


def check(text: str, audience: Audience, swaps: bool = True) -> dict:
    import time

    timings = {}
    t = time.time()
    refs = extract(text, audience)
    timings["extract"] = round(time.time() - t, 1); t = time.time()
    resolve(text, refs)
    timings["resolve"] = round(time.time() - t, 1); t = time.time()
    score(refs, audience)
    timings["score"] = round(time.time() - t, 1); t = time.time()
    if swaps:
        propose_swaps(text, refs, audience)
        timings["swaps"] = round(time.time() - t, 1)
    checked = [r for r in refs if r.entity_id]
    return {
        "timings": timings,
        "audience": asdict(audience),
        "summary": {
            "found": len(refs),
            "checked": len(checked),
            "not_in_qloo": len(refs) - len(checked),
            "lands": sum(r.verdict == "lands" for r in checked),
            "risky": sum(r.verdict == "risky" for r in checked),
            "misses": sum(r.verdict == "misses" for r in checked),
        },
        "references": [asdict(r) for r in refs],
    }


if __name__ == "__main__":
    # offline self-check of the pure parts
    t = "We rented it at Blockbuster.\nBlockbuster again."
    used = []
    assert _locate(t, "Blockbuster", used) == (16, 27), used
    assert _locate(t, "Blockbuster", used) == (29, 40), used
    assert verdict_for(land_score(0.9, 0.3, 0, None)) == "lands" and verdict_for(land_score(0.3, -0.4, 0, None)) == "misses"
    print("ok")
