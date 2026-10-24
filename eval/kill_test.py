"""Kill test: does a Qloo-grounded score predict who has actually heard of a reference better than an LLM guessing alone?

Ground truth: eval/data/yougov_fame.csv (YouGov Ratings fame % by generation; see eval/yougov.py).
For a sample of entities we compute:
  qloo_score(gen)  = land_score(popularity, age_affinity for that generation's Qloo buckets)
  llm_guess(gen)   = the LLM's own estimate of fame % for that generation, no data (batched prompt)
and report Spearman rank correlations with YouGov fame, overall and for the millennial-minus-boomer gap
(the gap is the part that matters for an audience switch). Numbers go in the README whatever they are.

Run: QLOO_API_KEY=... python -m eval.kill_test --n 300
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor

from server import llm, pipeline, qloo

GEN_BUCKETS = {"millennials": ["30_to_34", "35_to_44"], "generationx": ["45_to_54", "55_and_older"], "babyboomers": ["55_and_older"]}
DATA = os.path.join(os.path.dirname(__file__), "data", "yougov_fame.csv")
OUT = os.path.join(os.path.dirname(__file__), "out")


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


def load(n: int, seed: int) -> list[dict]:
    """Balanced across entity types. Within each type, half the slots are random and half come from the top quarter
    by |millennial minus boomer| fame gap, so the generation-skewed references the product exists to catch are in the test."""
    rows = [r for r in csv.DictReader(open(DATA)) if r.get("fame_millennials") and r.get("fame_babyboomers") and r.get("fame_all")]
    rng = random.Random(seed)
    by_type: dict[str, list] = {}
    for r in rows:
        by_type.setdefault(r["qloo_type"], []).append(r)
    per = max(2, n // len(by_type))
    out = []
    for t in sorted(by_type):
        rs = by_type[t][:]
        rng.shuffle(rs)
        gap = sorted(rs, key=lambda r: -abs(float(r["fame_millennials"]) - float(r["fame_babyboomers"])))
        skewed = gap[: max(1, len(gap) // 4)][: per // 2]
        keys = {(r["group"], r["slug"]) for r in skewed}
        rest = [r for r in rs if (r["group"], r["slug"]) not in keys][: per - len(skewed)]
        out += skewed + rest
    return out[:n]


def qloo_side(rows: list[dict]) -> None:
    def one(r):
        try:
            hits = qloo.search(r["name"], types=[r["qloo_type"]], take=3)
        except qloo.QlooError as ex:  # one bad row must not sink a 300-row run
            print("search failed", r["name"], ex)
            hits = []
        hit = next((h for h in hits if pipeline._similar(r["name"], h.get("name", ""))), None)
        r["qloo_id"] = hit.get("entity_id") if hit else None
        r["qloo_pop"] = hit.get("popularity") if hit else None

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, rows))
    ids = [r["qloo_id"] for r in rows if r["qloo_id"]]
    try:
        demo = qloo.demographics(ids)
    except qloo.QlooError as ex:
        print("demographics failed", ex)
        demo = {}
    for r in rows:
        d = demo.get(r.get("qloo_id") or "", {}).get("age") or {}
        for gen, buckets in GEN_BUCKETS.items():
            aff = sum(float(d.get(b, 0) or 0) for b in buckets) / len(buckets)
            r[f"qloo_{gen}"] = pipeline.land_score(r["qloo_pop"], aff, 0.0, None) if r["qloo_id"] else None


def llm_side(rows: list[dict]) -> None:
    """LLM guesses are cached in eval/out/llm_guesses.json so the Qloo run later does not repeat them."""
    cache_path = os.path.join(OUT, "llm_guesses.json")
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [r for r in rows if f"{r['group']}/{r['slug']}" not in cache]
    _llm_guess(todo)
    for r in todo:
        if r.get("llm_millennials") is not None:
            cache[f"{r['group']}/{r['slug']}"] = {g: r[f"llm_{g}"] for g in GEN_BUCKETS}
    os.makedirs(OUT, exist_ok=True)
    json.dump(cache, open(cache_path, "w"))
    for r in rows:
        c = cache.get(f"{r['group']}/{r['slug']}")
        for g in GEN_BUCKETS:
            r[f"llm_{g}"] = c[g] if c else None


def _llm_guess(rows: list[dict]) -> None:
    system = ("For each named thing, estimate the percentage of US adults in each generation who have HEARD OF it "
              "(fame, not liking). Generations: millennials (born 1981-1996), generationx (1965-1980), babyboomers (1946-1964). "
              'Return {"items": [{"name": ..., "millennials": <0-100>, "generationx": <0-100>, "babyboomers": <0-100>}, ...]} in the same order.')
    for i in range(0, len(rows), 40):
        batch = rows[i : i + 40]
        try:
            out = llm.complete_json(system, json.dumps([{"name": r["name"], "type": r["qloo_type"]} for r in batch]), max_tokens=6000)
            items = out.get("items", [])
        except Exception as ex:
            print("llm batch failed", ex)
            items = []
        for r, it in zip(batch, items):
            for gen in GEN_BUCKETS:
                r[f"llm_{gen}"] = float(it.get(gen)) if isinstance(it, dict) and it.get(gen) is not None else None


def report(rows: list[dict]) -> str:
    ok = [r for r in rows if r.get("qloo_id") and r.get("llm_millennials") is not None]
    lines = [f"entities sampled: {len(rows)}; resolved in Qloo: {sum(1 for r in rows if r.get('qloo_id'))}; used: {len(ok)}", ""]
    lines.append("| target | Qloo-grounded score | LLM guess alone |")
    lines.append("|---|---|---|")
    for gen in ("millennials", "babyboomers"):
        truth = [float(r[f"fame_{gen}"]) for r in ok]
        lines.append(f"| fame among {gen} | {spearman([r[f'qloo_{gen}'] for r in ok], truth):.2f} | {spearman([r[f'llm_{gen}'] for r in ok], truth):.2f} |")
    truth_gap = [float(r["fame_millennials"]) - float(r["fame_babyboomers"]) for r in ok]
    lines.append(f"| millennial minus boomer gap | {spearman([r['qloo_millennials'] - r['qloo_babyboomers'] for r in ok], truth_gap):.2f} | {spearman([r['llm_millennials'] - r['llm_babyboomers'] for r in ok], truth_gap):.2f} |")
    pop_only = [float(r["qloo_pop"] or 0) for r in ok]
    lines.append(f"| fame among all adults, Qloo popularity only | {spearman(pop_only, [float(r['fame_all']) for r in ok]):.2f} | {spearman([(r['llm_millennials'] + r['llm_generationx'] + r['llm_babyboomers']) / 3 for r in ok], [float(r['fame_all']) for r in ok]):.2f} |")
    def within(pred, truth):
        vals = []
        for t in sorted({r["qloo_type"] for r in ok}):
            sub = [r for r in ok if r["qloo_type"] == t]
            if len(sub) >= 8:
                vals.append(spearman([pred(r) for r in sub], [truth(r) for r in sub]))
        return sum(vals) / len(vals) if vals else float("nan")

    for gen in ("millennials", "babyboomers"):
        lines.append(f"| fame among {gen}, mean within entity type | {within(lambda r: r[f'qloo_{gen}'], lambda r: float(r[f'fame_{gen}'])):.2f} | {within(lambda r: r[f'llm_{gen}'], lambda r: float(r[f'fame_{gen}'])):.2f} |")
    lines.append(f"| gap, mean within entity type | {within(lambda r: r['qloo_millennials'] - r['qloo_babyboomers'], lambda r: float(r['fame_millennials']) - float(r['fame_babyboomers'])):.2f} | {within(lambda r: r['llm_millennials'] - r['llm_babyboomers'], lambda r: float(r['fame_millennials']) - float(r['fame_babyboomers'])):.2f} |")
    lines.append("")
    lines.append("Spearman rank correlation with YouGov fame (% who have heard of it). 1.0 = perfect ordering. Within-type rows average the correlation inside each entity type (TV, film, music, brands, people, books, podcasts), so a model cannot score well just by knowing that TV shows are more famous than podcasts.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--skip-qloo", action="store_true", help="only compute and cache the LLM baseline")
    a = ap.parse_args()
    rows = load(a.n, a.seed)
    if not a.skip_qloo:
        qloo_side(rows)
    if not a.skip_llm:
        llm_side(rows)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "kill_test_rows.json"), "w") as f:
        json.dump(rows, f, indent=1)
    if a.skip_qloo:
        rep = f"llm guesses cached for {sum(1 for r in rows if r.get('llm_millennials') is not None)}/{len(rows)}"
    elif a.skip_llm:
        rep = f"resolved {sum(1 for r in rows if r.get('qloo_id'))}/{len(rows)}"
    else:
        rep = report(rows)
    open(os.path.join(OUT, "kill_test.md"), "w").write(rep)
    print(rep)


if __name__ == "__main__":
    assert abs(spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) - 0.8) < 1e-9
    assert abs(spearman([1, 2, 3], [3, 2, 1]) + 1) < 1e-9
    main()
