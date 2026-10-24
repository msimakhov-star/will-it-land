"""Whole-response memos shared by the web API and the MCP tools.

A result is stored only if no Qloo call and no LLM call failed while it was built, so a brief outage can never pin
a wrong answer for the life of the process. A guard (the rate limit) is charged only when work is actually done:
cache hits are free, which keeps the page's own re-scoring and the prewarmed demo from tripping the limit.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict, defaultdict

from . import llm, pipeline, qloo


def ledger_summary(calls: list) -> dict:
    by_endpoint: dict[str, int] = defaultdict(int)
    by_capability: dict[str, int] = defaultdict(int)
    for c in calls:
        by_endpoint[c["endpoint"]] += 1
        ftype = (c.get("params") or {}).get("filter.type", "")
        cap = c["endpoint"] if c["endpoint"] != "/v2/insights" else (
            "insights: demographics" if ftype == "urn:demographics" else "insights: tags" if ftype == "urn:tag" else "insights: heatmap" if ftype == "urn:heatmap"
            else "insights: rank in place" if "filter.results.entities" in (c.get("params") or {}) else "insights: recommendations")
        by_capability[cap] += 1
    return {
        "total": len(calls),
        "live": sum(c["source"] == "live" for c in calls),
        "cache": sum(c["source"] in ("cache", "stale") for c in calls),
        "mock": sum(c["source"] == "mock" for c in calls),
        "errors": sum(c["source"] == "error" for c in calls),
        "by_endpoint": dict(by_endpoint),
        "by_capability": dict(by_capability),
        "calls": calls[:400],
    }


class Memo:
    def __init__(self, maxsize: int):
        self.maxsize, self.data, self.lock = maxsize, OrderedDict(), threading.Lock()

    def peek(self, key) -> str | None:
        with self.lock:
            if key in self.data:
                self.data.move_to_end(key)
                return self.data[key]
        return None

    def get_or(self, key, fn, guard=None) -> str:
        hit = self.peek(key)
        if hit is not None:
            return hit
        if guard:
            guard()
        calls = qloo.start_ledger()
        fails = llm.start_failures()
        out = fn()
        out["ledger"] = ledger_summary(calls)
        body = json.dumps(out)
        if not qloo.degraded() and not fails:
            with self.lock:
                self.data[key] = body
                while len(self.data) > self.maxsize:
                    self.data.popitem(last=False)
        return body

    def clear(self):
        with self.lock:
            self.data.clear()


CHECKS, SWAPS, MATRICES, GUESSES, STANDINS, LOCALISED, LOCALISED_ALL = (Memo(n) for n in (256, 256, 128, 128, 128, 128, 64))
ALL = (CHECKS, SWAPS, MATRICES, GUESSES, STANDINS, LOCALISED, LOCALISED_ALL)


def aud_key(auds) -> str:
    return json.dumps([{"age": a.age, "gender": a.gender, "location": a.location, "name": a.name} for a in auds], sort_keys=True)


def check_body(text: str, a: pipeline.Audience, swaps: bool, guard=None) -> str:
    return CHECKS.get_or(("check", text, a.age, a.gender, a.location, swaps), lambda: pipeline.check(text, a, swaps=swaps), guard)


def swaps_body(text: str, a: pipeline.Audience, guard=None) -> str:
    """Stand-ins are computed from the server's own scored check (never from client-sent references), so the prewarm
    and a browser request share one cache entry."""
    def run():
        first = json.loads(check_body(text, a, False))
        return {"references": pipeline.swaps_for(text, a, first["references"])}

    return SWAPS.get_or(("swaps", text, a.age, a.gender, a.location), run, guard)


def matrix_body(text: str, auds: list, guard=None) -> str:
    return MATRICES.get_or(("matrix", text, aud_key(auds)), lambda: pipeline.matrix(text, auds), guard)


def guesses_body(text: str, auds: list, guard=None) -> str:
    return GUESSES.get_or(("guesses", text, aud_key(auds)), lambda: {"guesses": pipeline.matrix_guesses(text, auds)}, guard)


def standin_body(text: str, auds: list, ref_start: int, guard=None) -> str:
    def run():
        refs = json.loads(matrix_body(text, auds))["references"]
        return pipeline.common_standin(text, refs, ref_start, auds)

    return STANDINS.get_or(("standin", text, aud_key(auds), ref_start), run, guard)


def localise_all_body(text: str, auds: list, guard=None) -> str:
    return LOCALISED_ALL.get_or(("lall", text, aud_key(auds)), lambda: pipeline.localise_all(text, auds), guard)


def localise_body(text: str, a: pipeline.Audience, guard=None) -> str:
    return LOCALISED.get_or(("loc", text, aud_key([a])), lambda: pipeline.localise(text, a), guard)
