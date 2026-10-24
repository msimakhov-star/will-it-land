"""Location sanity: does Qloo's place signal mean what the product says it means?

20 things with a well-known home region are scored (location term only) at home and somewhere far away. A hit is
'stronger at home than away'. The hit rate decides whether location gets a weight in the score (server/scoring.py
k_loc) and whether the UI shows a place box at all (a control that changes nothing is worse than no control).

Run: python -m eval.location_sanity        -> eval/out/location_sanity.json
"""
from __future__ import annotations

import json
import os

from server import pipeline, qloo

CASES = [  # (name, Qloo type, home, away)
    ("Greggs", "brand", "United Kingdom", "United States"),
    ("Irn-Bru", "brand", "Glasgow", "Texas"),
    ("Whataburger", "brand", "Texas", "London"),
    ("Wawa", "brand", "Philadelphia", "London"),
    ("Tim Hortons", "brand", "Toronto", "London"),
    ("In-N-Out Burger", "brand", "Los Angeles", "Glasgow"),
    ("Buc-ee's", "brand", "Texas", "Manchester"),
    ("Tesco", "brand", "United Kingdom", "United States"),
    ("Primark", "brand", "United Kingdom", "United States"),
    ("Chick-fil-A", "brand", "Atlanta", "London"),
    ("Dunkin'", "brand", "Boston", "London"),
    ("Pret A Manger", "brand", "London", "Texas"),
    ("Vegemite", "brand", "Sydney", "Texas"),
    ("Publix", "brand", "Miami", "London"),
    ("Love Island", "tv_show", "United Kingdom", "Texas"),
    ("Coronation Street", "tv_show", "Manchester", "Texas"),
    ("Schitt's Creek", "tv_show", "Toronto", "Mumbai"),
    ("Shah Rukh Khan", "person", "Mumbai", "Texas"),
    ("Stormzy", "artist", "London", "Texas"),
    ("Garth Brooks", "artist", "Nashville", "London"),
]


def main() -> None:
    rows, hits, scored = [], 0, 0
    for name, t, home, away in CASES:
        found = qloo.search(name, [t], 3)
        hit = next((h for h in found if pipeline._similar(name, h.get("name", ""))), None)
        if not hit:
            rows.append({"name": name, "status": "not in Qloo"})
            continue
        item = [{"entity_id": qloo.eid(hit), "type": t, "popularity": hit.get("popularity"), "age_skew": None, "gender_skew": None}]
        h_cell = pipeline.score_entities(item, pipeline.Audience(location=home)).get(qloo.eid(hit), {})
        a_cell = pipeline.score_entities(item, pipeline.Audience(location=away)).get(qloo.eid(hit), {})
        lh, la = h_cell.get("location"), a_cell.get("location")
        row = {"name": name, "type": t, "home": home, "away": away, "loc_home": lh, "loc_away": la}
        if lh is not None and la is not None:
            scored += 1
            row["hit"] = lh > la
            hits += int(lh > la)
        else:
            row["status"] = "no location signal"
        rows.append(row)
        print(f"{name:20} home {home:15} {lh!s:>8}  away {away:15} {la!s:>8}  {'HIT' if row.get('hit') else ('miss' if 'hit' in row else row.get('status'))}")
    out = {"scored": scored, "hits": hits, "hit_rate": round(hits / scored, 3) if scored else None, "rows": rows,
           "decision": ("keep location (k_loc > 0)" if scored >= 15 and hits / scored >= 0.75 else "drop location from the score and hide the place box") if scored else "no data"}
    os.makedirs(os.path.join(os.path.dirname(__file__), "out"), exist_ok=True)
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "out", "location_sanity.json"), "w"), indent=1)
    print(f"\n{hits}/{scored} stronger at home than away -> {out['decision']}")


if __name__ == "__main__":
    main()
