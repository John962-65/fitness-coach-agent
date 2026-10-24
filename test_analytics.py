"""M6.3：逐组口径的动作历史 / 个人纪录 / 日历 / 周期汇总。"""
from __future__ import annotations

import json

import pytest

from coach.analytics import exercise_sessions, month_calendar, personal_records, period_summary
from coach.db import Database

UID = "analytics_user"
BENCH = "barbell_bench_press"

BENCH_S1 = {"name": "杠铃平板卧推", "exercise_id": BENCH, "set_logs": [
    {"weight_kg": 60, "reps": 10, "at": "2026-10-05T10:00:00"},
    {"weight_kg": 65, "reps": 8, "at": "2026-10-05T10:03:00"},
    {"weight_kg": 70, "reps": 6, "at": "2026-10-05T10:06:00"},
]}
BENCH_S2 = {"name": "杠铃平板卧推", "exercise_id": BENCH, "set_logs": [
    {"weight_kg": 20, "reps": 10, "warmup": True, "at": "2026-10-12T10:00:00"},
    {"weight_kg": 72.5, "reps": 5, "at": "2026-10-12T10:04:00"},
]}


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "analytics.db")
    yield d
    d.conn.close()


def _record(db, exercises, at=None):
    cid = db.record_checkin(UID, "training", {"exercises": exercises, "raw": "测试"})
    if at:
        db.conn.execute("UPDATE checkins SET created_at=? WHERE id=?", (at, cid))
        db.conn.commit()
    return cid


def test_exercise_sessions_from_set_logs(db):
    _record(db, [BENCH_S1], at="2026-10-05T10:06:30")
    sessions = exercise_sessions(db, UID, BENCH)
    assert len(sessions) == 1
    s = sessions[0]
    assert s["date"] == "2026-10-05"
    assert s["working_sets"] == 3
    # 容量 = 60×10 + 65×8 + 70×6 = 1540（逐组求和，不依赖代表组）
    assert s["volume"] == 1540
    assert s["best_set"] == {"weight_kg": 70, "reps": 6}
    # e1RM 逐组取最佳：Epley(70,6)=84.0 > Epley(65,8)=82.3 > Epley(60,10)=80.0
    assert s["best_e1rm"] == 84.0
    assert s["duration_min"] == 6


def test_warmup_excluded_and_rep_range_guard(db):
    _record(db, [BENCH_S2], at="2026-10-12T10:05:00")
    sessions = exercise_sessions(db, UID, BENCH)
    s = sessions[0]
    assert s["working_sets"] == 1                      # 热身组不计
    assert s["volume"] == 362                          # 72.5×5=362.5，round→362
    assert s["best_e1rm"] == 84.6                      # Epley(72.5,5)
    # 超出 1-12 次区间的组不参与 e1RM 估计（只算容量与次数）
    _record(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH,
                  "set_logs": [{"weight_kg": 40, "reps": 20, "at": "2026-10-13T10:00:00"}]}])
    s3 = exercise_sessions(db, UID, BENCH)[0]
    assert s3["best_e1rm"] is None
    assert s3["volume"] == 800


def test_bodyweight_sets_zero_volume_but_counted(db):
    _record(db, [{"name": "引体向上", "exercise_id": "pull_up",
                  "set_logs": [{"reps": 8, "at": "2026-10-06T10:00:00"},
                               {"reps": 6, "at": "2026-10-06T10:02:00"}]}])
    sessions = exercise_sessions(db, UID, "pull_up")
    s = sessions[0]
    assert s["volume"] == 0                            # 自重无外部负重，容量如实为 0
    assert s["reps_total"] == 14
    rec = personal_records(sessions)
    assert rec["heaviest"] is None
    assert rec["max_reps"]["reps"] == 8


def test_personal_records_across_sessions(db):
    _record(db, [BENCH_S1], at="2026-10-05T10:06:30")
    _record(db, [BENCH_S2], at="2026-10-12T10:05:00")
    rec = personal_records(exercise_sessions(db, UID, BENCH))
    assert rec["heaviest"] == {"weight_kg": 72.5, "reps": 5, "date": "2026-10-12"}
    assert rec["best_e1rm"] == {"e1rm": 84.6, "weight_kg": 72.5, "reps": 5, "date": "2026-10-12"}
    assert rec["max_reps"] == {"reps": 10, "weight_kg": 60, "date": "2026-10-05"}
    assert rec["best_volume_session"] == {"volume": 1540, "working_sets": 3, "date": "2026-10-05"}


def test_alias_name_matches_without_id(db):
    _record(db, [{"name": "卧推", "set_logs": BENCH_S1["set_logs"]}])
    assert len(exercise_sessions(db, UID, BENCH)) == 1


