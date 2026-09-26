"""复盘引擎单元测试"""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from coach.db import Database
from coach.review import (adherence, build_summary, days_since_last, e1rm,
                          login_recap, review_context_text, rpe_drift,
                          strength_trend, weekly_weight, _brief)


def ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def _mk_db():
    db = Database(Path(tempfile.mkdtemp()) / "t.db")
    uid = "rv"
    sessions = [
        (14, 60, 5, 7), (10, 62.5, 5, 7), (7, 65, 5, 8), (3, 65, 5, 9),
    ]
    for d, w, reps, rpe in sessions:
        db.conn.execute(
            "INSERT INTO checkins(user_id,type,data,created_at) VALUES(?,?,?,?)",
            (uid, "training",
             json.dumps({"exercises": [
                 {"name": "杠铃深蹲", "weight_kg": w, "sets": 5,
                  "reps": reps, "rpe": rpe}]}),
             ago(d)),
        )
    for d, w in [(12, 85.5), (11, 85.3), (5, 84.9), (4, 84.8), (2, 84.7)]:
        db.conn.execute(
            "INSERT INTO checkins(user_id,type,data,created_at) VALUES(?,?,?,?)",
            (uid, "body", json.dumps({"weight_kg": w}), ago(d)),
        )
    db.conn.commit()
    return db, uid


PLAN = {"days_per_week": 3, "schedule": [
    {"day": "周一", "focus": "全身", "exercises": [{"name": "杠铃深蹲"}]}
]}


def test_e1rm():
    assert e1rm(100, 5) == 116.7
    assert e1rm(80, 1) == 80.0
    assert e1rm(60, None) == 60.0


def test_strength_trend():
    db, uid = _mk_db()
    trend = strength_trend(db.list_checkins(uid, 200), "深蹲")
    assert len(trend) == 4
    assert trend[-1][1] > trend[0][1]


def test_weekly_weight():
    db, uid = _mk_db()
    wt = weekly_weight(db.list_checkins(uid, 200))
    assert len(wt) >= 2
    assert wt[-1][1] < wt[0][1]


def test_adherence():
    db, uid = _mk_db()
    ad = adherence(db.list_checkins(uid, 200), 3)
    assert ad["trained_days"] == 1 and ad["planned_days"] == 3
    assert abs(ad["rate"] - 0.33) < 0.01


def test_days_since_last_and_rpe_drift():
    db, uid = _mk_db()
    cks = db.list_checkins(uid, 200)
    assert days_since_last(cks) == 2
    assert rpe_drift(cks, "深蹲") == "rising"


def test_build_summary():
    db, uid = _mk_db()
    s = build_summary(db, uid, PLAN)
    assert s["main_exercise"] == "杠铃深蹲"
    assert len(s["recent"]) == 5 and "体测" in s["recent"][0]


def test_brief_format():
    demo = _brief({"type": "training", "at": ago(1),
                   "data": {"exercises": [{"name": "杠铃深蹲", "weight_kg": 65,
                                           "sets": 5, "reps": 5}]}})
    assert "杠铃深蹲65kg" in demo and "5×5" in demo


def test_login_recap():
    db, uid = _mk_db()
    recap = login_recap(db, uid, PLAN)
    assert "执行率" in recap
    assert "e1RM" in recap
    assert "周均体重" in recap
    assert "RPE 持续上升" in recap


def test_review_context_text():
    db, uid = _mk_db()
    ctx = review_context_text(db, uid, PLAN)
    assert "e1RM 趋势" in ctx and "最近打卡" in ctx


def test_empty_data():
    empty_db = Database(Path(tempfile.mkdtemp()) / "e.db")
    assert login_recap(empty_db, "nobody", None) == ""
    assert "暂无打卡" in review_context_text(empty_db, "nobody", None)
