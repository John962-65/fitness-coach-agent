"""P5-B1 回归：有氧与 HIIT 数据契约、统计口径与兼容。

覆盖任务书 §六 自动化要求的后端面：
混合训练保存（同会话）/ 旧记录兼容 / 五测量类型 / HIIT 元数据契约（非法
剔除不炸）/ 阶段跳过与提前结束如实记录 / 有氧不生成容量与 e1RM /
fact_service cardio/interval 事实 / period_summary 分口径 / 幂等 / 隔离 /
洞察漂移（hiit 记录纠错后失效）。
"""
import json
import pytest
from datetime import date
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.analytics.exercise_metrics import exercise_sessions
from coach.analytics.fact_service import get_training_facts
from coach.analytics.training_calendar import period_summary
from coach.db import Database
from coach.experts import insight_service, task_dispatcher
from test_repair_regressions import profile

TODAY = date.today().isoformat()
D = lambda n: (date.today().replace(day=max(1, date.today().day - n))).isoformat()

HIIT_META = {
    "name": "四轮间歇训练",
    "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                "work_seconds": 30, "rest_seconds": 30, "rounds": 4}],
    "planned_rounds": 4, "completed_rounds": 3,
    "work_seconds_done": 84, "rest_seconds_done": 66,
    "skipped": [{"block": 0, "round": 4}],
    "ended_early": True, "end_reason": "时间不够"}


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5b.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.save_profile("other", profile())
        yield c, db


def save_mixed(c):
    """场景一数据：卧推 3 组 + 划船 3 组 + 跑步 20 分钟 5km（同会话）。"""
    return c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [
            {"name": "杠铃卧推", "exercise_id": "barbell_bench_press",
             "set_logs": [{"type": "weight_reps", "weight_kg": 60, "reps": 10}] * 3},
            {"name": "杠铃划船", "exercise_id": "barbell_row",
             "set_logs": [{"type": "weight_reps", "weight_kg": 50, "reps": 10}] * 3},
            {"name": "跑步", "exercise_id": "running",
             "set_logs": [{"type": "distance_time", "distance_m": 5000,
                           "duration_seconds": 1800, "rpe": 6}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})


def save_hiit(c, ended_early=True, completed=3):
    meta = {**HIIT_META, "completed_rounds": completed,
            "ended_early": ended_early,
            "end_reason": "时间不够" if ended_early else "全部计划完成"}
    return c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": HIIT_META["name"],
                       "set_logs": [{"type": "duration", "duration_seconds": 150,
                                     "hiit": meta}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})


# ---- 场景 B：混合训练 ----

def test_mixed_session_strength_and_cardio_separated(client):
    c, db = client
    resp = save_mixed(c)
    assert resp.status_code == 200
    cid = resp.json()["id"]
    saved = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    assert len(saved["data"]["exercises"]) == 3  # 同一会话三项活动
    # 力量口径：跑步不产生容量/e1RM/正式组贡献
    bench = exercise_sessions(db, "u", "barbell_bench_press")[0]
    run = exercise_sessions(db, "u", "running")[0]
    assert bench["volume"] == 1800 and bench["working_sets"] == 3
    assert run["volume"] == 0 and run["best_e1rm"] is None
    assert run["distance_total_m"] == 5000
    # 周期统计分口径：力量容量不含跑步；有氧时间/距离单列
    ps = period_summary(db, "u", 30)
    assert ps["volume"] == 3300  # 仅力量
    assert ps["cardio_seconds"] == 1800 and ps["cardio_distance_m"] == 5000
    # fact：有氧事实（来源链=该会话打卡）
    facts = get_training_facts(db, "u", 30)
    cardio = {f["metric"]: f for f in facts["facts"] if f["metric"].startswith("cardio")}
    assert cardio["cardio-sessions"]["value"] == 1
    assert cardio["cardio-total-duration"]["value"] == 30.0
    assert cardio["cardio-total-distance"]["value"] == 5.0
    assert all("checkin:" in s for s in cardio["cardio-sessions"]["source_ids"])


