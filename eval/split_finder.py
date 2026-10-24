"""Split finder: which references change verdict between rooms, on real Qloo data?

The hero demo ("same bit, two rooms") must show splits that are true. This scores a pool of candidate references
(the examples' references, the YouGov entities with the biggest generation gaps, and any extra names) in every age
band and in a set of places, and lists the biggest swings by age and by place. The demo text and the room pair are
chosen from this output, never invented.

Run: python -m eval.split_finder [--places London "St. Louis" "New York" Mumbai] [--extra "Seinfeld:tv_show" ...]
"""
from __future__ import annotations

import argparse
import csv
import json
import os

from server import pipeline, qloo
from server.examples import EXAMPLES

DATA = os.path.join(os.path.dirname(__file__), "data", "yougov_fame.csv")


def pool(extra: list[str], n_yougov: int) -> list[tuple[str, str]]:
    names: list[tuple[str, str]] = []
    for ex in EXAMPLES:
        for r in pipeline.prepare(ex["text"]):
            names.append((r.name or r.query, r.type))
    rows = [r for r in csv.DictReader(open(DATA)) if r.get("fame_millennials") and r.get("fame_babyboomers")]
    rows.sort(key=lambda r: -abs(float(r["fame_millennials"]) - float(r["fame_babyboomers"])))
    names += [(r["name"], r["qloo_type"]) for r in rows[:n_yougov]]
    for e in extra:
        n, _, t = e.partition(":")
        names.append((n, t or "tv_show"))
    seen, out = set(), []
    for n, t in names:
        if (n.lower(), t) not in seen:
            seen.add((n.lower(), t))
            out.append((n, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--places", nargs="*", default=["London", "St. Louis", "New York", "Atlanta", "Glasgow", "Mumbai", "Toronto", "Texas"])
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--yougov", type=int, default=120)
    a = ap.parse_args()
    cands = pool(a.extra, a.yougov)

    def resolve(c):
        hits = qloo.search(c[0], [c[1]], 3)
        h = next((x for x in hits if pipeline._similar(c[0], x.get("name", ""))), None)
        return (c, h) if h else None

    resolved = [x for x in qloo.pmap(resolve, cands, workers=6) if x]
    demo = qloo.demographics([qloo.eid(h) for _, h in resolved])
    items = [{"entity_id": qloo.eid(h), "type": c[1], "popularity": h.get("popularity"), "age_skew": (demo.get(qloo.eid(h)) or {}).get("age"), "gender_skew": None, "name": h.get("name")} for c, h in resolved]
    by_age = {age: pipeline.score_entities(items, pipeline.Audience(age=age)) for age in pipeline.AUDIENCE_AGES}
    by_place = {pl: pipeline.score_entities(items, pipeline.Audience(location=pl)) for pl in a.places}
    rows = []
    for it in items:
        e = it["entity_id"]
        ages = {k: by_age[k][e]["score"] for k in by_age if e in by_age[k]}
        places = {k: by_place[k][e]["score"] for k in by_place if e in by_place[k]}
        rows.append({"name": it["name"], "type": it["type"], "popularity": it["popularity"], "ages": ages, "places": places,
                     "age_swing": round(max(ages.values()) - min(ages.values()), 1) if ages else 0,
                     "young_minus_old": round(ages.get("24_and_younger", 0) - ages.get("55_and_older", 0), 1),
                     "place_swing": round(max(places.values()) - min(places.values()), 1) if places else 0,
                     "verdicts_young_old": (pipeline.verdict_for(ages.get("24_and_younger", 0)), pipeline.verdict_for(ages.get("55_and_older", 0)))})
    flips = [r for r in rows if r["verdicts_young_old"][0] != r["verdicts_young_old"][1]]
    out = {"n": len(rows), "verdict_flips_young_vs_55plus": len(flips), "rows": sorted(rows, key=lambda r: -abs(r["young_minus_old"]))}
    os.makedirs(os.path.join(os.path.dirname(__file__), "out"), exist_ok=True)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "out", "split_finder.json"), "w"), indent=1)
    print(f"{len(rows)} references scored; {len(flips)} change verdict between under 25 and 55+\n")
    print("biggest age splits (under 25 minus 55+):")
    for r in out["rows"][:20]:
        print(f"  {r['name'][:32]:32} {r['type']:9} {r['young_minus_old']:+6.1f}  {r['verdicts_young_old'][0]:>7} vs {r['verdicts_young_old'][1]}")
    print("\nbiggest place swings:")
    for r in sorted(rows, key=lambda r: -r["place_swing"])[:12]:
        best = max(r["places"], key=r["places"].get) if r["places"] else "-"
        worst = min(r["places"], key=r["places"].get) if r["places"] else "-"
        print(f"  {r['name'][:32]:32} {r['place_swing']:5.1f}  best {best} / worst {worst}")


if __name__ == "__main__":
    main()
