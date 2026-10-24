"""Survey: stores only age band, city and answers; rejects bad input; export is closed without the token."""
import os

os.environ["QLOO_MOCK"] = "1"


def test_survey_roundtrip(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from server import llm, main, qloo, survey

    monkeypatch.setattr(qloo, "CACHE_PATH", str(tmp_path / "q.sqlite"))
    monkeypatch.setattr(llm, "warm", lambda: None)
    monkeypatch.setattr(main, "_prewarm_examples", lambda: None)
    monkeypatch.setenv("SURVEY_TOKEN", "t0k")
    with TestClient(main.app) as c:
        items = c.get("/api/survey").json()["items"]
        assert len(items) >= 30
        ans = {i["id"]: True for i in items}
        assert c.post("/api/survey", json={"age": "18_to_24", "city": " London ", "answers": ans}).json()["ok"]
        assert c.post("/api/survey", json={"age": "teen", "answers": ans}).status_code == 400
        assert c.post("/api/survey", json={"age": "18_to_24", "answers": {"q01": True}}).status_code == 400
        assert c.get("/api/survey/export").status_code == 404
        exp = c.get("/api/survey/export?token=t0k").json()
        assert exp["responses"][0]["city"] == "London" and set(exp["responses"][0]) == {"day", "age", "city", "answers"}
