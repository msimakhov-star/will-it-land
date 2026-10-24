"""Freshness: things a room loves right now that a language model cannot know (released after its training data).

For each young room, ask Qloo for films and TV shows released this year that the room over-indexes on, then ask the
model, with no data, how likely that room is to know each one and whether it knows the title at all. Cases where Qloo
rates a title highly and the model does not know it are the plainest evidence of what grounding adds.
Published only if there are at least 5 clean cases (see eval/PREREG.md); otherwise dropped.

Run: python -m eval.freshness [--year 2026]
"""
from __future__ import annotations

import argparse
import json
import os

from server import llm, qloo

DATA_SOURCE = "mock" if os.environ.get("QLOO_MOCK") else "live"
ROOMS = [("24_and_younger", "London"), ("24_and_younger", "New York"), ("25_to_29", "Atlanta")]
ASK = """For each title, say whether you know it at all and estimate what percentage (0 to 100) of the given audience
would recognise it. Do not guess details you do not know. Return {"items": [{"title": ..., "known": true|false, "guess": <0-100>}, ...]} in order."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    a = ap.parse_args()
    found = []
    for age, place in ROOMS:
        for t in ("movie", "tv_show"):
            params = {"filter.type": f"urn:entity:{t}", "signal.demographics.age": age, "signal.location.query": place, "filter.release_year.min": a.year, "take": 15}
            try:
                ents = qloo._entities(qloo.get("/v2/insights", params))
            except qloo.QlooError as ex:
                print("insights failed", t, age, place, ex)
                continue
            for e in ents:
                if e.get("name"):
                    found.append({"room": f"{age} {place}", "type": t, "name": e["name"], "affinity": qloo.affinity(e), "popularity": e.get("popularity"), "year": (e.get("properties") or {}).get("release_year")})
    rows = []
    for room in sorted({f["room"] for f in found}):
        batch = [f for f in found if f["room"] == room]
        try:
            ans = llm.complete_json(ASK, json.dumps({"audience": room.replace("_", " "), "titles": [f["name"] for f in batch]})).get("items", [])
        except Exception:
            ans = []
        for f, x in zip(batch, ans):
            rows.append({**f, "llm_known": bool(x.get("known")) if isinstance(x, dict) else None, "llm_guess": x.get("guess") if isinstance(x, dict) else None})
    clean = [r for r in rows if r["llm_known"] is False and (r["affinity"] or 0) >= 0.5]
    out = {"data_source": DATA_SOURCE, "year": a.year, "titles": len(rows), "unknown_to_model": sum(1 for r in rows if r["llm_known"] is False), "clean_cases": clean[:20], "publish": len(clean) >= 5, "rows": rows}
    os.makedirs(os.path.join(os.path.dirname(__file__), "out"), exist_ok=True)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "out", "freshness.json"), "w"), indent=1)
    print(f"{len(rows)} titles from {a.year}; the model says it does not know {out['unknown_to_model']}; clean cases: {len(clean)} -> {'publish' if out['publish'] else 'drop'}")
    for r in clean[:10]:
        print(f"  {r['name']} ({r['type']}, {r['room']}): Qloo affinity {r['affinity']}")


if __name__ == "__main__":
    main()
