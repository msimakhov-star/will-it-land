"""The agent loop.

prepare(text)            extract references (LLM) -> resolve each to a Qloo entity (search + LLM disambiguation)
                         -> audience-independent Qloo data (demographics, trend). Cached per text.
score_entities(...)      ONE scoring function for references and stand-ins alike, per audience.
check(text, audience)    one audience: prepare + score + (optionally) stand-ins.
matrix(text, audiences)  many audiences at once: one extraction, one score column per audience.
propose_swaps(...)       stand-ins from two sources: Qloo itself (the reference's tags -> insights for the audience)
                         and the model (role-based ideas), every candidate resolved and scored by Qloo.
localise(text, audience) the visible agent loop: check -> apply best stand-ins -> re-check, until it lands or stops improving.

Everything Qloo-related is aggregate audience data. Only entity names leave the server, never the user's text.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import asdict, dataclass, field

from . import llm, qloo, scoring

AUDIENCE_AGES = qloo.AGE_BUCKETS
AGE_LABELS = {"24_and_younger": "under 25", "25_to_29": "25 to 29", "30_to_34": "30 to 34", "35_to_44": "35 to 44", "45_to_54": "45 to 54", "55_and_older": "55+"}
TYPES = qloo.INSIGHT_TYPES

# Fixed anchors per type so every location rank call contains two known points (one near-universal, one niche):
# location affinity is expressed relative to them, which keeps it comparable across calls.
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
Return {"references": [...]} in order of appearance. Keep duplicates: each occurrence is its own entry."""

GUESS_SYSTEM = """You estimate, from your own knowledge only, what percentage (0 to 100) of each audience would recognise each named thing.
Return {"guesses": [[<audience 1 %>, <audience 2 %>, ...], ...]} with one row per reference, in the given order."""

PICK_SYSTEM = """You disambiguate a reference against candidate entities from a knowledge graph.
Given the line, the reference, its intended type and role, and candidates (name, type, year/disambiguation, popularity), return
{"pick": <index of best candidate or -1 if none fits>, "why": "<one short clause>"}."""

SWAP_SYSTEM = """You propose stand-in references for a line whose current reference will not land with the target audience.
Each stand-in must play the same ROLE in the joke or sentence, be the same type of thing, and be something the target audience
is likely to know. Prefer things that are at least as famous with that audience. Return {"candidates": ["Name", ...]} with 6 names,
most promising first. No explanations."""

ROLE_FILTER_SYSTEM = """A writer needs a stand-in for a reference in one line. A taste graph proposed candidates that this audience over-indexes on.
Keep only candidates that could convincingly play the same ROLE in the line (same kind of thing, the joke or point still works).
Return {"keep": ["Name", ...]} using the exact names given, best first; [] if none fit."""

REWRITE_SYSTEM = """You rewrite one line of a script so that a named reference is replaced by each stand-in in turn, keeping rhythm,
tone, tense and length, changing nothing else (fix articles like a/an if needed). Return {"lines": ["<line with stand-in 1>", ...]}
in the same order as the stand-ins."""


@dataclass
class Audience:
    age: str | None = None  # one of AUDIENCE_AGES
    gender: str | None = None  # male | female | None
    location: str | None = None  # free text locality, e.g. "London", "Texas", "United Kingdom"
    name: str | None = None  # optional display name, e.g. "Tour stop: Leeds"

    def label(self) -> str:
        if self.name:
            return self.name
        bits = [AGE_LABELS.get(self.age, self.age) if self.age else None, {"male": "men", "female": "women"}.get(self.gender or "", None), self.location]
        return ", ".join(b for b in bits if b) or "general audience"

    def describe(self) -> str:
        """Plain description for prompts, without the display name."""
        return Audience(self.age, self.gender, self.location).label()


