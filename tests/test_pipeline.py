"""Offline tests: fake Qloo (server/mock.py) and a scripted LLM, so the agent loop is checked without keys.
Run: .venv/bin/python -m pytest -q
"""
from __future__ import annotations

import json
import os

import pytest

os.environ["QLOO_MOCK"] = "1"
os.environ.setdefault("ANTHROPIC_API_KEY", "test")


@pytest.fixture(autouse=True)
def fresh_cache(tmp_path, monkeypatch):
    from server import qloo

    monkeypatch.setattr(qloo, "CACHE_PATH", str(tmp_path / "q.sqlite"))
    monkeypatch.setattr(qloo, "_db", None)
    yield


TEXT = "My dad watches Seinfeld every night.\nMy mum still carries a Blockbuster card and a Blockbuster mug."


def fake_llm(monkeypatch, extract_refs):
    from server import llm

    def complete_json(system, user, max_tokens=4000, fast=False):
        if system.startswith("You find cultural references"):
            return {"references": extract_refs}
        if system.startswith("You disambiguate"):
            return {"pick": 0, "why": "first"}
        if system.startswith("You propose stand-ins"):
            return {"candidates": ["HMV", "Woolworths", "Blockbuster"]}
        if system.startswith("You rewrite one line"):
            body = json.loads(user)
            return {"lines": [body["line"].replace(body["replace"], w) for w in body["with"]]}
        raise AssertionError("unexpected prompt: " + system[:40])

    monkeypatch.setattr(llm, "complete_json", complete_json)


REFS = [
    {"surface": "Seinfeld", "type": "tv_show", "query": "Seinfeld", "role": "a 90s sitcom", "era": "1990s", "guess": 40},
    {"surface": "Blockbuster", "type": "brand", "query": "Blockbuster", "role": "a dead video-rental chain", "era": "2000s", "guess": 50},
    {"surface": "Blockbuster", "type": "brand", "query": "Blockbuster", "role": "a dead video-rental chain", "era": "2000s", "guess": 50},
    {"surface": "Not In Text", "type": "brand", "query": "x", "role": "", "era": None, "guess": 50},
    {"surface": "Seinfeld", "type": "spaceship", "query": "Seinfeld", "role": "", "era": None, "guess": 50},
]


def test_check_shapes_and_spans(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS)
    out = pipeline.check(TEXT, pipeline.Audience("24_and_younger", None, "London"), swaps=False)
    refs = out["references"]
    # hallucinated surface and unknown type are dropped; duplicate surfaces get distinct spans
    assert [r["surface"] for r in refs] == ["Seinfeld", "Blockbuster", "Blockbuster"]
    spans = [(r["start"], r["end"]) for r in refs]
    assert len(set(spans)) == 3
    for r in refs:
        assert TEXT[r["start"]:r["end"]] == r["surface"]
        assert r["entity_id"] and 0 <= r["score"] <= 100
        assert r["verdict"] in ("lands", "risky", "misses")
    s = out["summary"]
    assert s["found"] == 3 and s["checked"] == 3 and s["lands"] + s["risky"] + s["misses"] == 3


def test_swaps_round_trip(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    aud = pipeline.Audience("24_and_younger", None, None)
    first = pipeline.check(TEXT, aud, swaps=False)
    second = pipeline.swaps_for(TEXT, aud, json.loads(json.dumps(first["references"])))
    assert len(second) == len(first["references"])
    for before, after in zip(first["references"], second):
        assert before["score"] == after["score"] and before["start"] == after["start"]
        for s in after["swaps"]:
            assert s["name"].lower() != "blockbuster"  # never propose the original back
            assert s["score"] > (after["score"] or 0)
            assert s["line"] is None or s["name"] in s["line"]


def test_audience_changes_scores(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    young = pipeline.check(TEXT, pipeline.Audience("24_and_younger"), swaps=False)["references"]
    old = pipeline.check(TEXT, pipeline.Audience("55_and_older"), swaps=False)["references"]
    # mock data: Seinfeld skews old, so it must score higher for 55+ than for under-25s
    assert old[0]["score"] > young[0]["score"]


def test_no_references(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, [])
    out = pipeline.check("Nothing cultural here at all.", pipeline.Audience(), swaps=True)
    assert out["references"] == [] and out["summary"]["found"] == 0


def test_api_validation(monkeypatch):
    from fastapi.testclient import TestClient

    from server import llm, main

    monkeypatch.setattr(llm, "warm", lambda: None)
    fake_llm(monkeypatch, REFS[:1])
    main._check_cached.cache_clear()
    with TestClient(main.app) as c:
        assert c.post("/api/check", json={"text": "x", "age": "teen"}).status_code == 400
        assert c.post("/api/check", json={"text": "", "age": None}).status_code == 422
        r = c.post("/api/check", json={"text": "My dad watches Seinfeld every night.", "age": "55_and_older", "swaps": False})
        assert r.status_code == 200 and r.json()["references"][0]["surface"] == "Seinfeld"
        tools = c.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"accept": "application/json, text/event-stream"})
        assert tools.status_code == 200 and {t["name"] for t in tools.json()["result"]["tools"]} >= {"check_references", "audience_options"}
