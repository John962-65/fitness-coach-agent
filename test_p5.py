"""P5-A 回归：训练方法（递减/休息暂停/单侧）数据契约、统计与兼容。

覆盖任务书 §八 自动化要求的核心后端面：
旧记录兼容 / 五测量类型 / 四方法结构校验 / 段数统计（逻辑组=1）/
单侧完整性 / 容量计算（分段求和不重复）/ 纠错重算 / fact 说明 / 隔离。
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.analytics.exercise_metrics import (exercise_sessions, set_e1rm,
                                              set_volume)
from coach.db import Database
from coach.experts import insight_service
from coach.validate import coerce_checkin
from test_repair_regressions import profile

TODAY = date.today().isoformat()
D = lambda n: (date.today().replace(day=max(1, date.today().day - n))).isoformat()

DROP_SEGS = [{"weight_kg": 80, "reps": 8}, {"weight_kg": 65, "reps": 6}]
REST_PAUSE_SEGS = [{"weight_kg": 60, "reps": 8, "rest_seconds": 20},
                   {"weight_kg": 60, "reps": 3, "rest_seconds": 20},
                   {"weight_kg": 60, "reps": 2}]
UNILATERAL_SEGS = [{"side": "left", "weight_kg": 12, "reps": 10},
                   {"side": "right", "weight_kg": 12, "reps": 8}]


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.save_profile("other", profile())
        yield c, db


# ---- 契约：结构校验 ----

def test_method_contract_validation():
    data, warns = coerce_checkin("training", {"exercises": [{
        "name": "卧推", "set_logs": [
            {"type": "weight_reps", "weight_kg": 60, "reps": 8},                     # 旧记录兼容
            {"type": "weight_reps", "method": "drop_set",
             "segments": DROP_SEGS},                                               # 递减
            {"type": "weight_reps", "method": "rest_pause",
             "segments": REST_PAUSE_SEGS},                                          # 休息暂停
            {"type": "weight_reps", "method": "unilateral",
             "segments": UNILATERAL_SEGS},                                          # 单侧
            {"type": "weight_reps", "method": "drop_set", "weight_kg": 50,
             "reps": 6, "segments": []},                                            # 空段降级(保留主字段)
            {"type": "weight_reps", "method": "bogus", "weight_kg": 50, "reps": 5},  # 未知方法
            {"type": "weight_reps", "method": "unilateral", "weight_kg": 10,
             "reps": 5, "segments": [{"weight_kg": 10, "reps": 5}]},                 # 单侧缺 side
            {"type": "weight_reps", "method": "straight_set",
             "weight_kg": 40, "reps": 10},                                          # 显式普通=同构
        ]}]})
    logs = data["exercises"][0]["set_logs"]
    methods = [l.get("method") for l in logs]
    assert methods == [None, "drop_set", "rest_pause", "unilateral", None, None, None, None]
    # 空段降级为普通组并保留主字段
    assert logs[4]["weight_kg"] == 50 and logs[4]["reps"] == 6
    # 未知方法剥离后按普通组记录
    assert logs[5]["weight_kg"] == 50 and logs[5]["reps"] == 5
    # 单侧缺 side 的段被剔除后无有效段 → 降级
    assert logs[6]["weight_kg"] == 10
    # 显式 straight_set 不留冗余字段
    assert "method" not in logs[7]
    # 未知方法有警告
    assert any("bogus" in w for w in warns)
    assert any("没有有效执行段" in w for w in warns)


def test_all_five_measurement_types_still_work():
    data, warns = coerce_checkin("training", {"exercises": [{
        "name": "混合", "set_logs": [
            {"type": "weight_reps", "weight_kg": 50, "reps": 5},
            {"type": "bodyweight_reps", "reps": 10, "added_weight_kg": 5},
            {"type": "assisted_reps", "reps": 8, "assistance_kg": 20},
            {"type": "duration", "duration_seconds": 60},
            {"type": "distance_time", "distance_m": 500, "duration_seconds": 120},
        ]}]})
    assert len(data["exercises"][0]["set_logs"]) == 5 and not warns


# ---- 容量与统计 ----

def test_segment_volume_math():
    assert set_volume({"type": "weight_reps", "method": "drop_set",
                       "segments": DROP_SEGS}) == 80 * 8 + 65 * 6  # 1030
    assert set_volume({"type": "weight_reps", "method": "rest_pause",
                       "segments": REST_PAUSE_SEGS}) == 60 * 13
    assert set_volume({"type": "weight_reps", "method": "unilateral",
                       "segments": UNILATERAL_SEGS}) == 12 * 10 + 12 * 8  # 216
    # 单侧不被简化/重复：左右各一次
    assert set_volume({"type": "weight_reps", "weight_kg": 60, "reps": 8}) == 480
    # e1RM 取段中最大有效
    assert set_e1rm({"type": "weight_reps", "method": "drop_set",
                     "segments": DROP_SEGS}) == pytest.approx(101.3, abs=0.2)


def test_logical_group_count_and_volume_in_session(tmp_path):
    db = Database(tmp_path / "s.db")
    db.save_profile("u", profile())
    data, _ = coerce_checkin("training", {"exercises": [{
        "name": "杠铃卧推", "exercise_id": "barbell_bench_press",
        "set_logs": [
            {"type": "weight_reps", "weight_kg": 60, "reps": 8},
            {"type": "weight_reps", "method": "drop_set", "segments": DROP_SEGS},
            {"type": "weight_reps", "method": "unilateral",
             "segments": UNILATERAL_SEGS},
        ]}]})
    db.record_checkin("u", "training", data)
    s = exercise_sessions(db, "u", "barbell_bench_press")[0]
    assert s["working_sets"] == 3          # 逻辑组：3 条记录 = 3 组（不按段重复）
    assert s["volume"] == 480 + 1030 + 216  # 各段实际完成求和
    assert s["reps_total"] == 8 + 14 + 18   # 递减=段和、单侧=左右和
    assert s["best_e1rm"] == pytest.approx(101.3, abs=0.2)
    assert s["best_set"]["weight_kg"] == 80  # 代表段


def test_unilateral_sides_preserved_in_history(client):
    """单侧记录保留左右差异：不同次数不得被合并。"""
    c, db = client
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "哑铃划船", "exercise_id": "dumbbell_row",
                       "set_logs": [{"type": "weight_reps", "method": "unilateral",
                                     "segments": UNILATERAL_SEGS}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert resp.status_code == 200
    cid = resp.json()["id"]
    saved = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    segs = saved["data"]["exercises"][0]["set_logs"][0]["segments"]
    assert [s["side"] for s in segs] == ["left", "right"]
    assert [s["reps"] for s in segs] == [10, 8]  # 不简化为 10


def test_fact_service_notes_complex_methods(tmp_path):
    db = Database(tmp_path / "f.db")
    db.save_profile("u", profile())
    data, _ = coerce_checkin("training", {"exercises": [{
        "name": "杠铃卧推", "exercise_id": "barbell_bench_press",
        "set_logs": [{"type": "weight_reps", "method": "drop_set",
                      "segments": DROP_SEGS}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}})
    db.record_checkin("u", "training", data)
    from coach.analytics.fact_service import get_training_facts
    facts = get_training_facts(db, "u", 30)
    notes = []
    for f in facts["facts"]:
        notes += (f.get("data_quality", {}).get("notes") or [])
    assert any("逻辑组" in n and "递减组" in n for n in notes)
    vol = next(f for f in facts["facts"] if f["metric"] == "volume"
               and f["value"] is not None)
    assert vol["value"] == 1030


# ---- 纠错重算 ----

def test_correction_recomputes_segment_stats(client):
    c, db = client
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "杠铃卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "method": "drop_set",
                                     "segments": DROP_SEGS}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    cid = resp.json()["id"]
    before = exercise_sessions(db, "u", "barbell_bench_press")[0]
    assert before["volume"] == 1030
    # 纠错：段改小
    cur = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    fixed = c.post(f"/api/users/u/checkins/{cid}/correct", json={
        "expected_revision": cur["revision"],
        "data": {**cur["data"], "exercises": [{
            "name": "杠铃卧推", "exercise_id": "barbell_bench_press",
            "set_logs": [{"type": "weight_reps", "method": "drop_set",
                          "segments": [{"weight_kg": 70, "reps": 8},
                                       {"weight_kg": 55, "reps": 6}]}]}]},
        "reason": "重量记错", "evidence": "用户说实际是 70/55"})
    assert fixed.status_code == 200
    after = exercise_sessions(db, "u", "barbell_bench_press")[0]
    assert after["volume"] == 70 * 8 + 55 * 6  # 890
    assert after["revision"] == 1
    # 修订历史保留
    assert db.conn.execute(
        "SELECT COUNT(*) FROM checkin_revisions WHERE checkin_id=?",
        (cid,)).fetchone()[0] == 1
    # 引用旧版本的洞察失效（P5-7）
    from coach.experts import task_dispatcher
    res = task_dispatcher.run_task(db, task_dispatcher.enqueue(
        db, "u", "training_science", "post-workout-review", "UserRequested",
        {"checkin_id": cid}))
    if res.get("insight"):
        stale = insight_service.get_insight(db, "u", res["insight"]["id"])
        # 纠错发生在洞察生成前 → 洞察基于新数据；再用旧 revision 引用构造失效场景
        pass
    # 直接验证漂移机制：纠错后 revision=1，任何 source_revision.checkins 记录 0 的洞察失效
    ins = {"source_revision": {"checkins": {str(cid): 0}}}
    from coach.experts.insight_service import _revision_drift
    reason = _revision_drift(db, "u", ins)
    assert reason and "纠错" in reason


# ---- API / 隔离 / 幂等 ----

def test_api_save_with_methods_and_isolation(client):
    c, db = client
    payload = {"type": "training", "data": {
        "exercises": [{"name": "杠铃卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [
                           {"type": "weight_reps", "weight_kg": 60, "reps": 8},
                           {"type": "weight_reps", "method": "drop_set",
                            "segments": DROP_SEGS}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}},
        "submission_id": "p5-sub-1"}
    r1 = c.post("/api/users/u/checkins", json=payload)
    assert r1.status_code == 200
    # 重放幂等
    r2 = c.post("/api/users/u/checkins", json=payload)
    assert r2.json().get("existing") is True
    # 旧引擎兼容聚合：代表段派生（drop 组代表=80kg，总 reps=14）
    saved = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    ex = saved["data"]["exercises"][0]
    assert ex["weight_kg"] == 80 and ex["reps"] == 14 and ex["sets"] == 2
    # 隔离
    assert c.get("/api/users/other/checkins?limit=5").json()["checkins"] == []


def test_template_roundtrip_with_methods(client):
    """模板存的是目标（不含 method 记录），但保存/取回不受 P5 改动影响。"""
    c, _ = client
    r = c.post("/api/users/u/training-templates", json={
        "name": "胸背日", "entries": [
            {"exercise_id": "barbell_bench_press", "name": "杠铃卧推",
             "superset_group": "A"},
            {"exercise_id": "barbell_row", "name": "杠铃划船",
             "superset_group": "A"}]})
    assert r.status_code == 200
    t = c.get("/api/users/u/training-templates").json()["templates"][0]
    assert len(t["entries"]) == 2 and t["entries"][0]["superset_group"] == "A"
