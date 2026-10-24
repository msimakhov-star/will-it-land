"""Warm a deployed Will It Land through its public API, so judges (and the live final) hit cached answers.

Calls /api/matrix for every example against its own rooms and against pairs of (age band x city) from CITIES, plus
/api/localise_all for the examples' default rooms. Location costs one Qloo call per city per entity type, age bands
cost nothing extra, so this stays cheap. Respects the server's rate guard by pacing requests.

Run: python -m tools.prewarm --base https://m-simakhov--will-it-land-web.us-east.modal.run [--cities London "St. Louis" ...]
"""
from __future__ import annotations

import argparse
import itertools
import time

import httpx

from server.examples import EXAMPLES

CITIES = ["London", "St. Louis", "New York", "Los Angeles", "Atlanta", "Austin", "Texas", "Glasgow", "Manchester", "Toronto", "Mumbai", "United States", "United Kingdom"]
AGES = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--cities", nargs="*", default=CITIES)
    ap.add_argument("--pace", type=float, default=10.5, help="seconds between requests (rate guard is 60 per 10 min per IP)")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base.rstrip("/"), timeout=300, trust_env=False)
    jobs = []
    for ex in EXAMPLES:
        rooms = ex.get("matrix") or [ex["audience"]]
        jobs.append(("matrix", {"text": ex["text"], "audiences": rooms}))
        jobs.append(("localise_all", {"text": ex["text"], "audiences": rooms}))
    stand = EXAMPLES[0]["text"]
    for city in a.cities:  # one location rank call per city covers all six bands
        jobs.append(("matrix", {"text": stand, "audiences": [{"age": "24_and_younger", "location": city}, {"age": "55_and_older", "location": city}]}))
    for young, old in itertools.islice(itertools.product(["24_and_younger", "25_to_29"], ["45_to_54", "55_and_older"]), 4):
        jobs.append(("matrix", {"text": stand, "audiences": [{"age": young, "location": "London"}, {"age": old, "location": "St. Louis"}]}))
    print(f"{len(jobs)} requests, about {len(jobs) * a.pace / 60:.0f} min")
    for i, (ep, body) in enumerate(jobs, 1):
        t = time.time()
        r = c.post(f"/api/{ep}", json=body)
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        print(f"[{i}/{len(jobs)}] {ep:13} {r.status_code} {time.time() - t:5.1f}s qloo_calls={d.get('ledger', {}).get('total')} live={d.get('ledger', {}).get('live')}")
        time.sleep(max(0.0, a.pace - (time.time() - t)))


if __name__ == "__main__":
    main()