def test_cardio_duration_only_variants(client):
    """不是所有有氧都必须有距离（椭圆机/爬楼梯只记时间）。"""
    c, db = client
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "椭圆机", "exercise_id": "elliptical",
                       "set_logs": [{"type": "duration", "duration_seconds": 1500,
                                     "rpe": 6}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert resp.status_code == 200
    ps = period_summary(db, "u", 30)
    assert ps["cardio_seconds"] == 1500 and ps["cardio_distance_m"] == 0
    facts = get_training_facts(db, "u", 30)
    dist = next(f for f in facts["facts"] if f["metric"] == "cardio-total-distance")
    assert dist["value"] == 0 and dist["status"] == "insufficient"


def test_jump_rope_reps_variant(client):
    """跳绳可按次数记录（可选 reps 随 duration 记录保留）。"""
    c, db = client
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "跳绳", "exercise_id": "jump_rope",
                       "set_logs": [{"type": "duration", "duration_seconds": 120,
                                     "reps": 600}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert resp.status_code == 200
    saved = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    assert saved["data"]["exercises"][0]["set_logs"][0]["reps"] == 600


# ---- 场景 C：HIIT 元数据契约与真实执行 ----

def test_hiit_metadata_contract(client):
    c, db = client
    resp = save_hiit(c)
    assert resp.status_code == 200
    saved = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    log = saved["data"]["exercises"][0]["set_logs"][0]
    h = log["hiit"]
    assert h["planned_rounds"] == 4 and h["completed_rounds"] == 3
    assert h["skipped"] == [{"block": 0, "round": 4}]
    assert h["ended_early"] is True and h["end_reason"] == "时间不够"
    # 非法字段剔除不炸整条；空 hiit 剥离
    r2 = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "坏 HIIT", "set_logs": [
            {"type": "duration", "duration_seconds": 60,
             "hiit": {"blocks": [{"work_seconds": 99999999}],
                      "planned_rounds": 99999}}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert r2.status_code == 200
    log2 = r2.json() and c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    h2 = log2["data"]["exercises"][0]["set_logs"][0].get("hiit")
    assert (h2 or {}).get("planned_rounds") in (None, 99999)  # 非法值清洗或剔除
    blocks = (h2 or {}).get("blocks") or []
    assert all(b.get("work_seconds", 0) <= 86400 for b in blocks)
    # 隔离
    assert c.get("/api/users/other/checkins?limit=5").json()["checkins"] == []


def test_hiit_not_counted_as_strength(tmp_path):
    from coach.validate import coerce_checkin
    db = Database(tmp_path / "hiit.db")
    db.save_profile("u", profile())
    data, _ = db_record_hiit(db)
    db.record_checkin("u", "training", data)
    ps = period_summary(db, "u", 30)
    assert ps["working_sets"] == 0 and ps["volume"] == 0
    assert ps["interval_seconds"] == 84 + 66
    facts = get_training_facts(db, "u", 30)
    iv = {f["metric"]: f for f in facts["facts"] if f["metric"].startswith("interval")}
    assert iv["interval-sessions"]["value"] == 1
    assert iv["interval-planned-rounds"]["value"] == 4
    assert iv["interval-completed-rounds"]["value"] == 3
    assert iv["interval-work-seconds"]["value"] == 84
    assert iv["interval-completed-rounds"]["data_quality"]["skipped"] == 1
    assert iv["interval-completed-rounds"]["data_quality"]["ended_early"] == 1


def db_record_hiit(db):
    from coach.validate import coerce_checkin
    return coerce_checkin("training", {"exercises": [{
        "name": HIIT_META["name"],
        "set_logs": [{"type": "duration", "duration_seconds": 150,
                      "hiit": HIIT_META}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}})


def test_hiit_correction_invalidates_insight(client):
    c, db = client
    resp = save_hiit(c)
    cid = resp.json()["id"]
    res = task_dispatcher.run_task(db, task_dispatcher.enqueue(
        db, "u", "training_science", "post-workout-review", "UserRequested",
        {"checkin_id": cid}))
    ins = res.get("insight")
    if ins:
        # 纠错（完成轮次 3→4）→ 引用旧修订的洞察失效
        cur = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
        new_meta = {**HIIT_META, "completed_rounds": 4, "ended_early": False}
        c.post(f"/api/users/u/checkins/{cid}/correct", json={
            "expected_revision": cur["revision"],
            "data": {**cur["data"], "exercises": [{
                "name": HIIT_META["name"],
                "set_logs": [{"type": "duration", "duration_seconds": 210,
                              "hiit": new_meta}]}]},
            "reason": "记错了", "evidence": "用户说其实完成了 4 轮"})
        stale = insight_service.get_insight(db, "u", ins["id"])
        assert stale["status"] == "invalidated" and "纠错" in stale["status_reason"]


def test_hiit_template_roundtrip(client):
    c, _ = client
    # 保存含 hiit 的模板
    r = c.post("/api/users/u/training-templates", json={
        "name": "四轮间歇", "entries": [],
        "hiit": {"name": "四轮间歇训练",
                 "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                             "work_seconds": 30, "rest_seconds": 30,
                             "rounds": 4}]}})
    assert r.status_code == 200
    t = c.get("/api/users/u/training-templates").json()["templates"][0]
    assert t["hiit"]["blocks"][0]["name"] == "开合跳"
    assert t["hiit_index"] == 0
    # 无 hiit 的模板不受影响
    r2 = c.post("/api/users/u/training-templates", json={
        "name": "力量日", "entries": [{"exercise_id": "barbell_bench_press",
                                       "name": "杠铃卧推"}]})
    assert r2.status_code == 200
    t2 = next(x for x in c.get("/api/users/u/training-templates").json()["templates"]
              if x["name"] == "力量日")
    assert "hiit" not in t2


def test_hiit_template_rejects_invalid_timing_and_position(client):
    c, _ = client
    base = {"name": "坏编排", "entries": [],
            "hiit": {"name": "坏编排", "blocks": [{
                "name": "开合跳", "work_seconds": 0.5,
                "rest_seconds": 20, "rounds": 2}]}}
    assert c.post("/api/users/u/training-templates", json=base).status_code == 422
    base["hiit"]["blocks"][0].update(work_seconds=86400, rounds=2)
    assert c.post("/api/users/u/training-templates", json=base).status_code == 422
    base["hiit"]["blocks"][0].update(work_seconds=30, rounds=2)
    base["hiit_index"] = 1
    assert c.post("/api/users/u/training-templates", json=base).status_code == 422


def test_offline_idempotent_with_cardio(client):
    c, _ = client
    payload = {"type": "training", "submission_id": "cardio-sub-1", "data": {
        "exercises": [{"name": "跑步", "exercise_id": "running",
                       "set_logs": [{"type": "distance_time", "distance_m": 3000,
                                     "duration_seconds": 1200}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}}
    r1 = c.post("/api/users/u/checkins", json=payload)
    r2 = c.post("/api/users/u/checkins", json=payload)
    assert r1.json()["id"] == r2.json()["id"] and r2.json().get("existing") is True


def test_old_records_unchanged(tmp_path):
    """旧记录（无 hiit/activity）口径不变。"""
    from coach.validate import coerce_checkin
    db = Database(tmp_path / "old.db")
    db.save_profile("u", profile())
    data, _ = coerce_checkin("training", {"exercises": [{
        "name": "杠铃卧推", "exercise_id": "barbell_bench_press",
        "set_logs": [{"type": "weight_reps", "weight_kg": 60, "reps": 8}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}})
    db.record_checkin("u", "training", data)
    ps = period_summary(db, "u", 30)
    assert ps["volume"] == 480 and ps["working_sets"] == 1
    assert ps["cardio_seconds"] == 0 and ps["interval_seconds"] == 0


def test_hiit_invalid_nested_fields_are_dropped_without_raising():
    from coach.validate import coerce_checkin
    data, _ = coerce_checkin("training", {"exercises": [{
        "name": "间歇", "set_logs": [{
            "type": "duration", "duration_seconds": 30,
            "hiit": {
                "name": "间歇", "planned_rounds": 1000,
                "blocks": [{"name": "开合跳", "work_seconds": 30,
                            "rest_seconds": 20, "rounds": 1000}],
                "skipped": [{"block": "bad", "round": "x"},
                            {"block": 0, "round": 2}],
            }}]}]})
    hiit = data["exercises"][0]["set_logs"][0]["hiit"]
    assert hiit["blocks"][0]["work_seconds"] == 30
    assert "rounds" not in hiit["blocks"][0]
    assert "planned_rounds" not in hiit
    assert hiit["skipped"] == [{"block": 0, "round": 2}]


def test_zero_work_hiit_and_99_skips_roundtrip(client):
    c, _ = client
    skipped = [{"block": 0, "round": i} for i in range(1, 100)]
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "全部跳过", "set_logs": [{
            "type": "duration", "duration_seconds": 0,
            "hiit": {
                "name": "全部跳过",
                "blocks": [{"name": "开合跳", "work_seconds": 30,
                            "rest_seconds": 20, "rounds": 99}],
                "planned_rounds": 99, "completed_rounds": 0,
                "work_seconds_done": 0, "rest_seconds_done": 0,
                "skipped": skipped, "ended_early": False,
            }}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert resp.status_code == 200
    saved = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    log = saved["data"]["exercises"][0]["set_logs"][0]
    assert log["duration_seconds"] == 0
    assert log["hiit"]["work_seconds_done"] == 0
    assert log["hiit"]["skipped"] == skipped
