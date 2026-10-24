"""/api/proof never shows numbers produced from demo data."""
import json
import os

os.environ["QLOO_MOCK"] = "1"


def test_proof_shows_live_results_only(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from server import llm, main

    monkeypatch.setattr(llm, "warm", lambda: None)
    monkeypatch.setattr(main, "_prewarm_examples", lambda: None)
    monkeypatch.setattr(main, "EVAL_OUT", str(tmp_path))
    (tmp_path / "location_sanity.json").write_text(json.dumps({"data_source": "mock", "hits": 9, "scored": 20}))
    (tmp_path / "fit_report.json").write_text(json.dumps({"data_source": "live", "pooled": {"qloo": 0.5}, "rows": [1]}))
    (tmp_path / "kill_test.md").write_text("data: mock\n| a | b |")
    with TestClient(main.app) as c:
        d = c.get("/api/proof").json()
    assert "location" not in d and "kill_test_md" not in d
    assert d["fit"]["pooled"]["qloo"] == 0.5 and "rows" not in d["fit"]
