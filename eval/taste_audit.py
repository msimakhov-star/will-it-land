"""AI taste audit: when a language model is told who the audience is, do its cultural references land with that audience?

generate  Ask two models from different vendors (Claude and Gemini) to write short pieces "for" specific rooms
          (3 formats x 6 rooms). Saved to eval/data/ai_texts.json. Needs no Qloo key.
run       Score every piece with Will It Land against the very room it was written for, and report the share of
          references that are risky or miss, per model and per room. Needs the Qloo key.

Run: python -m eval.taste_audit generate   |   python -m eval.taste_audit run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

DATA = os.path.join(os.path.dirname(__file__), "data", "ai_texts.json")
OUT = os.path.join(os.path.dirname(__file__), "out", "taste_audit.json")

ROOMS = [
    {"name": "under 25s in London", "age": "24_and_younger", "location": "London"},
    {"name": "25 to 29 year olds in Atlanta", "age": "25_to_29", "location": "Atlanta"},
    {"name": "30 to 34 year olds in Mumbai", "age": "30_to_34", "location": "Mumbai"},
    {"name": "35 to 44 year olds in Glasgow", "age": "35_to_44", "location": "Glasgow"},
    {"name": "45 to 54 year olds in Texas", "age": "45_to_54", "location": "Texas"},
    {"name": "people aged 55 and over in Toronto", "age": "55_and_older", "location": "Toronto"},
]
FORMATS = {
    "standup": "a 6-line stand-up opener about moving back in with your parents",
    "ad": "a 30-second radio ad script for a budget airline",
    "toast": "a 5-line best-man toast",
}
PROMPT = ("Write {fmt} for an audience of {room}. Use at least four specific cultural references (TV shows, films, musicians, "
          "brands, famous people, games or places) that THIS audience will recognise and enjoy. Return only the text.")


def _claude(prompt: str) -> str:
    import anthropic
    import httpx2

    c = anthropic.Anthropic(http_client=httpx2.Client(trust_env=False, timeout=60))
    m = c.messages.create(model=os.environ.get("AUDIT_CLAUDE", "claude-sonnet-5-5"), max_tokens=4000, messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in m.content if getattr(b, "type", "") == "text").strip()


def _gemini(prompt: str) -> str:
    from google import genai

    os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
    c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return (c.models.generate_content(model=os.environ.get("AUDIT_GEMINI", "gemini-3.5-flash"), contents=prompt).text or "").strip()


MODELS = {"claude": _claude, "gemini": _gemini}


def generate() -> None:
    jobs = [(m, f, r) for m in MODELS for f in FORMATS for r in ROOMS]

    def one(job):
        m, f, r = job
        try:
            return {"model": m, "format": f, "room": r, "text": MODELS[m](PROMPT.format(fmt=FORMATS[f], room=r["name"]))}
        except Exception as ex:
            print("failed", m, f, r["name"], ex, file=sys.stderr)
            return None

    with ThreadPoolExecutor(6) as ex:
        out = [x for x in ex.map(one, jobs) if x and x["text"]]
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(out, open(DATA, "w"), indent=1, ensure_ascii=False)
    print(f"wrote {len(out)}/{len(jobs)} texts to {DATA}")


def run() -> None:
    from server import pipeline

    items = json.load(open(DATA))

    def one(it):
        r = it["room"]
        res = pipeline.check(it["text"], pipeline.Audience(r["age"], None, r["location"]), swaps=False)
        refs = [x for x in res["references"] if x["entity_id"]]
        return {**{k: it[k] for k in ("model", "format")}, "room": r["name"], "checked": len(refs), "weak": sum(x["verdict"] in ("risky", "misses") for x in refs), "misses": sum(x["verdict"] == "misses" for x in refs),
                "not_in_qloo": res["summary"]["not_in_qloo"], "refs": [{"name": x["name"], "score": x["score"], "verdict": x["verdict"], "llm_guess": x["llm_guess"]} for x in refs]}

    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(one, items))
    agg = {}
    for key in ("model", "room", "format"):
        agg[key] = {}
        for row in rows:
            a = agg[key].setdefault(row[key], {"checked": 0, "weak": 0, "misses": 0})
            for k in ("checked", "weak", "misses"):
                a[k] += row[k]
        for a in agg[key].values():
            a["weak_share"] = round(a["weak"] / a["checked"], 3) if a["checked"] else None
    tot = {k: sum(r[k] for r in rows) for k in ("checked", "weak", "misses")}
    tot["weak_share"] = round(tot["weak"] / tot["checked"], 3) if tot["checked"] else None
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"total": tot, "by": agg, "rows": rows}, open(OUT, "w"), indent=1)
    print(json.dumps({"total": tot, "by_model": agg["model"]}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["generate", "run"])
    {"generate": generate, "run": run}[ap.parse_args().cmd]()