@dataclass
class Swap:
    name: str
    entity_id: str
    score: float
    source: str  # "qloo" (found by Qloo from the reference's tags for this audience) | "ai" (suggested by the model, checked by Qloo)
    why: str = ""
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
    entity_id: str | None = None
    name: str | None = None
    disambiguation: str | None = None
    candidates: list[dict] = field(default_factory=list)
    popularity: float | None = None
    age_skew: dict | None = None
    gender_skew: dict | None = None
    trend: dict | None = None
    # audience-specific (filled by check(); the matrix keeps these in cells instead)
    llm_guess: float | None = None
    affinity: float | None = None
    score: float | None = None
    verdict: str = "unknown"  # lands | risky | misses | unknown
    why: str = ""
    swaps: list[Swap] = field(default_factory=list)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


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


def _line_of(text: str, start: int, end: int) -> str:
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", end)
    return text[a : b if b >= 0 else len(text)]


# ---- prepare: everything that does not depend on the audience ------------------------------------


def extract(text: str) -> list[Reference]:
    prompt = f"TEXT:\n{text}"
    try:
        out = llm.complete_json(EXTRACT_SYSTEM, prompt, max_tokens=8000)
    except Exception:  # malformed JSON or a timeout: one retry on the fast model rather than a failed demo
        out = llm.complete_json(EXTRACT_SYSTEM, prompt, max_tokens=8000, fast=True)
    refs, used = [], []
    for r in out.get("references", []) if isinstance(out, dict) else []:
        if r.get("type") not in TYPES or not r.get("surface"):
            continue
        span = _locate(text, r["surface"], used)
        if not span:
            continue
        refs.append(Reference(surface=r["surface"], start=span[0], end=span[1], type=r["type"], query=r.get("query") or r["surface"], role=r.get("role") or "", era=r.get("era")))
    return sorted(refs, key=lambda r: r.start)


def _summ(e: dict) -> dict:
    p = e.get("properties") or {}
    types = e.get("types") or ([e["type"]] if e.get("type") else [])
    return {
        "entity_id": qloo.eid(e),
        "name": e.get("name"),
        "type": types[0].split(":")[-1] if types else None,
        "popularity": e.get("popularity"),
        "year": p.get("release_year") or p.get("publication_year") or p.get("date_of_birth") or p.get("release_date"),
        "disambiguation": e.get("disambiguation") or p.get("short_description") or (p.get("description") or "")[:80],
    }


def resolve(text: str, refs: list[Reference]) -> None:
    by_query: dict[tuple[str, str], list[dict]] = {}

    def lookup(key):
        try:
            by_query[key] = [_summ(h) for h in qloo.search(key[0], types=[key[1]], take=6)][:6]
        except qloo.QlooError as ex:
            by_query[key] = ex  # type: ignore[assignment]

    qloo.pmap(lookup, sorted({(r.query, r.type) for r in refs}))

    def one(ref: Reference):
        hits = by_query.get((ref.query, ref.type))
        if isinstance(hits, Exception):
            ref.why = str(hits)
            return
        ref.candidates = hits or []
        if not ref.candidates:
            ref.why = "not in Qloo"
            return
        pick = 0
        exact = [i for i, c in enumerate(ref.candidates) if (c["name"] or "").lower() == ref.query.lower()]
        if len(ref.candidates) > 1 and (len(exact) != 1 or exact[0] != 0):
            try:
                res = llm.complete_json(PICK_SYSTEM, json.dumps({"line": _line_of(text, ref.start, ref.end), "reference": ref.surface, "type": ref.type, "role": ref.role, "era": ref.era, "candidates": ref.candidates}), fast=True)
                pick = int(res.get("pick", 0))
            except Exception:
                pick = exact[0] if exact else 0
        if pick < 0 or pick >= len(ref.candidates):
            ref.why = "no candidate matched"
            return
        c = ref.candidates[pick]
        ref.entity_id, ref.name, ref.popularity, ref.disambiguation = c["entity_id"], c["name"], c.get("popularity"), c.get("disambiguation")

    qloo.pmap(one, refs)


