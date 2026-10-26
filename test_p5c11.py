"""P5-C1.1：候选引擎收尾回归——可比性/目标达成分离、档位来源分级、HIIT 身份。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.plan import generate_plan
from coach.training_progression import get_next_training_options
from coach.training_progression.comparability import (
    parse_target, target_attainment,
)
from test_p5c1 import bench_logs, bench_plan_context, d, option_ids, save_sets
from test_repair_regressions import profile


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5c11.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.create_plan("u", generate_plan(profile()))
        places = c.get("/api/users/u/locations").json()
        gym = next(x for x in places["locations"] if x["kind"] == "gym")
        c.patch(f"/api/users/u/locations/{gym['id']}", json={
            "required_equipment": ["barbell", "dumbbell", "bench",
                                   "pullup_bar", "treadmill", "machine"],
            "optional_equipment": []})
        c.post(f"/api/users/u/locations/{gym['id']}/select", json={})
        yield c, db


# ---- 目标达成分类（纯函数边界） ----

def _session(reps_list, weight=60):
    return {"activity_classes": ["strength"], "sets": [
        {"activity_class": "strength", "type": "weight_reps",
         "method": "straight_set", "weight_kg": weight, "reps": r}
        for r in reps_list]}


def test_target_attainment_classifies_all_boundaries():
    target = parse_target("8-12")
    assert target_attainment(_session([12, 12]), target)["level"] == "at_top"
    assert target_attainment(_session([8, 10]), target)["level"] == "met_min"
    assert target_attainment(_session([7, 10]), target)["level"] == "below_target"
    assert target_attainment(_session([13, 13]), target)["level"] == "above_range"
    # 混合：部分低于下沿、部分超出上沿 → 低于目标（带说明）
    mixed = target_attainment(_session([7, 13]), target)
    assert mixed["level"] == "below_target" and "超出" in mixed["note"]
    # 数据不足
    assert target_attainment(_session([]), target)["level"] == "insufficient_data"
    assert target_attainment(_session([10]), None)["level"] == "insufficient_data"


def test_target_attainment_duration_kind():
    target = {"kind": "duration", "seconds": 60, "raw": "60秒"}
    ok = target_attainment({"activity_classes": ["strength"], "sets": [
        {"activity_class": "strength", "type": "duration",
         "duration_seconds": 65}]}, target)
    assert ok["level"] == "at_top"
    short = target_attainment({"activity_classes": ["strength"], "sets": [
        {"activity_class": "strength", "type": "duration",
         "duration_seconds": 40}]}, target)
    assert short["level"] == "below_target"


# ---- 验收 A：未达标记录仍参与目标完成分析 ----

def test_acceptance_a_below_target_still_analyzed_for_completion(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    target = parse_target(entry["reps"])
    below = target["min"] - 1
    cid = save_sets(c, "barbell_bench_press",
                    bench_logs(below, weight=60, sets=int(entry["sets"]),
                               rpe=7), offset=2)
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    comp = result["context"]["comparability"]
    # 结构可比：未达标不排除出集合
    assert str(cid) in comp["structurally_comparable"]
    assert comp["comparison_limitations"] == {}
    att = comp["target_attainment"][str(cid)]
    assert att["level"] == "below_target"
    ids = option_ids(result)
    # 仍能分析"完成目标"——给出先完成次数的候选
    assert "complete-target-reps" in ids
    complete = next(o for o in result["options"]
                    if o["option_id"] == "complete-target-reps")
    assert complete["data_quality"]["latest_target_attainment"] == "below_target"
    assert f"{target['min']}-{target['max']}" in complete["title"]
    # 加重仍必须满足明确完成标准：未达标不给加重
    assert "consider-increase-load" not in ids


# ---- 验收 B：历史重量差不是已确认档位，不生成明确加重数值 ----

def _custom_press_plan(c, db):
    db.add_custom_exercise("u", "custom_gap_press", {
        "id": "custom_gap_press", "name": "自定义档差推举", "pattern": "h_push",
        "primary": ["chest"], "equipment": ["barbell", "bench"],
        "location": ["gym"], "measurement": "weight_reps",
        "level_min": "beginner", "activity": "strength",
        "status": "approved", "scope": "user"})
    db.create_plan("u", {
        "template": "p5c11-test", "level": "beginner", "days_per_week": 1,
        "goal_version": 1, "schedule": [{
            "day": "档差日", "focus": "胸", "exercises": [{
                "exercise_id": "custom_gap_press", "name": "自定义档差推举",
                "sets": 3, "reps": "8-12"}]}], "notes": []})
    plan = c.get("/api/users/u/plan").json()
    return {"plan_id": plan["plan_id"], "plan_version": plan["version"],
            "planned_day": "档差日", "index": 0,
            "planned_exercise_id": "custom_gap_press"}


def test_acceptance_b_observed_weight_gap_is_not_executable_increment(client):
    c, db = client
    # 对照：内置动作已验证档位（barbell 2.5kg）生成明确数值（先在原计划下完成）
    pctx2, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(parse_target(entry["reps"])["max"], weight=60,
                         sets=int(entry["sets"])), offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(parse_target(entry["reps"])["max"], weight=60,
                         sets=int(entry["sets"])), offset=2)
    result2 = get_next_training_options(db, "u", "barbell_bench_press", pctx2)
    load2 = next(o for o in result2["options"]
                 if o["option_id"] == "consider-increase-load")
    assert load2["proposed_targets"]["weight_kg"] == 62.5
    assert load2["data_quality"]["increment_verified"] is True
    assert load2["data_quality"]["increment_source"] == \
        "exercise_progression_metadata"

    # 历史重量差 10kg、无已确认档位 → 只给方向
    pctx = _custom_press_plan(c, db)
    ramp = [bench_logs(12, weight=60, sets=1)[0]] + bench_logs(12, weight=70, sets=2)
    save_sets(c, "custom_gap_press", ramp, offset=8, name="自定义档差推举")
    save_sets(c, "custom_gap_press", bench_logs(12, weight=70, sets=3),
              offset=4, name="自定义档差推举")
    save_sets(c, "custom_gap_press", bench_logs(12, weight=70, sets=3),
              offset=2, name="自定义档差推举")
    result = get_next_training_options(db, "u", "custom_gap_press", pctx)
    load = next((o for o in result["options"]
                 if o["option_id"] == "consider-increase-load"), None)
    assert load is not None  # 完成标准满足，方向可以给
    assert "weight_kg" not in load["proposed_targets"]
    assert load["data_quality"]["increment_source"] == "observed_history"
    assert load["data_quality"]["increment_verified"] is False
    assert any("历史" in x and "档位" in x for x in load["limitations"])


def test_user_configured_custom_exercise_increment_is_verified(client):
    c, db = client
    db.add_custom_exercise("u", "custom_cfg_press", {
        "id": "custom_cfg_press", "name": "自配档位推举", "pattern": "h_push",
        "primary": ["chest"], "equipment": ["barbell", "bench"],
        "location": ["gym"], "measurement": "weight_reps",
        "level_min": "beginner", "activity": "strength",
        "status": "approved", "scope": "user",
        "progression": {"type": "load", "increment_kg": 5}})
    db.create_plan("u", {
        "template": "p5c11-cfg", "level": "beginner", "days_per_week": 1,
        "goal_version": 1, "schedule": [{
            "day": "自配日", "focus": "胸", "exercises": [{
                "exercise_id": "custom_cfg_press", "name": "自配档位推举",
                "sets": 3, "reps": "8-12"}]}], "notes": []})
    plan = c.get("/api/users/u/plan").json()
    pctx = {"plan_id": plan["plan_id"], "plan_version": plan["version"],
            "planned_day": "自配日", "index": 0,
            "planned_exercise_id": "custom_cfg_press"}
    save_sets(c, "custom_cfg_press", bench_logs(12, weight=60, sets=3),
              offset=4, name="自配档位推举")
    save_sets(c, "custom_cfg_press", bench_logs(12, weight=60, sets=3),
              offset=2, name="自配档位推举")
    result = get_next_training_options(db, "u", "custom_cfg_press", pctx)
    load = next(o for o in result["options"]
                if o["option_id"] == "consider-increase-load")
    assert load["proposed_targets"]["weight_kg"] == 65
    assert load["data_quality"]["increment_source"] == \
        "user_exercise_progression_metadata"
    assert load["data_quality"]["increment_verified"] is True


# ---- 验收 C：HIIT 不同动作编排不可直接比较 ----

def _hiit_meta(block_exercise_id, block_name, *, completed=4, skipped=None,
               ended=False):
    return {"name": "同编排", "exercise_id": "custom_hiit",
            "blocks": [{"name": block_name,
                        "exercise_id": block_exercise_id,
                        "work_seconds": 30, "rest_seconds": 20,
                        "rounds": 4}],
            "planned_rounds": 4, "completed_rounds": completed,
            "work_seconds_done": 120, "rest_seconds_done": 80,
            "skipped": skipped or [],
            "ended_early": ended,
            **({"end_reason": "时间不够"} if ended else {})}


def test_acceptance_c_hiit_identity_in_signature(client):
    c, db = client
    # 开合跳 与 高抬腿：相同计时编排，不同动作身份 → 不可比
    id1 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("jumping_jack", "开合跳")}], offset=4)
    id2 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("high_knees", "高抬腿")}], offset=2)
    result = get_next_training_options(db, "u", "custom_hiit")
    comp = result["context"]["comparability"]
    assert comp["structurally_comparable"] == [str(id2)]
    reasons = comp["comparison_limitations"][str(id1)]
    assert any("动作身份" in r and "不同活动" in r for r in reasons)

    # 同一动作、同编排 → 可比
    id3 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("jumping_jack", "开合跳")}], offset=1)
    result3 = get_next_training_options(db, "u", "custom_hiit")
    comp3 = result3["context"]["comparability"]
    assert str(id3) in comp3["structurally_comparable"]
    assert str(id1) in comp3["structurally_comparable"]


def test_hiit_custom_activity_identity_distinguishes_sessions(client):
    c, db = client
    # 块 exercise_id 无法解析 → 保存时重置 custom_hiit，块名成为身份
    id1 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("custom_hiit", "自编开合跳循环")}], offset=3)
    id2 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("custom_hiit", "自编波比跳循环")}], offset=2)
    id3 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("custom_hiit", "自编开合跳循环")}], offset=1)
    result = get_next_training_options(db, "u", "custom_hiit")
    comp = result["context"]["comparability"]
    # 自定义身份不同 → 不可比；同名同编排 → 可比
    assert comp["structurally_comparable"] == [str(id3), str(id1)]
    assert any("动作身份" in r
               for r in comp["comparison_limitations"][str(id2)])


def test_hiit_timing_change_breaks_comparability_with_same_identity(client):
    c, db = client
    save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 200,
         "hiit": _hiit_meta("jumping_jack", "开合跳")}], offset=3)
    id2 = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 240,
         "hiit": {"name": "同编排", "exercise_id": "custom_hiit",
                  "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                              "work_seconds": 40, "rest_seconds": 20,
                              "rounds": 4}],
                  "planned_rounds": 4, "completed_rounds": 4,
                  "work_seconds_done": 160, "rest_seconds_done": 80,
                  "skipped": [], "ended_early": False}}], offset=1)
    result = get_next_training_options(db, "u", "custom_hiit")
    comp = result["context"]["comparability"]
    assert comp["structurally_comparable"] == [str(id2)]
    reasons = comp["comparison_limitations"][
        str(result["context"]["recent_sessions"][1]["checkin_id"])]
    assert any("计时编排" in r for r in reasons)


def test_hiit_block_order_breaks_comparability(client):
    c, db = client
    save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 300,
         "hiit": {"name": "双块", "exercise_id": "custom_hiit",
                  "blocks": [
                      {"name": "开合跳", "exercise_id": "jumping_jack",
                       "work_seconds": 30, "rest_seconds": 20, "rounds": 4},
                      {"name": "高抬腿", "exercise_id": "high_knees",
                       "work_seconds": 30, "rest_seconds": 20, "rounds": 2}],
                  "planned_rounds": 6, "completed_rounds": 6,
                  "work_seconds_done": 180, "rest_seconds_done": 120,
                  "skipped": [], "ended_early": False}}], offset=3)
    swapped = save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 300,
         "hiit": {"name": "双块", "exercise_id": "custom_hiit",
                  "blocks": [
                      {"name": "高抬腿", "exercise_id": "high_knees",
                       "work_seconds": 30, "rest_seconds": 20, "rounds": 2},
                      {"name": "开合跳", "exercise_id": "jumping_jack",
                       "work_seconds": 30, "rest_seconds": 20, "rounds": 4}],
                  "planned_rounds": 6, "completed_rounds": 6,
                  "work_seconds_done": 180, "rest_seconds_done": 120,
                  "skipped": [], "ended_early": False}}], offset=1)
    result = get_next_training_options(db, "u", "custom_hiit")
    comp = result["context"]["comparability"]
    # 顺序不同 → 不可比（签名保序）
    assert comp["structurally_comparable"] == [str(swapped)]
    assert any("顺序" in r
               for r in comp["comparison_limitations"][
                   str(result["context"]["recent_sessions"][1]["checkin_id"])])


def test_steady_cardio_records_stay_comparable_regardless_of_target(client):
    """未达时长目标的有氧记录保持结构可比（与力量同口径）。"""
    c, db = client
    pctx, _ = bench_plan_context(c)
    del pctx
    save_sets(c, "running", [
        {"type": "distance_time", "distance_m": 5000,
         "duration_seconds": 1500}], offset=4)
    cid = save_sets(c, "running", [
        {"type": "distance_time", "distance_m": 5000,
         "duration_seconds": 1200}], offset=2)
    result = get_next_training_options(db, "u", "running")
    comp = result["context"]["comparability"]
    assert str(cid) in comp["structurally_comparable"]
    assert len(comp["structurally_comparable"]) == 2
