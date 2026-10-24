"""Anonymous recognition survey: 'have you heard of this?' for each item, plus an age band and a city.
External ground truth for the youngest room (YouGov publishes no under-25 figures). Stores no names, contact
details or IP addresses: only the age band, the city as typed (trimmed), the yes/no answers and the day.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading

from . import qloo

ITEMS_PATH = os.path.join(os.path.dirname(__file__), "..", "eval", "data", "survey_items.json")
AGES = ["under_18", "18_to_24", "25_to_29", "30_to_44", "45_plus"]
_lock = threading.Lock()


def items() -> list[dict]:
    try:
        return [{"id": i["id"], "name": i["name"], "type": i["type"]} for i in json.load(open(ITEMS_PATH))]
    except FileNotFoundError:
        return []


def _db() -> sqlite3.Connection:
    path = os.path.join(os.path.dirname(os.path.abspath(qloo.CACHE_PATH)), "survey.sqlite")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("create table if not exists s (day text, age text, city text, answers text)")
    return db


def save(age: str, city: str, answers: dict[str, bool]) -> int:
    valid = {i["id"] for i in items()}
    if age not in AGES:
        raise ValueError("bad age band")
    clean = {k: bool(v) for k, v in answers.items() if k in valid}
    if len(clean) < max(1, len(valid) // 2):
        raise ValueError("please answer at least half of the items")
    with _lock:
        db = _db()
        db.execute("insert into s values (?,?,?,?)", (dt.date.today().isoformat(), age, (city or "").strip()[:40], json.dumps(clean)))
        db.commit()
        n = db.execute("select count(*) from s").fetchone()[0]
        db.close()
    return n


def responses() -> list[dict]:
    with _lock:
        db = _db()
        rows = db.execute("select day, age, city, answers from s").fetchall()
        db.close()
    return [{"day": d, "age": a, "city": c, "answers": json.loads(x)} for d, a, c, x in rows]