def enrich(refs: list[Reference]) -> None:
    """Audience-independent Qloo signals: age/gender skew and six-month trend."""
    live = [r for r in refs if r.entity_id]
    if not live:
        return
    demo = qloo.demographics([r.entity_id for r in live])
    end = dt.date.today()
    start = end - dt.timedelta(days=180)
    trends: dict[str, dict] = {}

    def trend(key):
        e, t = key
        try:
            rows = qloo.trending(e, t, start.isoformat(), end.isoformat())
        except qloo.QlooError:
            return
        if len(rows) >= 2:
            last = rows[-1]
            v = last.get("population_rank_velocity") or 0
            trends[e] = {"percentile": last.get("population_percentile"), "delta": last.get("population_percent_delta"), "weeks": len(rows), "direction": "rising" if v > 0 else "fading" if v < 0 else "flat"}

    qloo.pmap(trend, sorted({(r.entity_id, r.type) for r in live}))
    for r in live:
        d = demo.get(r.entity_id) or {}
        r.age_skew, r.gender_skew, r.trend = d.get("age"), d.get("gender"), trends.get(r.entity_id)


_prep_cache: OrderedDict[str, list[dict]] = OrderedDict()
_prep_lock = threading.Lock()


def prepare(text: str) -> list[Reference]:
    """Extract + resolve + enrich, memoised per text (switching audiences never re-runs the LLM extraction)."""
    key = hashlib.sha1(text.encode()).hexdigest()
    with _prep_lock:
        hit = _prep_cache.get(key)
        if hit is not None:
            _prep_cache.move_to_end(key)
            return [Reference(**copy.deepcopy(d)) for d in hit]
    refs = extract(text)
    resolve(text, refs)
    enrich(refs)
    with _prep_lock:
        _prep_cache[key] = [asdict(r) for r in refs]
        while len(_prep_cache) > 256:
            _prep_cache.popitem(last=False)
    return refs


def guesses(refs: list[Reference], audiences: list[Audience]) -> list[list[float | None]]:
    """The model's own estimate, with no data, for every reference x audience. Shown next to the Qloo score."""
    if not refs:
        return []
    payload = {"audiences": [a.describe() for a in audiences], "references": [{"name": r.name or r.query, "type": r.type} for r in refs]}
    try:
        rows = llm.complete_json(GUESS_SYSTEM, json.dumps(payload)).get("guesses", [])
    except Exception:
        rows = []
    out = []
    for i in range(len(refs)):
        row = rows[i] if i < len(rows) and isinstance(rows[i], list) else []
        out.append([float(row[j]) if j < len(row) and isinstance(row[j], (int, float)) else None for j in range(len(audiences))])
    return out


# ---- scoring: one function for references and stand-ins -----------------------------------------


def land_score(popularity: float | None, age_aff: float, gender_aff: float, loc_aff: float | None) -> float:
    """0-100 'likely to land' (see server/scoring.py for the model and its calibration)."""
    return scoring.score(popularity, age_aff, gender_aff, loc_aff)


def verdict_for(score: float) -> str:
    return scoring.verdict(score)


_anchor_ids: dict[str, list[str]] = {}


def anchors_for(entity_type: str) -> list[str]:
    if entity_type not in _anchor_ids:
        ids = []
        for n in ANCHORS.get(entity_type, []):
            try:
                hits = qloo.search(n, types=[entity_type], take=3)
            except qloo.QlooError:
                hits = []
            hit = next((h for h in hits if _similar(n, h.get("name", ""))), None)
            if hit and qloo.eid(hit):
                ids.append(qloo.eid(hit))
        if len(ids) < 2:
            return ids  # do not memoise a failure (no key yet, transient error)
        _anchor_ids[entity_type] = ids
    return _anchor_ids[entity_type]


