"""RC-FIX-C：长期报告/周期口径、洞察依赖失效、PersonalTrial 观察窗口。"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from coach.analytics.exercise_metrics import exercise_sessions
from coach.analytics.fact_service import get_training_facts
from coach.analytics.long_term_report import build_report
from coach.analytics.training_calendar import period_summary
from coach.collaboration.coordinator import analyze_collaboration
from coach.db import Database
from coach.experts import insight_service
from coach.experts.training_science import analyze_next_training
from coach.plan import generate_plan
from coach.training_progression import trial_service
from test_repair_regressions import profile

TODAY = date.today().isoformat()
BENCH = "barbell_bench_press"


def _db(tmp_path):
    db = Database(tmp_path / "rcfixc.db")
    p = profile()
    db.save_profile("u", p)
    db.create_plan("u", generate_plan(p))
    return db


def _set_logs(weight=60, reps=10, sets=4, **extra):
    return [{"type": "weight_reps", "weight_kg": weight, "reps": reps,
             **extra} for _ in range(sets)]


def _checkin(db, exercises, offset=0, created_at=None):
    day = (date.today() - timedelta(days=offset)).isoformat()
    cid = db.record_checkin("u", "training", {
        "exercises": exercises,
        "session_meta": {"mode": "free", "local_date": day}})
    if created_at:
        db.conn.execute("UPDATE checkins SET created_at=? WHERE id=?",
                        (created_at, cid))
        db.conn.commit()
    return cid


# ---- RC-FIX-3 ----

def test_long_term_report_aggregates_all_exercises_and_period_matches(tmp_path):
    db = _db(tmp_path)
    _checkin(db, [
        {"name": "杠铃平板卧推", "exercise_id": BENCH,
         "set_logs": _set_logs(60, 10, 4)},
        {"name": "杠铃划船", "exercise_id": "barbell_row",
         "set_logs": _set_logs(100, 5, 4)},
    ])
    ps = period_summary(db, "u", 30)
    rep = build_report(db, "u", "month")
    facts = get_training_facts(db, "u", 30)
    assert ps["strength_working_sets"] == 8
    assert ps["strength_volume_kg"] == 4400
    assert rep["training"]["sessions"] == 1
    assert rep["training"]["working_sets"] == 8
    assert rep["training"]["strength_volume_kg"] == 4400
    session_fact = next(f for f in facts["facts"] if f["metric"] == "sessions")
    assert session_fact["value"] == 1
    assert next(f for f in facts["facts"]
                if f["metric"] == "working_sets")["value"] == 8


def test_long_term_report_complex_forms_and_cardio_do_not_mix(tmp_path):
    db = _db(tmp_path)
    # 超级组：同一会话两个动作同组，不重复计数
    _checkin(db, [
        {"name": "杠铃平板卧推", "exercise_id": BENCH,
         "superset_group": "A", "set_logs": _set_logs(60, 10, 3)},
        {"name": "杠铃划船", "exercise_id": "barbell_row",
         "superset_group": "A", "set_logs": _set_logs(50, 10, 3)},
        # 递减组：一个逻辑组，容量按执行段求和
        {"name": "哑铃弯举", "exercise_id": "dumbbell_bench_press",
         "set_logs": [{"type": "weight_reps", "method": "drop_set",
                       "segments": [
                           {"weight_kg": 20, "reps": 8},
                           {"weight_kg": 15, "reps": 8}]}]},
        # 单侧：一个逻辑组，容量按左右段求和
        {"name": "保加利亚分腿蹲", "exercise_id": "bulgarian_split_squat",
         "set_logs": [{"type": "weight_reps", "method": "unilateral",
                       "segments": [
                           {"weight_kg": 20, "reps": 8},
                           {"weight_kg": 20, "reps": 8}]}]},
        # 持续有氧 / HIIT 不进入力量工作组与容量
        {"name": "跑步", "exercise_id": "running",
         "set_logs": [{"type": "distance_time", "distance_m": 5000,
                       "duration_seconds": 1200}]},
        {"name": "四轮间歇", "exercise_id": "custom_hiit",
         "set_logs": [{"type": "duration", "duration_seconds": 240,
                       "hiit": {"planned_rounds": 4,
                                "completed_rounds": 4,
                                "work_seconds_done": 120,
                                "rest_seconds_done": 120,
                                "blocks": [{"name": "开合跳",
                                            "work_seconds": 30,
                                            "rounds": 4}]}}]},
    ])
    rep = build_report(db, "u", "month")["training"]
    # 6 个超级组 + 1 递减 + 1 单侧 = 8 个力量工作组
    assert rep["working_sets"] == 8
    expected_volume = 60 * 10 * 3 + 50 * 10 * 3 + 20 * 8 + 15 * 8 + 20 * 8 * 2
    assert rep["strength_volume_kg"] == expected_volume
    assert rep["sessions"] == 1
    assert rep["interval_sessions"] == 1


def test_backdated_local_date_is_same_window_everywhere(tmp_path):
    db = _db(tmp_path)
    old = (date.today() - timedelta(days=31)).isoformat()
    cid = db.record_checkin("u", "training", {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                       "set_logs": _set_logs()}],
        "session_meta": {"mode": "free", "local_date": old}})
    # created_at 是现在，但本地日期在窗口外
    ps = period_summary(db, "u", 30)
    rep = build_report(db, "u", "month")
    facts = get_training_facts(db, "u", 30)
    assert ps["training_sessions"] == 0
    assert rep["training"]["sessions"] == 0
    assert next(f for f in facts["facts"]
                if f["metric"] == "sessions")["value"] == 0
    assert cid


# ---- RC-FIX-4 ----

def _next_insight(db):
    payload = analyze_next_training(db, "u", {"exercise_id": BENCH})
    return insight_service.create_insight(db, "u", payload)


def test_new_related_workout_invalidates_next_insight(tmp_path):
    db = _db(tmp_path)
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=6)
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=2)
    ins = _next_insight(db)
    assert ins["status"] == "ready"
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=0)
    fresh = insight_service.get_insight(db, "u", ins["id"])
    assert fresh["status"] == "invalidated"
    assert "训练记录" in fresh["status_reason"]


def test_unrelated_workout_does_not_invalidate_next_insight(tmp_path):
    db = _db(tmp_path)
    for off in (6, 2):
        _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                       "set_logs": _set_logs()}], offset=off)
    ins = _next_insight(db)
    _checkin(db, [{"name": "杠铃深蹲", "exercise_id": "barbell_back_squat",
                   "set_logs": _set_logs(100, 5, 4)}], offset=0)
    fresh = insight_service.get_insight(db, "u", ins["id"])
    assert fresh["status"] == "ready"


def test_delete_or_correct_related_workout_invalidates(tmp_path):
    db = _db(tmp_path)
    cid = _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                         "set_logs": _set_logs()}], offset=4)
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=1)
    ins = _next_insight(db)
    db.conn.execute("DELETE FROM checkins WHERE id=?", (cid,))
    db.conn.commit()
    fresh = insight_service.get_insight(db, "u", ins["id"])
    assert fresh["status"] == "invalidated"
    # 另一种路径：纠错已引用记录
    ins2 = _next_insight(db)
    cid2 = db.conn.execute(
        "SELECT id FROM checkins WHERE user_id='u' ORDER BY id DESC LIMIT 1"
    ).fetchone()["id"]
    db.revise_checkin("u", cid2, 0, {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                       "set_logs": _set_logs(62.5, 8, 4)}],
        "session_meta": {"mode": "free",
                         "local_date": (date.today() - timedelta(days=1)).isoformat()}},
        "纠错", "用户确认")
    fresh2 = insight_service.get_insight(db, "u", ins2["id"])
    assert fresh2["status"] == "invalidated"


def test_collaboration_report_invalidated_by_new_workout(tmp_path):
    db = _db(tmp_path)
    for off in (5, 2):
        _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                       "set_logs": _set_logs()}], offset=off)
    payload = analyze_collaboration(db, "u", {
        "scenario": "training-recovery", "exercise_id": BENCH,
        "window_days": 14})
    ins = insight_service.create_insight(db, "u", payload)
    assert ins["status"] == "ready"
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=0)
    fresh = insight_service.get_insight(db, "u", ins["id"])
    assert fresh["status"] == "invalidated"
    assert "训练记录" in fresh["status_reason"]


# ---- RC-FIX-5 ----

def test_trial_observes_all_sessions_and_freezes_after_end(tmp_path):
    db = _db(tmp_path)
    tid = db.start_personal_trial(
        "u", "卧推尝试", "RC-FIX-C", "观察次数", "10 次", review_days=60,
        chosen_target=json.dumps({"sets": 4, "reps": "8", "weight_kg": 60}),
        exercise_id=BENCH, observation_metric="target-completion",
        observation_window_days=60, min_sessions=10)
    for i in range(10):
        _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                       "set_logs": _set_logs()}], offset=9 - i)
    trial = db.get_personal_trial("u", tid)
    obs = trial_service.trial_observation(db, "u", trial)
    assert obs["sessions_total"] == 10
    assert len(obs["sessions"]) == 10
    result = trial_service.decide_trial(db, "u", tid, "keep", "保留")
    assert result["status"] == "ended"
    frozen = db.get_personal_trial("u", tid)
    assert frozen["review_snapshot"]
    before = trial_service.trial_review(db, "u", frozen)
    assert before["frozen"] is True
    assert before["observation"]["sessions_total"] == 10
    # 结束后新增训练：冻结复盘不改变
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=0)
    frozen = db.get_personal_trial("u", tid)
    after = trial_service.trial_review(db, "u", frozen)
    assert after["observation"]["sessions_total"] == 10
    assert after["frozen"] is True
    assert after["post_end_changes"] == []
    # 历史纠错：原快照不变，但标记重新复核
    target = db.conn.execute(
        "SELECT id FROM checkins WHERE user_id='u' ORDER BY id DESC LIMIT 1"
    ).fetchone()["id"]
    # 找观察期内的一条（不是刚新增的）
    in_window = db.conn.execute(
        "SELECT id FROM checkins WHERE user_id='u' ORDER BY id ASC LIMIT 1"
    ).fetchone()["id"]
    db.revise_checkin("u", in_window, 0, {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                       "set_logs": _set_logs(62.5, 8, 4)}],
        "session_meta": {"mode": "free",
                         "local_date": (date.today() - timedelta(days=9)).isoformat()}},
        "纠错", "用户确认")
    frozen = db.get_personal_trial("u", tid)
    changed = trial_service.trial_review(db, "u", frozen)
    assert changed["frozen"] is True
    assert changed["needs_rereview"] is True
    assert changed["post_end_changes"]
    assert "尝试期间：10 次训练" in "；".join(changed["sections"]["observed"])
    reread = trial_service.rereview_ended_trial(db, "u", tid)
    assert reread["previous"]["frozen"] is True
    assert not reread["current"].get("frozen")
    assert reread["requires_user_decision"] is True


def test_trial_excludes_earlier_same_day_and_replacement_sessions(tmp_path):
    db = _db(tmp_path)
    # 尝试开始前的同日记录
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=0)
    tid = db.start_personal_trial(
        "u", "卧推尝试", "RC-FIX-C", "观察次数", "3 次", review_days=30,
        chosen_target=json.dumps({"sets": 4, "reps": "8", "weight_kg": 60}),
        exercise_id=BENCH, observation_metric="target-completion",
        observation_window_days=30, min_sessions=3)
    _checkin(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                   "set_logs": _set_logs()}], offset=0)
    # 替换掉尝试动作的会话：不混入原动作统计
    _checkin(db, [{"name": "哑铃卧推", "exercise_id": "dumbbell_bench_press",
                   "session_replacement_of": BENCH,
                   "session_replacement": {"planned_exercise_id": BENCH,
                                           "actual_exercise_id": "dumbbell_bench_press",
                                           "scope": "session"},
                   "set_logs": _set_logs(20, 10, 3)}], offset=0)
    trial = db.get_personal_trial("u", tid)
    obs = trial_service.trial_observation(db, "u", trial)
    assert obs["sessions_total"] == 1
    assert all(s["checkin_id"] > int(trial["start_checkin_id"])
               for s in obs["sessions"])
