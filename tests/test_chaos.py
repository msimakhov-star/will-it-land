"""With Qloo failing at random, the examples still answer (partial results), and nothing degraded gets memoised."""
import json
import os

os.environ["QLOO_MOCK"] = "1"


def test_examples_survive_faults(tmp_path, monkeypatch):
    from server import pipeline, qloo
    from server.examples import EXAMPLES
    from tests.test_pipeline import fake_llm

    monkeypatch.setattr(qloo, "CACHE_PATH", str(tmp_path / "q.sqlite"))
    monkeypatch.setattr(qloo, "_db", None)
    monkeypatch.setenv("QLOO_MOCK_FAULTS", "429:0.15,timeout:0.05,empty:0.1")
    pipeline._prep_cache.clear()
    pipeline._anchor_ids.clear()
    refs = [{"surface": w, "type": t, "query": w, "role": "", "era": None} for w, t in (("Seinfeld", "tv_show"), ("Blockbuster", "brand"), ("Fortnite", "videogame"))]
    fake_llm(monkeypatch, refs)
    import random
    random.seed(4)
    for ex in EXAMPLES:
        qloo.start_ledger()
        out = pipeline.matrix(ex["text"], [pipeline.Audience("24_and_younger", None, "London"), pipeline.Audience("55_and_older")])
        assert len(out["cells"]) == len(out["references"])
        json.dumps(out)  # serialisable, no exceptions leaked