def score_entities(items: list[dict], audience: Audience) -> dict[str, dict]:
    """items: [{entity_id, type, popularity, age_skew, gender_skew}]. Returns {entity_id: cell}.
    Location affinity comes from one rank call per entity type (items + anchors), normalised between the anchors."""
    items = [i for i in items if i.get("entity_id")]
    loc_rel: dict[str, float] = {}
    affs: dict[str, float] = {}
    if audience.location:
        def per_type(t):
            ids = sorted({i["entity_id"] for i in items if i["type"] == t})
            anc = anchors_for(t)
            if len(anc) < 2:
                return {}, {}
            try:
                res = qloo.rank_for_audience(ids + anc, t, audience.age, audience.gender, audience.location)
            except qloo.QlooError:
                return {}, {}
            lo, hi = sorted([res.get(anc[0]), res.get(anc[1])], key=lambda v: (v is None, v))
            if lo is None or hi is None or hi <= lo:
                return {k: v for k, v in res.items() if k in ids}, {}
            return {k: v for k, v in res.items() if k in ids}, {k: max(-0.5, min(0.5, (v - lo) / (hi - lo) - 0.5)) for k, v in res.items() if k in ids}

        for a, l in qloo.pmap(per_type, sorted({i["type"] for i in items})):
            affs.update(a)
            loc_rel.update(l)
    out = {}
    for i in items:
        e = i["entity_id"]
        a = float((i.get("age_skew") or {}).get(audience.age, 0) or 0) if audience.age else 0.0
        g = float((i.get("gender_skew") or {}).get(audience.gender, 0) or 0) if audience.gender else 0.0
        loc = loc_rel.get(e)
        parts = scoring.components(i.get("popularity"), a, g, loc)
        s = parts["score"]
        bits = [f"known at the {_ordinal(int(100 * (i.get('popularity') or 0)))} percentile"]
        if audience.age and i.get("age_skew"):
            bits.append(f"{'over' if a >= 0 else 'under'}-indexes with {AGE_LABELS.get(audience.age, audience.age)} ({a:+.2f})")
        if audience.gender and i.get("gender_skew"):
            bits.append(f"{'over' if g >= 0 else 'under'}-indexes with {'men' if audience.gender == 'male' else 'women'} ({g:+.2f})")
        if loc is not None:
            bits.append(f"{'strong' if loc > 0.1 else 'weak' if loc < -0.1 else 'average'} in {audience.location}")
        out[e] = {"score": s, "verdict": verdict_for(s), "why": "; ".join(bits), "affinity": affs.get(e), "location": loc, "age_affinity": a if audience.age else None, "parts": parts}
    return out


def _items(refs: list[Reference]) -> list[dict]:
    return [{"entity_id": r.entity_id, "type": r.type, "popularity": r.popularity, "age_skew": r.age_skew, "gender_skew": r.gender_skew} for r in refs if r.entity_id]


def cells_for(refs: list[Reference], audience: Audience) -> list[dict | None]:
    scored = score_entities(_items(refs), audience)
    return [scored.get(r.entity_id) if r.entity_id else None for r in refs]


def _summary(cells: list[dict | None], total: int) -> dict:
    live = [c for c in cells if c]
    return {"found": total, "checked": len(live), "not_in_qloo": total - len(live), "lands": sum(c["verdict"] == "lands" for c in live), "risky": sum(c["verdict"] == "risky" for c in live), "misses": sum(c["verdict"] == "misses" for c in live)}


# ---- stand-ins -------------------------------------------------------------------------------------


