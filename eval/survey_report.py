"""Survey report: does the Qloo-grounded score track what real young people recognise, better than an AI guess?

Reads responses (from the deployed app's token-protected export, or a local JSON file), keeps respondents aged
18 to 24 (and optionally one city), computes each item's recognition rate, and compares it with:
  qloo  Will It Land's score for the room (24_and_younger [+ city])
  llm   the language model's unaided guess for the same room
Reports Spearman for both, n, and which references the models picked "for under-25s" that fewer than half of real
under-25 respondents recognised. Published whatever it says (see eval/PREREG.md, Survey section).

Run: python -m eval.survey_report --url https://<app>/api/survey/export?token=$SURVEY_TOKEN [--city London]
"""
from __future__ import annotations

import argparse
import json
import os

import httpx

from eval.kill_test import spearman
from server import pipeline, qloo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--file")
    ap.add_argument("--city", default=None)
    ap.add_argument("--min-n", type=int, default=5)
    a = ap.parse_args()
    data = json.load(open(a.file)) if a.file else httpx.get(a.url, timeout=60, trust_env=False).json()
    items = {i["id"]: i for i in data["items"]}
    resp = [r for r in data["responses"] if r["age"] == "18_to_24" and (not a.city or r["city"].strip().lower() == a.city.lower())]
    rate = {}
    for iid in items:
        votes = [r["answers"][iid] for r in resp if iid in r["answers"]]
        if len(votes) >= a.min_n:
            rate[iid] = 100 * sum(votes) / len(votes)
    room = pipeline.Audience("24_and_younger", None, a.city)
    names = [(iid, items[iid]) for iid in rate]

    def resolve(x):
        iid, it = x
        hits = qloo.search(it["name"], [it["type"]], 3)
        h = next((y for y in hits if pipeline._similar(it["name"], y.get("name", ""))), None)
        return (iid, h, it) if h else None

    found = [x for x in qloo.pmap(resolve, names, workers=6) if x]
    demo = qloo.demographics([qloo.eid(h) for _, h, _ in found])
    ents = [{"entity_id": qloo.eid(h), "type": it["type"], "popularity": h.get("popularity"), "age_skew": (demo.get(qloo.eid(h)) or {}).get("age"), "gender_skew": None} for _, h, it in found]
    scores = pipeline.score_entities(ents, room)
    refs = [pipeline.Reference(it["name"], 0, 0, it["type"], it["name"], "", None, entity_id=qloo.eid(h), name=it["name"]) for _, h, it in found]
    g = pipeline.guesses(refs, [room])
    rows = [{"name": it["name"], "recognised": round(rate[iid], 1), "qloo": scores[qloo.eid(h)]["score"], "llm": (g[k][0] if g and k < len(g) else None)} for k, (iid, h, it) in enumerate(found)]
    ok = [r for r in rows if r["llm"] is not None]
    out = {"respondents": len(resp), "items": len(ok),
           "spearman_qloo": round(spearman([r["qloo"] for r in ok], [r["recognised"] for r in ok]), 3) if len(ok) > 2 else None,
           "spearman_llm": round(spearman([r["llm"] for r in ok], [r["recognised"] for r in ok]), 3) if len(ok) > 2 else None,
           "ai_picks_most_did_not_know": sorted([r["name"] for r in rows if r["recognised"] < 50]), "rows": sorted(rows, key=lambda r: r["recognised"])}
    os.makedirs(os.path.join(os.path.dirname(__file__), "out"), exist_ok=True)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "out", "survey_report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
