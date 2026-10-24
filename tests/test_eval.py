"""The calibration must recover known parameters from synthetic data, and the report must be well formed."""
from __future__ import annotations

import json
import math
import random


def test_fit_recovers_parameters(tmp_path, monkeypatch):
    from eval import fit, kill_test
    from server import scoring

    monkeypatch.setattr(kill_test, "OUT", str(tmp_path))
    monkeypatch.setattr(fit, "OUT", str(tmp_path))
    rng = random.Random(3)
    true = {"a": -2.0, "b": 1.3, "k_age": 2.5}
    ents, demo = [], {}
    for i in range(240):
        pop = 1 - 10 ** (-rng.uniform(1.0, 4.0))
        young, old = rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6)
        age = {"24_and_younger": young, "25_to_29": young, "30_to_34": young, "35_to_44": young, "45_to_54": old, "55_and_older": old}
        row = {"slug": f"e{i}", "group": "g", "qloo_id": f"id{i}", "qloo_pop": pop}
        for gen, buckets in kill_test.GEN_BUCKETS.items():
            aff = sum(age[b] for b in buckets) / len(buckets)
            z = true["a"] + true["b"] * scoring.rarity(pop) + true["k_age"] * aff
            row[f"fame_{gen}"] = round(100 / (1 + math.exp(-z)) + rng.gauss(0, 1.0), 1)
            row[f"llm_{gen}"] = rng.uniform(0, 100)  # a guesser with no information
        ents.append(row)
        demo[f"id{i}"] = {"age": age}
    json.dump(ents, open(tmp_path / "kill_test_rows.json", "w"))
    monkeypatch.setattr(fit.qloo, "demographics", lambda ids: demo)
    monkeypatch.setattr("sys.argv", ["fit"])
    fit.main()
    rep = json.load(open(tmp_path / "fit_report.json"))
    assert abs(rep["fitted"]["b"] - true["b"]) < 0.25 and abs(rep["fitted"]["k_age"] - true["k_age"]) < 0.6
    assert rep["pooled"]["qloo"] > 0.8 > abs(rep["pooled"]["llm"])
    assert rep["pooled"]["qloo"] > rep["pooled"]["no_age"]
    assert rep["gap"]["qloo"] > 0.5 and rep["gap"]["n"] == 240