def propose_swaps(text: str, ref: Reference, audience: Audience, current: float | None) -> list[Swap]:
    """Stand-ins for one weak reference, from Qloo (tags -> audience insights) and from the model (role), all scored the same way."""
    line = _line_of(text, ref.start, ref.end)
    pool: dict[str, tuple[dict, str, str]] = {}  # entity_id -> (entity, source, why)

    def from_qloo():
        try:
            tags = qloo.entity_tags([ref.entity_id], take=8)
        except qloo.QlooError:
            return []
        picked = [t for t in tags if t["type"] and "keyword" not in (t["type"] or "")][:3] or tags[:3]
        if not picked:
            return []
        try:
            ents = qloo.recommend(ref.type, signal_tags=[t["tag_id"] for t in picked], age=audience.age, gender=audience.gender, location=audience.location, min_popularity=0.5, take=12)
        except qloo.QlooError:
            return []
        ents = [e for e in ents if qloo.eid(e) and qloo.eid(e) != ref.entity_id and e.get("name")]
        if not ents:
            return []
        try:
            keep = llm.complete_json(ROLE_FILTER_SYSTEM, json.dumps({"line": line, "reference": ref.surface, "role": ref.role, "audience": audience.describe(), "candidates": [e["name"] for e in ents]}), fast=True).get("keep", [])
        except Exception:
            keep = []
        by_name = {e["name"]: e for e in ents}
        why = "found by Qloo from its tags " + ", ".join(t["name"] for t in picked)
        return [(by_name[n], "qloo", why) for n in keep if n in by_name][:4]

    def from_ai():
        try:
            names = llm.complete_json(SWAP_SYSTEM, json.dumps({"audience": audience.describe(), "line": line, "reference": ref.surface, "type": ref.type, "role": ref.role})).get("candidates", [])
        except Exception:
            return []

        def res(n):
            try:
                hits = qloo.search(n, types=[ref.type], take=1)
            except qloo.QlooError:
                return None
            if hits and qloo.eid(hits[0]) != ref.entity_id and _similar(n, hits[0].get("name", "")):
                return (hits[0], "ai", "suggested by the model, checked by Qloo")
            return None

        return [x for x in qloo.pmap(res, names[:6]) if x]

    for found in qloo.pmap(lambda f: f(), [from_qloo, from_ai], workers=2):
        for e, src, why in found:
            pool.setdefault(qloo.eid(e), (e, src, why))
    if not pool:
        return []
    demo = qloo.demographics(list(pool))
    items = [{"entity_id": ref.entity_id, "type": ref.type, "popularity": ref.popularity, "age_skew": ref.age_skew, "gender_skew": ref.gender_skew}]
    items += [{"entity_id": k, "type": ref.type, "popularity": e.get("popularity"), "age_skew": (demo.get(k) or {}).get("age"), "gender_skew": (demo.get(k) or {}).get("gender")} for k, (e, _, _) in pool.items()]
    scored = score_entities(items, audience)  # the original is re-scored in the same calls, so the comparison is like for like
    base = scored.get(ref.entity_id, {}).get("score", current or 0)
    ranked = sorted(((scored[k]["score"], k) for k in pool if k in scored and scored[k]["score"] > base), reverse=True)
    chosen: list[str] = [k for _, k in ranked[:3]]
    # keep at least one Qloo-found stand-in in the top 3 when one qualifies: it is the part a model alone cannot do
    if chosen and not any(pool[k][1] == "qloo" for k in chosen):
        q = next((k for _, k in ranked if pool[k][1] == "qloo"), None)
        if q:
            chosen = chosen[:2] + [q]
    swaps = [Swap(pool[k][0]["name"], k, scored[k]["score"], pool[k][1], pool[k][2]) for k in chosen]
    if swaps:
        try:
            lines = llm.complete_json(REWRITE_SYSTEM, json.dumps({"line": line, "replace": ref.surface, "with": [s.name for s in swaps]}), fast=True).get("lines", [])
            for s, l in zip(swaps, lines):
                s.line = l if isinstance(l, str) else None
        except Exception:
            pass
    return swaps


