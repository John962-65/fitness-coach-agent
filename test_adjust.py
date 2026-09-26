"""调整引擎单元测试"""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from coach.adjust import apply_adjustment, suggest_adjustments
from coach.db import Database


def ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def mk_db(squat_sessions):
    db = Database(Path(tempfile.mkdtemp()) / "t.db")
    for d, w, reps, rpe in squat_sessions:
        db.conn.execute(
            "INSERT INTO checkins(user_id,type,data,created_at) VALUES(?,?,?,?)",
            ("u", "training",
             json.dumps({"exercises": [{"name": "杠铃深蹲", "weight_kg": w,
                                        "sets": 5, "reps": reps, "rpe": rpe}]}),
             ago(d)),
        )
    db.conn.commit()
    return db


PLAN = {
    "days_per_week": 3,
    "schedule": [
        {"day": "周一", "focus": "全身",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5", "note": ""}]},
        {"day": "周三", "focus": "全身",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5", "note": ""}]},
    ],
}


def test_rpe_drift_triggers_deload():
    db = mk_db([(10, 60, 5, 7), (5, 60, 5, 8), (2, 60, 5, 9)])
    sug = suggest_adjustments(db, "u", PLAN)
    assert any(s["action"] == "deload" for s in sug)
    assert sug[0]["reason"] and sug[0]["evidence"]


def test_plateau_triggers_add_volume():
    db = mk_db([(10, 60, 5, 7), (5, 60, 5, 7), (2, 60, 5, 7)])
    sug = suggest_adjustments(db, "u", PLAN)
    s = next((x for x in sug if x["action"] == "add_volume"), None)
    assert s is not None and "70.0kg" in s["reason"]


def test_progress_triggers_increase_weight():
    db = mk_db([(10, 60, 5, 7), (5, 62.5, 5, 7)])
    sug = suggest_adjustments(db, "u", PLAN)
    inc = next((s for s in sug if s["action"] == "increase_weight"), None)
    assert inc is not None and "+5.0kg" in inc["reason"]


def test_progress_with_3_points_still_suggests_increase():
    """17.2 L2 回归：数据点 ≥3 后加重建议不能被吞掉"""
    db = mk_db([(15, 60, 5, 7), (10, 62.5, 5, 7), (5, 65, 5, 7)])
    sug = suggest_adjustments(db, "u", PLAN)
    assert any(s["action"] == "increase_weight" for s in sug)


def test_progress_with_4_points_still_suggests_increase():
    db = mk_db([(20, 60, 5, 7), (15, 62.5, 5, 7), (10, 65, 5, 7), (5, 67.5, 5, 7)])
    sug = suggest_adjustments(db, "u", PLAN)
    assert any(s["action"] == "increase_weight" for s in sug)


def test_adherence_boundary_and_trigger():
    db = mk_db([(6, 60, 5, 7)])
    sug = suggest_adjustments(db, "u", PLAN)
    # PLAN schedule=2 天，练了 1 天 → 0.5，不触发（边界）
    assert not any(s["action"] == "reduce_frequency" for s in sug)
    plan3 = dict(PLAN, schedule=PLAN["schedule"] + [
        {"day": "周五", "focus": "全身",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5"}]}])
    sug = suggest_adjustments(db, "u", plan3)
    assert any(s["action"] == "reduce_frequency" for s in sug)


def test_apply_add_volume():
    new = apply_adjustment(PLAN, "add_volume", "杠铃深蹲", "测试理由")
    assert new["schedule"][0]["exercises"][0]["sets"] == 7
    assert PLAN["schedule"][0]["exercises"][0]["sets"] == 5  # 原对象不变
    assert new["adjust_reason"] == "测试理由"


def test_apply_deload():
    new = apply_adjustment(PLAN, "deload", "整体", "疲劳")
    assert "卸载周" in new["notes"][0] and "卸载" in new["schedule"][0]["focus"]


def test_apply_reduce_frequency():
    new = apply_adjustment(PLAN, "reduce_frequency", "计划频率", "执行率低")
    assert len(new["schedule"]) == 1
    assert "周三" in new["notes"][0]


def test_apply_illegal_action_raises():
    with pytest.raises(ValueError):
        apply_adjustment(PLAN, "fly_to_moon", "x", "x")


def test_full_suggest_apply_persist_cycle():
    db = mk_db([(10, 60, 5, 7), (5, 60, 5, 7), (2, 60, 5, 7)])
    db.create_plan("u", PLAN)
    sug = suggest_adjustments(db, "u", PLAN)
    s = next(x for x in sug if x["action"] == "add_volume")
    new_plan = apply_adjustment(PLAN, s["action"], s["target"], s["reason"])
    db.create_plan("u", new_plan)
    active = db.get_active_plan("u")
    assert active["adjust_action"] == "add_volume"
    v = db.conn.execute(
        "SELECT version FROM plans WHERE user_id='u' AND active=1").fetchone()[0]
    assert v == 2