def test_month_calendar_and_period_summary(db):
    _record(db, [BENCH_S1], at="2026-10-05T10:06:30")
    _record(db, [BENCH_S2], at="2026-10-12T10:05:00")
    cal = month_calendar(db, UID, 2026, 10)
    days = {d["date"]: d for d in cal["days"]}
    assert set(days) == {"2026-10-05", "2026-10-12"}
    assert days["2026-10-05"]["sessions"] == 1 and days["2026-10-05"]["working_sets"] == 3
    assert days["2026-10-05"]["volume"] == 1540

    summary = period_summary(db, UID, days=60)
    assert summary["sessions"] == 2
    assert summary["training_days"] == 2
    assert summary["working_sets"] == 4                # 3 + 1（热身除外）
    assert summary["volume"] == 1540 + 362
    # 肌群只归口 primary 主肌群：4 组全部记 chest，不重复记肩/三头
    assert summary["by_muscle"] == {"chest": 4}
    assert summary["avg_duration_min"] == 6


def test_period_summary_window_excludes_old(db):
    _record(db, [BENCH_S1], at="2020-01-01T10:00:00")
    summary = period_summary(db, UID, days=30)
    assert summary["sessions"] == 0 and summary["working_sets"] == 0


def test_browser_z_suffix_timestamps(db):
    """回归：浏览器 toISOString 带 Z 后缀与毫秒，时长计算不崩溃且口径一致。"""
    _record(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH, "set_logs": [
        {"weight_kg": 60, "reps": 10, "at": "2026-10-24T15:01:45.296Z"},
        {"weight_kg": 65, "reps": 8, "at": "2026-10-24T15:04:12.480Z"}]}])
    s = exercise_sessions(db, UID, BENCH)[0]
    assert s["duration_min"] == 2
    assert s["volume"] == 60 * 10 + 65 * 8


def test_custom_exercise_end_to_end(db):
    """P0-2 回归：自定义动作 创建 → 训练 → 历史/PR → 肌群归口 → 派生状态。"""
    doc = {"id": "my_chest_press", "name": "自定义胸推", "aliases": ["胸推"],
           "pattern": "h_push", "primary": ["chest"], "status": "draft", "scope": "user"}
    assert db.add_custom_exercise(UID, "my_chest_press", doc) is not None

    # 携带稳定 id 训练（save_checkin 派生聚合后传入 record_checkin 的形态）
    _record(db, [{"name": "自定义胸推", "exercise_id": "my_chest_press",
                  "sets": 2, "weight_kg": 52.5, "reps": 8,
                  "set_logs": [{"weight_kg": 50, "reps": 8, "at": "2026-10-20T10:00:00"},
                               {"weight_kg": 52.5, "reps": 8, "at": "2026-10-20T10:03:00"}]}])

    # 历史与个人纪录（此前内置库匹配会漏掉自定义动作）
    sessions = exercise_sessions(db, UID, "my_chest_press")
    assert len(sessions) == 1
    assert sessions[0]["volume"] == 400 + 420  # 50×8 + 52.5×8
    rec = personal_records(sessions)
    assert rec["heaviest"]["weight_kg"] == 52.5

    # 肌群归口用自定义动作自身定义的 primary（chest），而非 other
    summary = period_summary(db, UID, days=60)
    assert summary["by_muscle"] == {"chest": 2}

    # 派生状态（user_exercise 的 last_weight）覆盖自定义动作
    state = db.get_user_exercise(UID, "my_chest_press")
    assert state is not None and state["last_weight"] == 52.5

    # 旧记录（无 ID）按本人自定义动作名称/别名回退解析
    _record(db, [{"name": "胸推", "sets": 1, "weight_kg": 55, "reps": 5,
                  "set_logs": [{"weight_kg": 55, "reps": 5, "at": "2026-10-21T10:00:00"}]}])
    assert len(exercise_sessions(db, UID, "my_chest_press")) == 2


def test_session_meta_local_date_and_duration(db):
    """会话元数据：日历按用户本地日期分组；时长优先真实起止。"""
    _record(db, [{"name": "杠铃平板卧推", "exercise_id": BENCH, "set_logs": [
        {"weight_kg": 60, "reps": 10, "at": "2026-10-24T15:01:45.296Z"}]}], at="2026-10-24T15:02:00")
    # 把该记录补上会话元数据（服务端创建于本地 10-24，用户本地日期为 10-25）
    row = db.list_checkins(UID, 1)[0]
    data = {**row["data"], "session_meta": {
        "session_id": "s-x", "mode": "free",
        "started_at": "2026-10-24T15:00:00.000Z",
        "completed_at": "2026-10-24T15:25:00.000Z",
        "timezone": "Asia/Shanghai", "local_date": "2026-10-25"}}
    db.conn.execute("UPDATE checkins SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), row["id"]))
    db.conn.commit()

    assert exercise_sessions(db, UID, BENCH)[0]["date"] == "2026-10-25"   # 本地日期优先
    assert exercise_sessions(db, UID, BENCH)[0]["duration_min"] == 25     # 真实起止优先

    cal = month_calendar(db, UID, 2026, 10)
    assert [d["date"] for d in cal["days"]] == ["2026-10-25"]             # 按本地日期入格
    summary = period_summary(db, UID, days=30)
    assert summary["avg_duration_min"] == 25
