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
    from server import pipeline, qloo

    monkeypatch.setattr(qloo, "CACHE_PATH", str(tmp_path / "q.sqlite"))
    monkeypatch.setattr(qloo, "_db", None)
    pipeline._prep_cache.clear()
    pipeline._anchor_ids.clear()
    yield


TEXT = "My dad watches Seinfeld every night.\nMy mum still carries a Blockbuster card and a Blockbuster mug."

REFS = [
    {"surface": "Seinfeld", "type": "tv_show", "query": "Seinfeld", "role": "a 90s sitcom", "era": "1990s"},
    {"surface": "Blockbuster", "type": "brand", "query": "Blockbuster", "role": "a dead video-rental chain", "era": "2000s"},
    {"surface": "Blockbuster", "type": "brand", "query": "Blockbuster", "role": "a dead video-rental chain", "era": "2000s"},
    {"surface": "Not In Text", "type": "brand", "query": "x", "role": "", "era": None},
    {"surface": "Seinfeld", "type": "spaceship", "query": "Seinfeld", "role": "", "era": None},
]


def fake_llm(monkeypatch, extract_refs, calls=None):
    from server import llm

    def complete_json(system, user, max_tokens=4000, fast=False):
        if calls is not None:
            calls.append(system[:24])
        if system.startswith("You find cultural references"):
            return {"references": extract_refs}
        if system.startswith("You estimate"):
            body = json.loads(user)
            return {"guesses": [[50 + 10 * j for j in range(len(body["audiences"]))] for _ in body["references"]]}
        if system.startswith("You disambiguate"):
            return {"pick": 0, "why": "first"}
        if system.startswith("You propose stand-in"):
            return {"candidates": ["HMV", "Woolworths", "Blockbuster"]}
        if system.startswith("A writer needs a stand-in"):
            return {"keep": json.loads(user)["candidates"][:2]}
        if system.startswith("You rewrite one line"):
            body = json.loads(user)
            return {"lines": [body["line"].replace(body["replace"], w) for w in body["with"]]}
        raise AssertionError("unexpected prompt: " + system[:40])

    monkeypatch.setattr(llm, "complete_json", complete_json)


def test_check_shapes_and_spans(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS)
    out = pipeline.check(TEXT, pipeline.Audience("24_and_younger", None, "London"), swaps=False)
    refs = out["references"]
    # hallucinated surface and unknown type are dropped; duplicate surfaces get distinct spans
    assert [r["surface"] for r in refs] == ["Seinfeld", "Blockbuster", "Blockbuster"]
    assert len({(r["start"], r["end"]) for r in refs}) == 3
    for r in refs:
        assert TEXT[r["start"]:r["end"]] == r["surface"]
        assert r["entity_id"] and 0 <= r["score"] <= 100
        assert r["verdict"] in ("lands", "risky", "misses")
        assert r["llm_guess"] == 60  # fake guesser: 50 + 10 * column, and under-25s is column 1 after "any"
    s = out["summary"]
    assert s["found"] == 3 and s["checked"] == 3 and s["lands"] + s["risky"] + s["misses"] == 3


