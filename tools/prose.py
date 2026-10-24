"""Turn a factual brief into publishable prose with a non-Anthropic model (Gemini), per the author's rule that
public text is drafted by a different vendor than the one that did the engineering.

Usage: GEMINI_API_KEY=... python tools/prose.py BRIEF.md OUT.md [--model gemini-3.1-pro-preview]
The brief holds every fact, number and link; the model may only rephrase, never add facts.
"""
from __future__ import annotations

import argparse
import re
import sys

STYLE = """You are rewriting a factual brief into clear, plain, confident prose for a hackathon submission page or a README.
Rules:
- Use ONLY facts, numbers, names and links that appear in the brief. Never add a claim, metric, customer, quote or capability.
- Keep every number exactly as written in the brief, including any that are unfavourable.
- Keep the brief's headings and their order. Keep code blocks, tables and links exactly as they are.
- Short sentences, active voice, concrete nouns. No hype words (revolutionary, seamless, cutting-edge, game-changer, unlock, leverage, delve).
- Never use an em dash or an en dash. Use commas, colons, full stops or "to" instead.
- British spelling.
Return only the rewritten Markdown."""


def rewrite(brief: str, model: str) -> str:
    import os

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = client.models.generate_content(model=model, contents=brief, config=types.GenerateContentConfig(system_instruction=STYLE, temperature=0.4))
    return clean(r.text or "")


def clean(text: str) -> str:
    text = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text.strip())
    text = re.sub(r"\s*[—–]\s*", ", ", text)  # belt and braces: no em/en dashes survive
    return text.strip() + "\n"


def numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s))


if __name__ == "__main__":
    assert clean("a — b") == "a, b\n"
    ap = argparse.ArgumentParser()
    ap.add_argument("brief")
    ap.add_argument("out")
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    a = ap.parse_args()
    brief = open(a.brief).read()
    out = rewrite(brief, a.model)
    missing = numbers(brief) - numbers(out)
    added = numbers(out) - numbers(brief)
    if added:
        sys.exit(f"refusing to write: the model introduced numbers not in the brief: {sorted(added)}")
    if missing:
        print(f"warning: numbers from the brief not in the output: {sorted(missing)}", file=sys.stderr)
    open(a.out, "w").write(out)
    print("wrote", a.out)
