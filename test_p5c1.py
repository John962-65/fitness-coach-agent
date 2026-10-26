"""P5-C1：确定性下一次训练候选引擎回归。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.analytics.exercise_metrics import exercise_sessions
from coach.plan import generate_plan
from coach.rehab import restriction_service
from coach.training_progression import (
    build_next_training_context, get_next_training_options,
)
from coach.training_progression.comparability import parse_target
from test_repair_regressions import profile

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5c1.db")
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


def bench_plan_context(c):
    plan = c.get("/api/users/u/plan").json()
    day = next(d for d in plan["content"]["schedule"]
               if any(e["exercise_id"] == "barbell_bench_press"
                      for e in d["exercises"]))
    idx = next(i for i, e in enumerate(day["exercises"])
               if e["exercise_id"] == "barbell_bench_press")
    return {
        "plan_id": plan["plan_id"], "plan_version": plan["version"],
        "planned_day": day["day"], "index": idx,
        "planned_exercise_id": "barbell_bench_press",
    }, day["exercises"][idx]


def d(offset: int) -> str:
    return (date.today() - timedelta(days=offset)).isoformat()


def save_sets(c, exercise_id, logs, *, offset=2, name=None,
              superset_group=None):
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{
            "name": name or exercise_id, "exercise_id": exercise_id,
            "superset_group": superset_group,
            "set_logs": logs,
        }],
        "session_meta": {"mode": "free", "local_date": d(offset)}}})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def bench_logs(reps, weight=60, sets=4, rpe=None):
    return [{"type": "weight_reps", "weight_kg": weight, "reps": reps,
             **({"rpe": rpe} if rpe is not None else {})} for _ in range(sets)]


def option_ids(result):
    return [o["option_id"] for o in result["options"]]


def test_scenario_a_normal_strength_progression_uses_real_records(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    target_sets = int(entry["sets"])
    target = parse_target(entry["reps"])
    save_sets(c, "barbell_bench_press",
              bench_logs(target["max"], weight=60, sets=target_sets), offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(target["max"], weight=60, sets=target_sets), offset=2)
    plan_version = c.get("/api/users/u/plan").json()["version"]
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    ctx = result["context"]
    assert ctx["plan_prescription_applies"] is True
    assert ctx["current_prescription"]["sets"] == target_sets
    assert ctx["data_quality"]["comparable_session_count"] == 2
    assert ctx["data_quality"]["latest_session_comparable"] is True
    ids = option_ids(result)
    assert "keep-current" in ids
    assert "consider-increase-load" in ids
    load = next(o for o in result["options"]
                if o["option_id"] == "consider-increase-load")
    assert load["proposed_targets"]["weight_kg"] == 62.5
    assert load["proposed_targets"]["sets"] == target_sets
    assert "plan" in load["action_scope"]
    assert load["requires_confirmation"] is True
    fact_ids = {x["fact_id"] for x in ctx["fact_refs"]}
    assert all(fid in fact_ids for fid in load["basis_fact_ids"])
    assert load["source_ids"]
    assert c.get("/api/users/u/plan").json()["version"] == plan_version


def test_scenario_b_insufficient_and_incomparable_reps(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    target = parse_target(_entry["reps"])
    save_sets(c, "barbell_bench_press",
              bench_logs(target["min"], weight=60, sets=2), offset=3)
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    ids = option_ids(result)
    assert "keep-current" in ids
    assert "complete-target-reps" in ids
    assert "consider-increase-load" not in ids
    assert result["context"]["data_quality"]["comparable_session_count"] == 1
    assert any("可比记录不足 2 次" in x
               for x in result["options"][0]["limitations"])

    save_sets(c, "barbell_bench_press",
              bench_logs(3, weight=70, sets=4), offset=1)
    result2 = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert "consider-increase-load" not in option_ids(result2)
    assert result2["context"]["data_quality"]["latest_session_comparable"] is False
    # 70×3 不得因为重量更高被当作比 60×10 更强的目标训练
    assert any("次数不在目标范围" in reason
               for reasons in result2["context"]["data_quality"][
                   "comparable_exclusions"].values()
               for reason in reasons)


def test_scenario_c_complex_and_superset_context(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    complex_logs = [
        {"method": "drop_set", "segments": [
            {"weight_kg": 80, "reps": 8}, {"weight_kg": 65, "reps": 6}]},
        {"method": "drop_set", "segments": [
            {"weight_kg": 80, "reps": 8}, {"weight_kg": 65, "reps": 6}]},
    ]
    save_sets(c, "barbell_bench_press", complex_logs, offset=2)
    save_sets(c, "barbell_bench_press", complex_logs, offset=1)
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    latest = result["context"]["last_actual_performance"]
    assert latest["sets"][0]["method"] == "drop_set"
    assert len(latest["sets"][0]["segments"]) == 2
    assert "consider-increase-load" not in option_ids(result)
    assert any("复杂组" in x for x in result["options"][0]["limitations"])

    # 超级组组织必须出现在建议限制中
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=4), offset=6,
              superset_group="A")
    result2 = build_next_training_context(
        db, "u", "barbell_bench_press", pctx).as_dict()
    assert result2["data_quality"]["superset"] is True


def test_unilateral_incomplete_side_is_not_comparable(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    only_left = [{"method": "unilateral", "segments": [
        {"side": "left", "weight_kg": 20, "reps": 10}]}]
    save_sets(c, "barbell_bench_press", only_left, offset=2)
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert result["context"]["data_quality"]["latest_session_comparable"] is False
    assert any("左右侧不完整" in reason
               for reasons in result["context"]["data_quality"][
                   "comparable_exclusions"].values()
               for reason in reasons)
    assert "consider-increase-load" not in option_ids(result)


def test_scenario_d_all_record_types_use_their_own_metrics(client):
    c, db = client
    # 自重：不使用 e1RM
    save_sets(c, "pull_up", [{"type": "bodyweight_reps", "reps": 8}] * 2, offset=2)
    bw = get_next_training_options(db, "u", "pull_up")
    assert bw["context"]["measurement_type"] == "bodyweight_reps"
    assert bw["context"]["last_actual_performance"]["best_e1rm"] is None
    assert "consider-increase-load" not in option_ids(bw)

    # 辅助：看次数与辅助重量，不因辅助变小直接宣称力量增长
    db.add_custom_exercise("u", "assisted_dip", {
        "id": "assisted_dip", "name": "辅助臂屈伸", "pattern": "h_push",
        "primary": ["chest"], "equipment": ["bodyweight"],
        "location": ["gym", "home"], "measurement": "assisted_reps",
        "level_min": "beginner", "activity": "strength",
        "status": "approved", "scope": "user"})
    save_sets(c, "assisted_dip", [
        {"type": "assisted_reps", "reps": 8, "assistance_kg": 20}] * 3, offset=2)
    assisted = get_next_training_options(db, "u", "assisted_dip")
    assert assisted["context"]["measurement_type"] == "assisted_reps"
    assert assisted["context"]["last_actual_performance"]["best_e1rm"] is None
    assert "consider-increase-load" not in option_ids(assisted)

    # 持续有氧：时长/距离/配速；无力量 e1RM
    save_sets(c, "running", [
        {"type": "distance_time", "distance_m": 5000,
         "duration_seconds": 1200}], offset=2)
    save_sets(c, "running", [
        {"type": "distance_time", "distance_m": 5200,
         "duration_seconds": 1200}], offset=1)
    cardio = get_next_training_options(db, "u", "running")
    assert cardio["context"]["activity_class"] == "steady_cardio"
    perf = cardio["context"]["last_actual_performance"]
    assert perf["steady_cardio_distance_m"] == 5200
    assert perf["pace_sec_per_km"] == round(1200 / 5.2, 1)
    assert perf["best_e1rm"] is None

    # HIIT：实际轮次/工作/休息，不把计划时长当实际
    meta = {"name": "四轮", "exercise_id": "custom_hiit",
            "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                        "work_seconds": 30, "rest_seconds": 20, "rounds": 4}],
            "planned_rounds": 4, "completed_rounds": 3,
            "work_seconds_done": 90, "rest_seconds_done": 50,
            "skipped": [{"block": 0, "round": 4}],
            "ended_early": True, "end_reason": "时间不够"}
    save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 140, "hiit": meta}], offset=1)
    interval = get_next_training_options(db, "u", "custom_hiit")
    assert interval["context"]["activity_class"] == "interval"
    last = interval["context"]["last_actual_performance"]
    assert last["interval_work_seconds"] == 90
    assert last["interval_rest_seconds"] == 50
    assert last["interval_elapsed_seconds"] == 140
    assert last["interval_planned_rounds"] == 4
    assert last["interval_completed_rounds"] == 3
    assert "complete-interval-plan" in option_ids(interval)


def test_scenario_e_recovery_is_fact_not_diagnosis(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=3)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=1)
    rec = c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "sleep_hours": 4.5, "fatigue": 5,
        "muscle_soreness": 4, "training_readiness": 2,
        "notes": "最近工作忙"}})
    assert rec.status_code == 200, rec.text
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    observe = next((o for o in result["options"]
                    if o["option_id"] == "observe-recovery"), None)
    assert observe is not None
    text = observe["title"] + " ".join(observe["limitations"])
    assert "因果关系" in text and "医疗" in text
    assert "过度训练" not in observe["title"]
    assert observe["proposed_targets"] == {}
    assert observe["data_quality"]["signals"] == [
        "fatigue", "muscle_soreness", "sleep_hours"]


def test_scenario_f_safety_blocks_candidates_and_direct_edit(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=3)
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推时肩部疼痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [], "movements": ["barbell_bench_press"]},
    })
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert result["recommendations_allowed"] is False
    assert result["options"] == []
    assert any("限制" in x or "安全" in x for x in result["blocked_reasons"])
    plan = c.get("/api/users/u/plan").json()
    denied = c.post("/api/users/u/changes/ai", json={
        "target": "plan",
        "operations": [{
            "op": "edit_set_prescription", "day": pctx["planned_day"],
            "index": pctx["index"], "weight_kg": 65}],
        "reason": "尝试直接加重",
        "base_version": plan["base_version"]})
    assert denied.status_code == 422
    assert "限制" in str(denied.json())


def test_replacement_analyzes_actual_but_keeps_planned_identity(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    plan_before = c.get("/api/users/u/plan").json()
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{
            "name": "哑铃卧推", "exercise_id": "dumbbell_bench_press",
            "session_replacement_of": "barbell_bench_press",
            "session_replacement": {
                "planned_exercise_id": "barbell_bench_press",
                "planned_name": "杠铃平板卧推",
                "planned_index": pctx["index"],
                "actual_exercise_id": "dumbbell_bench_press",
                "actual_measurement": "weight_reps", "scope": "session"},
            "set_logs": [{"type": "weight_reps", "weight_kg": 20, "reps": 10}] * 3,
        }],
        "session_meta": {"mode": "planned", "local_date": d(1),
                         "day": pctx["planned_day"],
                         "plan_id": plan_before["plan_id"],
                         "plan_version": plan_before["version"]}}})
    assert resp.status_code == 200, resp.text
    result = get_next_training_options(
        db, "u", "dumbbell_bench_press", pctx)
    ctx = result["context"]
    assert ctx["data_quality"]["temporary_replacement"] is True
    assert ctx["planned_exercise"]["exercise_id"] == "barbell_bench_press"
    assert ctx["plan_prescription_applies"] is False
    assert ctx["last_actual_performance"]["replacement"]["scope"] == "session"
    assert ctx["last_actual_performance"]["replacement"]["actual_measurement"] == "weight_reps"
    assert all("plan" not in o["action_scope"] for o in result["options"])
    assert c.get("/api/users/u/plan").json()["version"] == plan_before["version"]


def test_plan_weight_mismatch_is_not_used_as_actual_base(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    target = parse_target(entry["reps"])
    plan = c.get("/api/users/u/plan").json()
    content = plan["content"]
    day = next(d for d in content["schedule"] if d["day"] == pctx["planned_day"])
    day["exercises"][pctx["index"]]["weight_kg"] = 100
    db.create_plan("u", content)
    plan2 = c.get("/api/users/u/plan").json()
    pctx2 = {**pctx, "plan_id": plan2["plan_id"],
             "plan_version": plan2["version"]}
    save_sets(c, "barbell_bench_press",
              bench_logs(target["max"], weight=60, sets=int(entry["sets"])),
              offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(target["max"], weight=60, sets=int(entry["sets"])),
              offset=2)
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx2)
    assert "consider-increase-load" not in option_ids(result)
    assert "complete-target-reps" in option_ids(result)
    assert any("计划重量当作已完成基数" in x
               for o in result["options"] for x in o["limitations"])


def test_duplicate_action_entries_do_not_invent_sessions(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    target = parse_target(entry["reps"])
    logs = bench_logs(target["max"], weight=60, sets=int(entry["sets"]))
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [
            {"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
             "set_logs": logs},
            {"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
             "set_logs": logs},
        ],
        "session_meta": {"mode": "free", "local_date": d(1)}}})
    assert resp.status_code == 200
    sessions = exercise_sessions(db, "u", "barbell_bench_press")
    assert len(sessions) == 1
    assert sessions[0]["duplicate_entries"] == 2
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert result["context"]["data_quality"]["comparable_session_count"] == 0
    assert "consider-increase-load" not in option_ids(result)


def test_p3_reorder_then_edit_cannot_bypass_restriction(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推肩痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [], "movements": ["barbell_bench_press"]},
    })
    plan = c.get("/api/users/u/plan").json()
    day = next(d for d in plan["content"]["schedule"]
               if d["day"] == pctx["planned_day"])
    bench_idx = next(i for i, e in enumerate(day["exercises"])
                     if e["exercise_id"] == "barbell_bench_press")
    other_idx = 1 if bench_idx == 0 else 0
    operations = [
        {"op": "reorder_exercise", "day": pctx["planned_day"],
         "from": bench_idx, "to": other_idx},
        {"op": "edit_set_prescription", "day": pctx["planned_day"],
         "index": other_idx, "weight_kg": 65},
    ]
    denied = c.post("/api/users/u/changes/ai", json={
        "target": "plan", "operations": operations, "reason": "错位绕过测试",
        "base_version": plan["base_version"]})
    assert denied.status_code == 422
    assert "限制" in str(denied.json())


def test_restore_old_plan_cannot_bypass_active_restriction(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    plan1 = c.get("/api/users/u/plan").json()
    content2 = {**plan1["content"], "adjust_reason": "新版"}
    db.create_plan("u", content2)
    plan2 = c.get("/api/users/u/plan").json()
    assert plan2["version"] == plan1["version"] + 1
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推肩痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [], "movements": ["barbell_bench_press"]},
    })
    restored = c.post(f"/api/users/u/plan/revisions/{plan1['version']}/restore",
                      json={"reason": "恢复旧版"})
    assert restored.status_code == 422
    assert "限制" in str(restored.json())


def test_superset_offers_direction_not_numeric_load(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    target = parse_target(entry["reps"])
    sets = int(entry["sets"])
    save_sets(c, "barbell_bench_press",
              bench_logs(target["max"], weight=60, sets=sets), offset=4,
              superset_group="A")
    save_sets(c, "barbell_bench_press",
              bench_logs(target["max"], weight=60, sets=sets), offset=2,
              superset_group="A")
    result = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert result["context"]["data_quality"]["superset"] is True
    load = next((o for o in result["options"]
                 if o["option_id"] == "consider-increase-load"), None)
    if load:
        assert "weight_kg" not in load["proposed_targets"]
        assert any("超级组" in x for x in load["limitations"])


def test_stale_plan_and_unknown_increment_never_invent_targets(client):
    c, db = client
    db.add_custom_exercise("u", "custom_plate_press", {
        "id": "custom_plate_press", "name": "自定义片式推胸",
        "pattern": "h_push", "primary": ["chest"],
        "equipment": ["barbell", "bench"], "location": ["gym"],
        "measurement": "weight_reps", "level_min": "beginner",
        "activity": "strength", "status": "approved", "scope": "user"})
    db.create_plan("u", {
        "template": "p5c-test", "level": "beginner", "days_per_week": 1,
        "goal_version": 1, "schedule": [{
            "day": "测试日", "focus": "胸", "exercises": [{
                "exercise_id": "custom_plate_press", "name": "自定义片式推胸",
                "sets": 3, "reps": "8-12"}]}], "notes": []})
    plan = c.get("/api/users/u/plan").json()
    pctx = {"plan_id": plan["plan_id"], "plan_version": plan["version"],
            "planned_day": "测试日", "index": 0,
            "planned_exercise_id": "custom_plate_press"}
    save_sets(c, "custom_plate_press",
              bench_logs(12, weight=60, sets=3), offset=3,
              name="自定义片式推胸")
    save_sets(c, "custom_plate_press",
              bench_logs(12, weight=60, sets=3), offset=1,
              name="自定义片式推胸")
    result = get_next_training_options(db, "u", "custom_plate_press", pctx)
    load = next((o for o in result["options"]
                 if o["option_id"] == "consider-increase-load"), None)
    assert load is not None
    assert "weight_kg" not in load["proposed_targets"]
    assert load["data_quality"]["increment_source"] == "unknown_no_exact_increment"
    assert any("不虚构精确重量" in x for x in load["limitations"])

    stale = {**pctx, "plan_version": plan["version"] + 99}
    stale_result = get_next_training_options(
        db, "u", "custom_plate_press", stale)
    assert stale_result["context"]["plan_prescription_applies"] is False
    assert "consider-increase-load" not in option_ids(stale_result)
    assert any("计划上下文" in x for x in stale_result["blocked_reasons"])