def test_bands_match_single_checks(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    out = pipeline.check(TEXT, pipeline.Audience("24_and_younger", None, "London"), swaps=False)
    assert list(out["bands"]) == ["any"] + pipeline.AUDIENCE_AGES
    other = pipeline.check(TEXT, pipeline.Audience("55_and_older", None, "London"), swaps=False)
    assert [c["score"] for c in out["bands"]["55_and_older"]] == [r["score"] for r in other["references"]]
    parts = out["bands"]["24_and_younger"][0]["parts"]
    assert abs(parts["base"] + parts["age"] + parts["gender"] + parts["location"] - parts["score"]) < 0.3


def test_extraction_runs_once_per_text(monkeypatch):
    from server import pipeline

    calls = []
    fake_llm(monkeypatch, REFS[:2], calls)
    pipeline.check(TEXT, pipeline.Audience("24_and_younger"), swaps=False)
    pipeline.check(TEXT, pipeline.Audience("55_and_older", None, "Texas"), swaps=False)
    assert sum(c.startswith("You find cultural") for c in calls) == 1


def test_swaps_round_trip_and_sources(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    aud = pipeline.Audience("24_and_younger", None, None)
    first = pipeline.check(TEXT, aud, swaps=False)
    second = pipeline.swaps_for(TEXT, aud, json.loads(json.dumps(first["references"])))
    assert len(second) == len(first["references"])
    sources = set()
    for before, after in zip(first["references"], second):
        assert before["score"] == after["score"] and before["start"] == after["start"]
        for s in after["swaps"]:
            sources.add(s["source"])
            assert s["name"].lower() != "blockbuster"  # never propose the original back
            assert s["score"] > (after["score"] or 0)
            assert s["line"] is None or s["name"] in s["line"]
    assert "qloo" in sources  # at least one stand-in came from Qloo's own recommendations


def test_audience_changes_scores(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    young = pipeline.check(TEXT, pipeline.Audience("24_and_younger"), swaps=False)["references"]
    old = pipeline.check(TEXT, pipeline.Audience("55_and_older"), swaps=False)["references"]
    # mock data: Seinfeld skews old, so it must score higher for 55+ than for under-25s
    assert old[0]["score"] > young[0]["score"]


def test_matrix_matches_single_checks(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    auds = [pipeline.Audience("24_and_younger", None, "London", "Young London"), pipeline.Audience("55_and_older", None, "St. Louis")]
    m = pipeline.matrix(TEXT, auds, with_guesses=True)
    assert len(m["audiences"]) == 2 and m["audiences"][0]["label"] == "Young London"
    assert len(m["cells"]) == len(m["references"]) == 2
    for j, a in enumerate(auds):
        single = pipeline.check(TEXT, a, swaps=False)["references"]
        assert [round(m["cells"][i][j]["score"], 1) for i in range(2)] == [r["score"] for r in single]
        assert m["cells"][0][j]["llm_guess"] == 50 + 10 * j


@pytest.fixture
def strict_qloo(monkeypatch):
    """Real-API failure contract: /search 404 'No results' for unknown names, 400 for an unknown place."""
    from server import mock, qloo

    orig = mock.respond

    def strict(path, params):
        if path == "/search" and params["query"].lower().startswith("zz"):
            raise qloo.QlooError('Qloo 404: {"error":"No results"}')
        if params.get("signal.location.query", "").lower() == "atlantis":
            raise qloo.QlooError("Qloo 400: no locality found")
        return orig(path, params)

    monkeypatch.setattr(mock, "respond", strict)


def test_failure_contract(monkeypatch, strict_qloo):
    from server import pipeline, qloo

    refs = REFS[:1] + [{"surface": "Zzyzx", "type": "brand", "query": "Zzyzx", "role": "", "era": None}]
    fake_llm(monkeypatch, refs)
    calls = qloo.start_ledger()
    out = pipeline.check("My dad watches Seinfeld. We drove past Zzyzx.", pipeline.Audience("24_and_younger", None, "Atlantis"), swaps=False)
    unknown = [r for r in out["references"] if r["surface"] == "Zzyzx"][0]
    assert unknown["entity_id"] is None and unknown["why"] == "not in Qloo"
    assert out["location_recognised"] is False
    assert qloo.degraded()  # the failed location call is recorded, so the response layer will not memoise this result
    assert any(c["source"] == "error" and "signal.location.query" in c["params"] for c in calls)


def test_audience_validation():
    from server import pipeline

    assert pipeline.Audience(" 24_AND_YOUNGER ", "Women", " Leeds ").label() == "under 25, women, Leeds"
    for bad in ({"age": "teen"}, {"gender": "x"}):
        with pytest.raises(ValueError):
            pipeline.Audience(**bad)


def test_locate_prefers_whole_words():
    from server.pipeline import _locate

    used = []
    assert _locate("Friendship with Friends", "Friends", used) == (16, 23)


def test_reference_cap(monkeypatch):
    from server import pipeline

    many = "\n".join(f"Line {i} mentions Seinfeld." for i in range(40))
    fake_llm(monkeypatch, [{"surface": "Seinfeld", "type": "tv_show", "query": "Seinfeld", "role": "", "era": None}] * 40)
    assert len(pipeline.extract(many)) == pipeline.MAX_REFS


def test_unknown_place_flag(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    monkeypatch.setattr(pipeline.qloo, "rank_for_audience", lambda *a, **k: {})
    out = pipeline.check(TEXT, pipeline.Audience("24_and_younger", None, "Atlantis"), swaps=False)
    assert out["location_recognised"] is False
    assert pipeline.check(TEXT, pipeline.Audience("24_and_younger"), swaps=False)["location_recognised"] is None


def test_localise_improves_or_stops(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    out = pipeline.localise(TEXT, pipeline.Audience("24_and_younger"))
    bad = lambda s: 2 * s["misses"] + s["risky"]
    assert bad(out["after"]) <= bad(out["before"])
    assert out["steps"] and out["steps"][-1]["action"] in ("stop", "recheck")
    if out["text"] != TEXT:
        assert "Blockbuster" not in out["text"] or bad(out["after"]) < bad(out["before"])


def test_pick_swap_prefers_qloo_within_margin():
    from server.pipeline import PREFER_QLOO_WITHIN, Swap, pick_swap

    ai, q = Swap("A", "a", 80, "ai"), Swap("Q", "q", 80 - PREFER_QLOO_WITHIN + 1, "qloo")
    assert pick_swap([ai, q]).name == "Q"
    assert pick_swap([ai, Swap("Q", "q", 80 - PREFER_QLOO_WITHIN - 5, "qloo")]).name == "A"
    assert pick_swap([]) is None


def test_localise_all(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, REFS[:2])
    auds = [pipeline.Audience("24_and_younger", None, "London"), pipeline.Audience("55_and_older", None, "St. Louis")]
    out = pipeline.localise_all(TEXT, auds)
    worst = lambda m: sum(2 * s["misses"] + s["risky"] for s in m["summaries"])
    assert worst(out["after"]) <= worst(out["before"])
    if out["kept"]:
        assert out["text"] != TEXT and worst(out["after"]) < worst(out["before"])
        for sw in out["swaps"]:
            assert min(sw["scores_to"]) > min(sw["scores_from"])


def test_apply_swaps_one_per_line():
    from server.pipeline import Reference, Swap, apply_swaps

    t = "We rented it at Blockbuster.\nBlockbuster again."
    r1 = Reference("Blockbuster", 16, 27, "brand", "Blockbuster", "", None)
    r2 = Reference("Blockbuster", 29, 40, "brand", "Blockbuster", "", None)
    assert apply_swaps(t, [(r1, Swap("HMV", "x", 80, "ai")), (r2, Swap("HMV", "x", 80, "ai"))]) == "We rented it at HMV.\nHMV again."


def test_no_references(monkeypatch):
    from server import pipeline

    fake_llm(monkeypatch, [])
    out = pipeline.check("Nothing cultural here at all.", pipeline.Audience(), swaps=True)
    assert out["references"] == [] and out["summary"]["found"] == 0
    assert pipeline.matrix("Nothing cultural here at all.", [pipeline.Audience("25_to_29")])["cells"] == []


def test_api(monkeypatch):
    from fastapi.testclient import TestClient

    from server import llm, main

    monkeypatch.setattr(llm, "warm", lambda: None)
    monkeypatch.setattr(main, "_prewarm_examples", lambda: None)
    fake_llm(monkeypatch, REFS[:2])
    for m in main.MEMOS:
        m.clear()
    with TestClient(main.app) as c:
        assert c.post("/api/check", json={"text": "x", "age": "teen"}).status_code == 400
        assert c.post("/api/check", json={"text": "", "age": None}).status_code == 422
        r = c.post("/api/check", json={"text": TEXT, "age": "55_and_older", "swaps": False})
        assert r.status_code == 200 and r.json()["references"][0]["surface"] == "Seinfeld"
        led = r.json()["ledger"]
        assert led["total"] > 0 and "/search" in led["by_endpoint"] and "/v2/insights" in led["by_endpoint"]
        m = c.post("/api/matrix", json={"text": TEXT, "audiences": [{"age": "24_and_younger", "location": "London"}, {"age": "55_and_older"}]})
        assert m.status_code == 200 and len(m.json()["cells"][0]) == 2
        assert c.post("/api/matrix", json={"text": TEXT, "audiences": [{"age": "x"}]}).status_code == 400
        g = c.post("/api/guesses", json={"text": TEXT, "audiences": [{"age": "24_and_younger"}, {"age": "55_and_older"}]})
        assert g.status_code == 200 and len(g.json()["guesses"]) == 2 and len(g.json()["guesses"][0]) == 2
        refs = m.json()["references"]
        st = c.post("/api/standin", json={"text": TEXT, "audiences": [{"age": "24_and_younger", "location": "London"}, {"age": "55_and_older"}], "references": refs, "ref_start": refs[1]["start"]})
        assert st.status_code == 200
        b = st.json()["best"]
        if b:
            assert b["min"] == min(b["scores"]) and b["min"] > min(st.json()["reference"]["scores"])
        loc = c.post("/api/localise", json={"text": TEXT, "audience": {"age": "24_and_younger"}})
        assert loc.status_code == 200 and "text" in loc.json() and "applied" in loc.json()
        la = c.post("/api/localise_all", json={"text": TEXT, "audiences": [{"age": "24_and_younger", "location": "London"}, {"age": "55_and_older"}]})
        assert la.status_code == 200 and "kept" in la.json()
        rep = c.post("/api/report", json={"kind": "matrix", "payload": m.json()})
        assert rep.status_code == 200
        got = c.get(f"/api/report/{rep.json()['id']}")
        assert got.status_code == 200 and got.json()["payload"]["cells"] == m.json()["cells"]
        assert c.get("/api/report/nope").status_code == 404
        # security: the SPA fallback never serves files outside web/dist
        for bad in ("/%2Fetc%2Fhosts", "/..%2F..%2Fserver%2Fmain.py", "/../../pyproject.toml"):
            r = c.get(bad)
            assert "fastapi" not in r.text and "localhost" not in r.text.lower()[:200] or r.headers.get("content-type", "").startswith("text/html")
        assert c.post("/mcp", json={"jsonrpc": "2.0", "id": 9, "method": "tools/list"}, headers={"accept": "application/json, text/event-stream"}).status_code == 200
        tools = c.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"accept": "application/json, text/event-stream"})
        assert tools.status_code == 200 and {t["name"] for t in tools.json()["result"]["tools"]} >= {"check_references", "check_matrix", "localise", "localise_for_all", "audience_options"}