def _weak(refs: list[Reference], cells: list[dict | None], limit: int = 8) -> list[tuple[Reference, dict]]:
    pairs = [(r, c) for r, c in zip(refs, cells) if c and c["verdict"] in ("risky", "misses")]
    return sorted(pairs, key=lambda p: p[1]["score"])[:limit]


def swaps_for(text: str, audience: Audience, references: list[dict]) -> list[dict]:
    """Second phase of a check: stand-ins for the weak references (as returned by check(..., swaps=False))."""
    refs = [Reference(**{k: v for k, v in r.items() if k in Reference.__dataclass_fields__ and k != "swaps"}) for r in references]
    cells = [{"score": r.score, "verdict": r.verdict} if r.entity_id and r.score is not None else None for r in refs]
    weak = _weak(refs, cells)
    results = qloo.pmap(lambda p: propose_swaps(text, p[0], audience, p[1]["score"]), weak, workers=4)
    by_start = {p[0].start: s for p, s in zip(weak, results)}
    for r in refs:
        r.swaps = by_start.get(r.start, [])
    return [asdict(r) for r in refs]


# ---- public entry points ----------------------------------------------------------------------------


BAND_KEYS = ["any"] + AUDIENCE_AGES


def check(text: str, audience: Audience, swaps: bool = True) -> dict:
    """One audience in detail, plus every age band precomputed for the same gender and place, so the UI can drag
    the room's age without another round trip (location still needs Qloo rank calls; those run here, cached)."""
    import time

    timings = {}
    t = time.time()
    refs = prepare(text)
    timings["prepare"] = round(time.time() - t, 1); t = time.time()
    band_auds = [Audience(None if k == "any" else k, audience.gender, audience.location) for k in BAND_KEYS]
    jobs = [lambda a=a: cells_for(refs, a) for a in band_auds] + [lambda: guesses(refs, band_auds)]
    res = qloo.pmap(lambda f: f(), jobs, workers=8)
    band_cells, band_guess = res[:-1], res[-1]
    bands = {k: [dict(c, llm_guess=(band_guess[i][j] if band_guess and i < len(band_guess) else None)) if c else None for i, c in enumerate(band_cells[j])] for j, k in enumerate(BAND_KEYS)}
    sel = audience.age or "any"
    cell_list = bands[sel]
    timings["score"] = round(time.time() - t, 1); t = time.time()
    for r, c in zip(refs, cell_list):
        if c:
            r.score, r.verdict, r.why, r.affinity, r.llm_guess = c["score"], c["verdict"], c["why"], c["affinity"], c["llm_guess"]
    if swaps:
        weak = _weak(refs, cell_list)
        for (r, c), s in zip(weak, qloo.pmap(lambda p: propose_swaps(text, p[0], audience, p[1]["score"]), weak, workers=4)):
            r.swaps = s
        timings["swaps"] = round(time.time() - t, 1)
    return {
        "timings": timings,
        "audience": asdict(audience) | {"label": audience.label()},
        "summary": _summary(cell_list, len(refs)),
        "references": [asdict(r) for r in refs],
        "bands": bands,
        "band_summaries": {k: _summary(v, len(refs)) for k, v in bands.items()},
        "model": {k: scoring.P[k] for k in ("a", "b", "k_age", "k_gender", "k_loc", "lands", "misses", "calibrated", "source")},
    }


def matrix(text: str, audiences: list[Audience]) -> dict:
    """One text, many audiences: one extraction and resolution, then one score column per audience."""
    refs = prepare(text)
    jobs = [lambda a=a: cells_for(refs, a) for a in audiences] + [lambda: guesses(refs, audiences)]
    results = qloo.pmap(lambda f: f(), jobs, workers=8)
    columns, guess_rows = results[:-1], results[-1]
    cells = []
    for i, r in enumerate(refs):
        row = []
        for j in range(len(audiences)):
            c = dict(columns[j][i]) if columns[j][i] else None
            if c is not None:
                c["llm_guess"] = guess_rows[i][j] if guess_rows and i < len(guess_rows) else None
            row.append(c)
        cells.append(row)
    return {
        "audiences": [asdict(a) | {"label": a.label()} for a in audiences],
        "references": [asdict(r) for r in refs],
        "cells": cells,
        "summaries": [_summary([cells[i][j] for i in range(len(refs))], len(refs)) for j in range(len(audiences))],
    }


