"""Key-day probe: one call per Qloo endpoint the app uses, print the raw response keys, and assert every field the
parsers read. First command once QLOO_API_KEY is set; runs on the mock too (QLOO_MOCK=1) as a self-check.

Run: QLOO_API_KEY=... python -m tools.probe          (exit code 1 if any contract assumption fails)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

from server import qloo

failures: list[str] = []


def show(label: str, data) -> None:
    txt = json.dumps(data)[:700]
    print(f"\n== {label}\n{txt}")


def expect(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


def keys(d) -> list[str]:
    return sorted(d.keys()) if isinstance(d, dict) else []


def main() -> int:
    print("base:", qloo.BASE_URL, "| key set:", bool(os.environ.get("QLOO_API_KEY")), "| mock:", bool(os.environ.get("QLOO_MOCK")))

    # 1. /search
    raw = qloo.get("/search", {"query": "Seinfeld", "types": "urn:entity:tv_show", "take": 6})
    show("/search Seinfeld", raw)
    hits = qloo.search("Seinfeld", ["tv_show"], 6)
    expect(bool(hits), "/search returns at least one hit for Seinfeld")
    h = hits[0] if hits else {}
    expect(bool(qloo.eid(h)), f"search hit has entity_id or id (keys: {keys(h)})")
    expect(isinstance(h.get("popularity"), (int, float)), f"search hit has numeric popularity (got {h.get('popularity')!r})")
    if isinstance(h.get("popularity"), (int, float)):
        print(f"  info popularity(Seinfeld) = {h['popularity']}  (scoring.rarity -> {__import__('server.scoring', fromlist=['x']).rarity(h['popularity']):.2f})")
    miss = qloo.search("Zzqxv Nonexistent Show Name", ["tv_show"], 3)
    expect(isinstance(miss, list), "a /search miss returns an empty list, not an error")

    ids = [qloo.eid(x) for x in (qloo.search("Euphoria", ["tv_show"], 1) + hits[:1]) if qloo.eid(x)]

    # 2. urn:demographics, batched
    raw = qloo.get("/v2/insights", {"filter.type": "urn:demographics", "signal.interests.entities": ids})
    show("urn:demographics (2 entities in one call)", raw)
    demo = qloo.demographics(ids)
    expect(len(demo) == len(set(ids)), f"one demographics row per entity in a batch ({len(demo)} rows for {len(set(ids))} ids)")
    row = next(iter(demo.values()), {})
    expect(set((row.get("age") or {}).keys()) >= set(qloo.AGE_BUCKETS), f"age buckets present (got {keys(row.get('age'))})")
    expect(set((row.get("gender") or {}).keys()) >= {"male", "female"}, f"gender keys present (got {keys(row.get('gender'))})")

    # 3. location-only rank with filter.results.entities
    anchors = [qloo.eid(qloo.search(n, ["tv_show"], 1)[0]) for n in ("Friends", "The Simpsons", "Breaking Bad", "Twin Peaks") if qloo.search(n, ["tv_show"], 1)]
    raw = qloo.get("/v2/insights", {"filter.type": "urn:entity:tv_show", "filter.results.entities": ids + anchors, "take": len(ids + anchors), "signal.location.query": "London"})
    show("rank in place (location only)", raw)
    ranked = qloo.rank_for_audience(ids + anchors, "tv_show", location="London")
    expect(len(ranked) >= len(set(ids + anchors)) - 1, f"rank returns an affinity for (nearly) every requested entity ({len(ranked)}/{len(set(ids + anchors))})")
    other = qloo.rank_for_audience(ids + anchors, "tv_show", location="Mumbai")
    differs = any(abs(ranked.get(k, 0) - other.get(k, 0)) > 1e-6 for k in ranked)
    expect(differs, "affinities differ between London and Mumbai (location actually changes the answer)")
    bad = None
    try:
        qloo.rank_for_audience(ids, "tv_show", location="Qzxqzx Nowhere")
    except qloo.QlooError as ex:
        bad = str(ex)
    print(f"  info unknown place -> {bad or 'no error (empty or ignored)'}")

    # 4. tags of an entity
    raw = qloo.get("/v2/insights", {"filter.type": "urn:tag", "signal.interests.entities": ids[:1], "take": 8})
    show("urn:tag for Seinfeld", raw)
    tags = qloo.entity_tags(ids[:1], 8)
    expect(bool(tags) and all(t["tag_id"] and t["name"] for t in tags), f"tags parse to tag_id + name ({len(tags)} tags)")

    # 5. recommend from tags + room, with the stand-in popularity floor and explainability
    if tags:
        params = {"filter.type": "urn:entity:tv_show", "signal.interests.entities": ids[:1], "signal.interests.tags": [t["tag_id"] for t in tags[:3]], "operator.signal.interests.tags": "union",
                  "signal.demographics.age": "24_and_younger", "signal.location.query": "London", "filter.popularity.min": 0.99, "take": 10, "feature.explainability": "true"}
        raw = qloo.get("/v2/insights", params)
        show("recommend (tags + under 25 + London, popularity >= 0.99, explainability)", raw)
        ents = qloo.recommend("tv_show", signal_entities=ids[:1], signal_tags=[t["tag_id"] for t in tags[:3]], age="24_and_younger", location="London", min_popularity=0.99, take=10)
        expect(bool(ents), f"recommend returns candidates with the 0.99 floor ({len(ents)})")
        if ents:
            print(f"  info first candidates: {[e.get('name') for e in ents[:6]]}; popularity {[e.get('popularity') for e in ents[:3]]}")
            ex = (ents[0].get("query") or {}).get("explainability")
            print(f"  info explainability present: {bool(ex)}")

    # 6. trending
    end = dt.date.today()
    rows = qloo.trending(ids[0], "tv_show", (end - dt.timedelta(days=180)).isoformat(), end.isoformat()) if ids else []
    show("trending (6 months)", rows[:3])
    expect(bool(rows), f"trending returns weekly rows ({len(rows)})")
    if rows:
        expect(all(k in rows[-1] for k in ("population_percentile", "population_rank_velocity")), f"trending fields the UI reads exist (got {keys(rows[-1])})")

    # 7. audience segments: list them, then rank our entities for one (the "Qloo audience" room)
    try:
        raw = qloo.get("/v2/audiences/types", {})
        show("/v2/audiences/types", raw)
        types = qloo.segment_types()
        raw = qloo.get("/v2/audiences", {"take": 10, **({"filter.parents.types": types[0]} if types else {})})
        show("/v2/audiences (first type)", raw)
        segs = qloo.segments(types[0] if types else None, take=10)
    except qloo.QlooError as ex:
        print(f"  info audiences unavailable: {ex}")
        segs = []
    expect(bool(segs) and all(x["id"] and x["name"] for x in segs), f"audience segments parse to id + name ({len(segs)}); if this fails set k_seg to 0 in calibration.json")
    if segs:
        r1 = qloo.rank_for_audience(ids + anchors, "tv_show", audiences=[segs[0]["id"]])
        r2 = qloo.rank_for_audience(ids + anchors, "tv_show", audiences=[segs[-1]["id"]])
        expect(len(r1) >= len(set(ids + anchors)) - 1, f"rank with signal.demographics.audiences returns affinities ({len(r1)})")
        expect(any(abs(r1.get(k, 0) - r2.get(k, 0)) > 1e-6 for k in r1), f"affinities differ between {segs[0]['name']} and {segs[-1]['name']} (the segment changes the answer)")

    print("\n" + ("ALL CONTRACT CHECKS PASSED" if not failures else f"{len(failures)} FAILED:\n  - " + "\n  - ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
