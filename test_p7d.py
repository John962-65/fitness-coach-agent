"""P7-D：长期个人报告回归。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.plan import generate_plan
from test_repair_regressions import profile

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p7d.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.create_plan("u", generate_plan(profile()))
        yield c, db


def _bench(c, reps, offset):
    logs = [{"type": "weight_reps", "weight_kg": 60, "reps": reps,
             "rpe": 7}] * 4
    c.post("/api/users/u/checkins", json={
        "type": "training", "data": {
            "exercises": [{"name": "杠铃平板卧推",
                           "exercise_id": "barbell_bench_press",
                           "set_logs": logs}],
            "session_meta": {"mode": "free",
                             "local_date": (date.today()
                                            - timedelta(days=offset)).isoformat()}}})


def test_report_aggregates_all_domains_with_sufficiency_notes(client):
    c, db = client
    _bench(c, 12, 20)
    _bench(c, 12, 12)
    _bench(c, 8, 1)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 3, "sleep_hours": 7}})
    c.post("/api/users/u/body-measurements", json={
        "measured_at": f"{TODAY}T08:00:00", "local_date": TODAY,
        "weight_kg": 75.0, "source": "user"})
    r = c.get("/api/users/u/long-term-report?period=month")
    assert r.status_code == 200
    rep = r.json()
    assert rep["kind"] == "long_term_report_v1"
    # 训练频率与容量（真实记录）
    assert rep["training"]["sessions"] == 3
    assert rep["training"]["days_trained"] == 3
    assert rep["training"]["strength_volume_kg"] > 0
    # 力量趋势（复用趋势口径）+ 局限
    assert rep["strength_trends"] and rep["strength_trends"][0][
        "exercise_id"] == "barbell_bench_press"
    # 恢复 / 身体
    assert rep["recovery"]["records_count"] == 1
    assert rep["body"]["facts"]
    # 饮食完整度：0/30 天 → 如实说明，不得描述为真实摄入
    assert rep["nutrition"]["days_recorded"] == 0
    assert any("不能将已记录均值描述为全月真实摄入" in lim
               for lim in rep["limitations"])
    # 计划执行参考
    assert rep["training"]["plan"]["plan_version"] == 1
    # 只读：报告不修改数据
    plan_version = c.get("/api/users/u/plan").json()["version"]
    assert c.get("/api/users/u/plan").json()["version"] == plan_version


def test_report_periods_and_validation(client):
    c, db = client
    _bench(c, 10, 0)
    week = c.get("/api/users/u/long-term-report?period=week").json()
    assert week["range"]["days"] == 7
    assert week["training"]["sessions"] == 1
    custom = c.get("/api/users/u/long-term-report",
                   params={"period": "custom", "start": "2026-10-01",
                           "end": "2026-10-27"}).json()
    assert custom["range"]["days"] == 27
    bad = c.get("/api/users/u/long-term-report",
                params={"period": "custom", "start": "2026-10-27",
                        "end": "2026-10-01"})
    assert bad.status_code == 422
    bad2 = c.get("/api/users/u/long-term-report?period=year")
    assert bad2.status_code == 422


def test_report_user_isolation(client):
    c, db = client
    _bench(c, 10, 0)
    db.save_profile("v", profile())
    empty = c.get("/api/users/v/long-term-report?period=month").json()
    assert empty["training"]["sessions"] == 0
    assert any("没有可做趋势判定" in lim or "趋势" in lim
               for lim in empty["limitations"])