def apply_swaps(text: str, picks: list[tuple[Reference, Swap]]) -> str:
    """Apply one stand-in per line, working from the end of the text so earlier offsets stay valid."""
    seen: set[int] = set()
    for ref, s in sorted(picks, key=lambda p: -p[0].start):
        a = text.rfind("\n", 0, ref.start) + 1
        if a in seen:
            continue
        seen.add(a)
        b = text.find("\n", ref.end)
        b = b if b >= 0 else len(text)
        old = text[a:b]
        new = s.line if s.line and s.name in s.line else old[: ref.start - a] + s.name + old[ref.end - a :]
        text = text[:a] + new + text[b:]
    return text


def localise(text: str, audience: Audience, rounds: int = 2) -> dict:
    """The agent loop, made visible: check, apply the best stand-in per weak line, re-check, repeat."""
    steps = []
    first = check(text, audience, swaps=True)
    before = first["summary"]
    current, result = text, first
    for n in range(rounds):
        refs = [Reference(**{k: v for k, v in r.items() if k in Reference.__dataclass_fields__ and k != "swaps"}) for r in result["references"]]
        for r, rd in zip(refs, result["references"]):
            r.swaps = [Swap(**s) for s in rd.get("swaps", [])]
        picks = [(r, r.swaps[0]) for r in refs if r.swaps]
        if not picks:
            steps.append({"round": n + 1, "action": "stop", "detail": "no weak reference has a stand-in that scores higher"})
            break
        new_text = apply_swaps(current, picks)
        steps.append({"round": n + 1, "action": "swap", "swaps": [{"from": r.name or r.surface, "to": s.name, "score_from": r.score, "score_to": s.score, "source": s.source} for r, s in picks]})
        nxt = check(new_text, audience, swaps=(n + 1 < rounds))
        steps.append({"round": n + 1, "action": "recheck", "summary": nxt["summary"]})

        def bad(s):
            return 2 * s["misses"] + s["risky"]

        if bad(nxt["summary"]) >= bad(result["summary"]):
            steps.append({"round": n + 1, "action": "stop", "detail": "the rewrite did not improve on the previous version, so it was not kept"})
            break
        current, result = new_text, nxt
        if bad(result["summary"]) == 0:
            steps.append({"round": n + 1, "action": "stop", "detail": "every checked reference lands"})
            break
    return {"audience": asdict(audience) | {"label": audience.label()}, "original": text, "text": current, "before": before, "after": result["summary"], "steps": steps, "references": result["references"]}


if __name__ == "__main__":
    # offline self-check of the pure parts
    t = "We rented it at Blockbuster.\nBlockbuster again."
    used = []
    assert _locate(t, "Blockbuster", used) == (16, 27), used
    assert _locate(t, "Blockbuster", used) == (29, 40), used
    assert verdict_for(land_score(0.9999, 0.3, 0, None)) == "lands" and verdict_for(land_score(0.9, -0.4, 0, None)) == "misses"
    r1 = Reference("Blockbuster", 16, 27, "brand", "Blockbuster", "", None)
    r2 = Reference("Blockbuster", 29, 40, "brand", "Blockbuster", "", None)
    out = apply_swaps(t, [(r1, Swap("HMV", "x", 80, "ai")), (r2, Swap("HMV", "x", 80, "ai"))])
    assert out == "We rented it at HMV.\nHMV again.", out
    assert Audience("24_and_younger", "female", "Leeds").label() == "under 25, women, Leeds"
    print("ok")
