"""Build the ground-truth set: YouGov Ratings "fame" (% of US adults who have heard of X) by generation.

Source: the public JSON behind yougov.com/en-us/ratings pages. Fame is asked on nationally representative
panels every quarter. Crossbreaks available: all, millennials, generationx, babyboomers, men, women.
Writes eval/data/yougov_fame.csv (public survey aggregates, no personal data).

Run: python -m eval.yougov
"""
from __future__ import annotations

import csv
import os
import time

import httpx

API = "https://api-test.yougov.com/public-data/v5/us/search/entity/"
UA = {"User-Agent": "will-it-land-eval/0.1 (hackathon research; contact via github.com/msimakhov-star)"}
CROSSBREAKS = ["all", "millennials", "generationx", "babyboomers", "men", "women"]
# YouGov group slug -> (group uuid, Qloo entity type)
GROUPS = {
    "all-time-tv-shows": ("1327a6ac-1b0e-11e8-accf-0ed5f89f718b", "tv_show"),
    "all-time-movies": ("6c9bacd4-a353-11f0-b6b1-1f382d69a606", "movie"),
    "2024-movies": ("fe1c9727-1532-11f0-902a-25071c7663ad", "movie"),
    "2025-movies": ("fe5cfc2f-1532-11f0-8182-713e6f120c4a", "movie"),
    "all-time-music-artists": ("1327b3f4-1b0e-11e8-accf-0ed5f89f718b", "artist"),
    "pop-artists": ("fba8bfe6-adef-11e9-8bb2-373b0b3b3eb4", "artist"),
    "rap-hiphop-artists": ("fc15d99c-adef-11e9-8bb2-373b0b3b3eb4", "artist"),
    "alternative-indie-music-artists": ("f9dfbfad-adef-11e9-8bb2-373b0b3b3eb4", "artist"),
    "food-snack-brands": ("1327c286-1b0e-11e8-accf-0ed5f89f718b", "brand"),
    "clothing-footwear-brands": ("1327ebb2-1b0e-11e8-accf-0ed5f89f718b", "brand"),
    "car-makers": ("1327c826-1b0e-11e8-accf-0ed5f89f718b", "brand"),
    "socials-apps-websites": ("0cb44e04-adf0-11e9-bdda-4937f7570ba9", "brand"),
    "all-time-actors-actresses": ("f91e6aff-adef-11e9-9161-317b338eee4b", "person"),
    "comedian": ("4b140bbb-e442-11e9-a415-458261136876", "person"),
    "all-time-sports-personalities": ("61377c1a-3e4d-11e8-820c-711139f793f8", "person"),
    "fiction-books": ("c216747d-3eb7-11ea-ad6c-f58df2eb70ac", "book"),
    "radio-programs-podcasts": ("1327c164-1b0e-11e8-accf-0ed5f89f718b", "podcast"),
}
PER_GROUP = 80  # top N by fame (all adults) per group


def fetch(group_uuid: str, crossbreak: str, limit: int, offset: int) -> dict:
    params = {"group": group_uuid, "sort_by": "fame", "limit": limit, "offset": offset}
    if crossbreak != "all":
        params["crossbreak"] = crossbreak
    for attempt in range(3):
        r = httpx.get(API, params=params, headers=UA, timeout=30)
        if r.status_code == 200:
            return r.json()
        time.sleep(1 + attempt)
    r.raise_for_status()
    return {}


def main(out_path: str = os.path.join(os.path.dirname(__file__), "data", "yougov_fame.csv")) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    rows: dict[tuple[str, str], dict] = {}
    for slug, (uuid, qtype) in GROUPS.items():
        for cb in CROSSBREAKS:
            got = 0
            offset = 0
            while got < PER_GROUP:
                data = fetch(uuid, cb, 20, offset)
                items = data.get("data") or []
                if not items:
                    break
                for it in items:
                    rd = it.get("rating_data") or {}
                    key = (slug, it["url"])
                    row = rows.setdefault(key, {"group": slug, "qloo_type": qtype, "name": it["name"], "slug": it["url"]})
                    row[f"fame_{cb}"] = rd.get("fame")
                    row[f"pop_{cb}"] = rd.get("popularity")
                got += len(items)
                offset += len(items)
                time.sleep(0.15)
        print(f"{slug}: {sum(1 for k in rows if k[0] == slug)} entities")
    cols = ["group", "qloo_type", "name", "slug"] + [f"fame_{c}" for c in CROSSBREAKS] + [f"pop_{c}" for c in CROSSBREAKS]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows.values():
            w.writerow(row)
    print("wrote", out_path, len(rows))


if __name__ == "__main__":
    main()
