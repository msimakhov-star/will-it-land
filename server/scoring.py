"""The 'likely to land' model, in one place so it can be calibrated and explained.

    rarity  r = -log10(1 - popularity)      popularity 0.9 -> 1, 0.99 -> 2, 0.999 -> 3, 0.9999 -> 4
    logit   z = a + b*r + k_age*age_affinity + k_gender*gender_affinity + k_loc*location + k_seg*segment
    score     = 100 * sigmoid(z)

Why a log transform: Qloo popularity is a percentile over a very large catalogue, so nearly anything a writer
names sits above 0.9; a linear 100*popularity base saturates and calls every famous-but-dated reference a hit.
Defaults below are hand-set priors (UNCALIBRATED) until eval/fit.py fits them against YouGov "fame by generation"
and writes server/calibration.json, which is loaded if present.
"""
from __future__ import annotations

import json
import math
import os

DEFAULTS = {"a": -2.3, "b": 1.17, "k_age": 3.0, "k_gender": 1.5, "k_loc": 2.0, "k_seg": 2.0, "lands": 60.0, "misses": 35.0, "calibrated": False, "loc_measured": False, "seg_measured": False, "source": "hand-set priors"}
_PATH = os.path.join(os.path.dirname(__file__), "calibration.json")


def params() -> dict:
    p = dict(DEFAULTS)
    if os.path.exists(_PATH):
        try:
            p.update(json.load(open(_PATH)))
        except Exception:
            pass
    return p


P = params()


def rarity(popularity: float | None) -> float:
    pop = 0.9 if popularity is None else min(max(float(popularity), 0.0), 0.99999)
    return -math.log10(1 - pop)


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def components(popularity: float | None, age_aff: float = 0.0, gender_aff: float = 0.0, loc: float | None = None, p: dict | None = None, seg: float | None = None) -> dict:
    """Score plus a sequential breakdown in points (base, then age, gender, location, audience segment), for the evidence waterfall."""
    p = p or P
    z = p["a"] + p["b"] * rarity(popularity)
    base = 100 * sigmoid(z)
    out = {"base": round(base, 1)}
    prev = base
    for key, k, v in (("age", "k_age", age_aff), ("gender", "k_gender", gender_aff), ("location", "k_loc", loc if loc is not None else 0.0), ("segment", "k_seg", seg if seg is not None else 0.0)):
        z += p.get(k, 0.0) * (v or 0.0)
        now = 100 * sigmoid(z)
        out[key] = round(now - prev, 1)
        prev = now
    out["score"] = round(prev, 1)
    return out


def score(popularity: float | None, age_aff: float = 0.0, gender_aff: float = 0.0, loc: float | None = None, seg: float | None = None) -> float:
    return components(popularity, age_aff, gender_aff, loc, seg=seg)["score"]


def verdict(s: float) -> str:
    return "lands" if s >= P["lands"] else "risky" if s >= P["misses"] else "misses"


if __name__ == "__main__":
    # the bug this module exists to fix: a famous-but-dated reference must be able to miss
    assert verdict(score(0.995, -0.5)) != "lands", score(0.995, -0.5)
    assert score(0.9999, 0.3) > score(0.9999, -0.3) > score(0.99, -0.3)
    c = components(0.999, -0.4, 0.1, 0.2)
    assert abs(c["base"] + c["age"] + c["gender"] + c["location"] + c["segment"] - c["score"]) < 0.3
    assert score(0.999, seg=0.4) > score(0.999) > score(0.999, seg=-0.4)
    assert 0 <= score(None) <= 100 and score(1.0) <= 100
    print("ok", P["source"], {k: round(score(k), 1) for k in (0.9, 0.99, 0.999, 0.9999)})
