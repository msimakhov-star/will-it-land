"""Calibrate the 'likely to land' model (server/scoring.py) against YouGov fame by generation, with 5-fold CV.

Model on the logit scale:  logit(fame_gen / 100) ~ a + b * rarity(popularity) + k_age * age_affinity(gen)
Fitted by least squares (no numpy). Reports out-of-fold Spearman for:
  qloo      the fitted Qloo model
  llm       the cached LLM-only guess (eval/out/llm_guesses.json)
  blend     average of the two ranks' z-scores (does grounding add to the model?)
  no_age    ablation: Qloo model without age affinity (does the age signal carry weight?)
and the same on the millennial-minus-boomer gap (what an audience switch changes).
Writes server/calibration.json only with --write (the numbers in the README must match what was written).

Run after kill_test (needs eval/out/kill_test_rows.json): python -m eval.fit [--write]
"""
from __future__ import annotations

import argparse
import json
import math
import os

DATA_SOURCE = "mock" if os.environ.get("QLOO_MOCK") else "live"
import random

from eval.kill_test import GEN_BUCKETS, OUT, spearman
from server import qloo, scoring

GENS = ["millennials", "generationx", "babyboomers"]


def lstsq(X: list[list[float]], y: list[float], ridge: float = 1e-6) -> list[float]:
    """Solve (X^T X + ridge I) w = X^T y by Gaussian elimination."""
    n = len(X[0])
    A = [[sum(X[k][i] * X[k][j] for k in range(len(X))) + (ridge if i == j else 0) for j in range(n)] for i in range(n)]
    b = [sum(X[k][i] * y[k] for k in range(len(X))) for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        for r in range(i + 1, n):
            f = A[r][i] / A[i][i]
            for c in range(i, n):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    w = [0.0] * n
    for i in range(n - 1, -1, -1):
        w[i] = (b[i] - sum(A[i][c] * w[c] for c in range(i + 1, n))) / A[i][i]
    return w


def logit(pct: float) -> float:
    p = min(max(pct / 100.0, 0.01), 0.99)
    return math.log(p / (1 - p))


def zscores(v: list[float]) -> list[float]:
    m = sum(v) / len(v)
    sd = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5 or 1.0
    return [(x - m) / sd for x in v]


def rows_for(entities: list[dict], demo: dict) -> list[dict]:
    out = []
    for r in entities:
        age = demo.get(r["qloo_id"], {}).get("age") or {}
        for gen in GENS:
            aff = sum(float(age.get(b, 0) or 0) for b in GEN_BUCKETS[gen]) / len(GEN_BUCKETS[gen])
            out.append({"ent": r["slug"], "gen": gen, "r": scoring.rarity(r["qloo_pop"]), "age": aff, "fame": float(r[f"fame_{gen}"]), "llm": r.get(f"llm_{gen}")})
    return out


def fit(train: list[dict], use_age: bool = True) -> list[float]:
    X = [[1.0, t["r"], t["age"]] if use_age else [1.0, t["r"]] for t in train]
    return lstsq(X, [logit(t["fame"]) for t in train])


def predict(w: list[float], t: dict) -> float:
    z = w[0] + w[1] * t["r"] + (w[2] * t["age"] if len(w) > 2 else 0.0)
    return 100 * scoring.sigmoid(z)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write server/calibration.json from the full-data fit")
    ap.add_argument("--folds", type=int, default=5)
    a = ap.parse_args()
    ents = [r for r in json.load(open(os.path.join(OUT, "kill_test_rows.json")))
            if r.get("qloo_id") and r.get("qloo_pop") is not None and all(r.get(f"fame_{g}") not in (None, "") and r.get(f"llm_{g}") is not None for g in GENS)]
    demo = qloo.demographics([r["qloo_id"] for r in ents])  # cached from the kill test
    random.Random(11).shuffle(ents)
    folds = [ents[i :: a.folds] for i in range(a.folds)]
    preds = {"qloo": {}, "no_age": {}}
    for k in range(a.folds):
        test = rows_for(folds[k], demo)
        train = rows_for([e for j, f in enumerate(folds) if j != k for e in f], demo)
        w_full, w_noage = fit(train, True), fit(train, False)
        for t in test:
            preds["qloo"][(t["ent"], t["gen"])] = predict(w_full, t)
            preds["no_age"][(t["ent"], t["gen"])] = predict(w_noage, t)
    allrows = rows_for(ents, demo)
    keys = [(t["ent"], t["gen"]) for t in allrows]
    truth = [t["fame"] for t in allrows]
    llm = [float(t["llm"]) for t in allrows]
    q = [preds["qloo"][k] for k in keys]
    blend = [x + y for x, y in zip(zscores(q), zscores(llm))]
    report = {"data_source": DATA_SOURCE, "n_entities": len(ents), "n_rows": len(allrows), "pooled": {}, "gap": {}}
    for name, v in (("qloo", q), ("no_age", [preds["no_age"][k] for k in keys]), ("llm", llm), ("blend", blend)):
        report["pooled"][name] = round(spearman(v, truth), 3)
    # millennial minus boomer gap, per entity
    by = {}
    for t, k in zip(allrows, keys):
        by.setdefault(t["ent"], {})[t["gen"]] = (t["fame"], preds["qloo"][k], float(t["llm"]))
    g_truth, g_q, g_llm = [], [], []
    for e, d in by.items():
        if "millennials" in d and "babyboomers" in d:
            g_truth.append(d["millennials"][0] - d["babyboomers"][0])
            g_q.append(d["millennials"][1] - d["babyboomers"][1])
            g_llm.append(d["millennials"][2] - d["babyboomers"][2])
    report["gap"] = {"qloo": round(spearman(g_q, g_truth), 3), "llm": round(spearman(g_llm, g_truth), 3), "n": len(g_truth)}
    w = fit(allrows, True)
    report["fitted"] = {"a": round(w[0], 4), "b": round(w[1], 4), "k_age": round(w[2], 4)}
    print(json.dumps(report, indent=1))
    os.makedirs(OUT, exist_ok=True)
    json.dump(report, open(os.path.join(OUT, "fit_report.json"), "w"), indent=1)
    if a.write:
        cal = scoring.params()  # keep location settings written by eval/location_sanity.py
        cal.update(report["fitted"])
        cal.update({"calibrated": True, "source": f"fitted on {len(ents)} YouGov entities x 3 generations, 5-fold CV Spearman {report['pooled']['qloo']}"})
        json.dump(cal, open(os.path.join(os.path.dirname(scoring.__file__), "calibration.json"), "w"), indent=1)
        print("wrote server/calibration.json")


if __name__ == "__main__":
    assert [round(v, 6) for v in lstsq([[1, 0], [1, 1], [1, 2]], [1, 3, 5], ridge=0)] == [1.0, 2.0]
    main()
