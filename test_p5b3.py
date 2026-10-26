"""P5-B3 固定数据集：同一条训练记录跨接口一致。"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.analytics.activity_class import (
    ACTIVITY_CLASS_VERSION, CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH,
    classify_training_record,
)
from coach.analytics.exercise_metrics import exercise_sessions
from coach.analytics.fact_service import get_training_facts
from coach.analytics.training_calendar import month_calendar, period_summary
from coach.experts import task_dispatcher, training_science
from coach.plan import generate_plan
from test_repair_regressions import profile

TODAY = date.today().isoformat()
YEAR, MONTH = date.today().year, date.today().month

BENCH = "barbell_bench_press"
ROW = "barbell_row"
RUN = "running"
HIIT = "custom_hiit"

HIIT_META = {
    "name": "四轮间歇", "exercise_id": HIIT,
    "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                "work_seconds": 30, "rest_seconds": 30, "rounds": 4}],
    "planned_rounds": 4, "completed_rounds": 3,
    "work_seconds_done": 84, "rest_seconds_done": 66,
    "skipped": [{"block": 0, "round": 4}],
    "ended_early": True, "end_reason": "时间不够",
}


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5b3.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.create_plan("u", generate_plan(profile()))
        yield c, db


def training(c, exercises, *, mode="free", day=None, plan=None):
    meta = {"mode": mode, "local_date": TODAY}
    if day:
        meta["day"] = day
    if plan:
        meta.update(plan)
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": exercises, "session_meta": meta}})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def strength_session():
    return [
        {"name": "杠铃平板卧推", "exercise_id": BENCH, "set_logs": [
            {"type": "weight_reps", "weight_kg": 60, "reps": 10}] * 3},
        {"name": "杠铃划船", "exercise_id": ROW, "set_logs": [
            {"type": "weight_reps", "weight_kg": 50, "reps": 10}] * 3},
    ]


def steady_cardio():
    return {"name": "跑步", "exercise_id": RUN, "set_logs": [
        {"type": "distance_time", "distance_m": 5000,
         "duration_seconds": 1200, "rpe": 6}]}


def hiit_exercise(meta=None):
    payload = meta or HIIT_META
    duration = int(payload.get("work_seconds_done") or 0) \
        + int(payload.get("rest_seconds_done") or 0)
    return {"name": "四轮间歇", "exercise_id": HIIT, "set_logs": [
        {"type": "duration", "duration_seconds": duration,
         "hiit": payload}]}


def fact_value(db, metric, measurement="session", uid="u"):
    facts = get_training_facts(db, uid, 30)["facts"]
    matches = [f for f in facts
               if f.get("metric") == metric and f.get("measurement_type") == measurement]
    assert matches, f"missing fact {metric}/{measurement}"
    return matches[0]["value"]


def test_scenario_a_strength_and_steady_cardio(client):
    c, db = client
    cid = training(c, strength_session() + [steady_cardio()])
    ps = period_summary(db, "u", 30)
    assert ps["training_sessions"] == 1 and ps["training_days"] == 1
    assert ps["strength_working_sets"] == 6
    assert ps["strength_volume_kg"] == 3300
    assert ps["steady_cardio_seconds"] == 1200
    assert ps["steady_cardio_distance_m"] == 5000
    assert ps["interval_work_seconds"] == 0
    assert ps["interval_rest_seconds"] == 0
    assert ps["interval_elapsed_seconds"] == 0
    assert ps["by_muscle"] == {"chest": 3, "lats": 3}
    assert ps["classification"]["inferred_records"] == 0
    assert ps["classification"]["version"] == ACTIVITY_CLASS_VERSION
    assert ps["sessions"] == ps["training_sessions"] == 1
    assert ps["working_sets"] == ps["strength_working_sets"] == 6
    assert ps["cardio_seconds"] == ps["steady_cardio_seconds"] == 1200
    # 配速只由有距离记录计算：5000m / 1200s = 240s/km
    run_row = next(x for x in ps["cardio_by_activity"] if x["exercise_id"] == RUN)
    assert run_row["pace_sec_per_km"] == 240.0 and run_row["speed_mps"] == 4.167

    cal = month_calendar(db, "u", YEAR, MONTH)
    day = next(d for d in cal["days"] if d["date"] == TODAY)
    assert day["training_sessions"] == 1 and day["strength_working_sets"] == 6
    assert day["strength_volume_kg"] == 3300
    assert day["steady_cardio_seconds"] == 1200
    assert day["interval_elapsed_seconds"] == 0

    bench = exercise_sessions(db, "u", BENCH)[0]
    run = exercise_sessions(db, "u", RUN)[0]
    assert bench["activity_class"] == CLASS_STRENGTH and bench["working_sets"] == 3
    assert run["activity_class"] == CLASS_STEADY_CARDIO
    assert run["working_sets"] == 0 and run["volume"] == 0
    assert run["steady_cardio_seconds"] == 1200
    assert run["steady_cardio_distance_m"] == 5000

    assert fact_value(db, "training_sessions") == 1
    assert fact_value(db, "strength_working_sets") == 6
    assert fact_value(db, "strength_volume_kg") == 3300
    assert fact_value(db, "steady_cardio_seconds") == 1200
    assert fact_value(db, "interval_work_seconds") == 0
    action_pace = next(f for f in get_training_facts(db, "u", 30)["facts"]
                       if f["metric"] == "steady-cardio-pace"
                       and f.get("exercise_id") == RUN)
    assert action_pace["value"] == 240.0
    assert c.get(f"/api/users/u/checkins?limit=1").json()["checkins"][0]["id"] == cid


def test_cardio_without_distance_never_gets_speed_or_pace(client):
    c, db = client
    training(c, [{"name": "椭圆机", "exercise_id": "elliptical", "set_logs": [
        {"type": "duration", "duration_seconds": 900}]}])
    ps = period_summary(db, "u", 30)
    assert ps["steady_cardio_seconds"] == 900
    assert ps["steady_cardio_distance_m"] == 0
    row = next(x for x in ps["cardio_by_activity"] if x["exercise_id"] == "elliptical")
    assert row["speed_mps"] is None and row["pace_sec_per_km"] is None


def test_scenario_b_hiit_metrics_are_separate(client):
    c, db = client
    training(c, [hiit_exercise()])
    ps = period_summary(db, "u", 30)
    assert ps["training_sessions"] == 1
    assert ps["strength_working_sets"] == 0 and ps["strength_volume_kg"] == 0
    assert ps["steady_cardio_seconds"] == 0
    assert ps["interval_work_seconds"] == 84
    assert ps["interval_rest_seconds"] == 66
    assert ps["interval_elapsed_seconds"] == 150
    assert ps["interval_planned_rounds"] == 4
    assert ps["interval_completed_rounds"] == 3
    assert ps["interval_skipped_rounds"] == 1
    assert ps["interval_ended_early"] == 1
    assert ps["cardio_seconds"] == 0                 # 兼容别名仍是 steady
    assert ps["interval_seconds"] == 150             # 兼容别名=elapsed

    interval = exercise_sessions(db, "u", HIIT)[0]
    assert interval["activity_class"] == CLASS_INTERVAL
    assert interval["working_sets"] == 0
    assert interval["interval_work_seconds"] == 84
    assert interval["interval_rest_seconds"] == 66
    assert interval["interval_elapsed_seconds"] == 150
    assert interval["interval_completed_rounds"] == 3
    assert interval["interval_planned_rounds"] == 4
    assert interval["interval_skipped_rounds"] == 1

    assert fact_value(db, "interval_work_seconds") == 84
    assert fact_value(db, "interval_rest_seconds") == 66
    assert fact_value(db, "interval_elapsed_seconds") == 150
    assert fact_value(db, "steady_cardio_seconds") == 0

    cal = month_calendar(db, "u", YEAR, MONTH)
    day = next(d for d in cal["days"] if d["date"] == TODAY)
    assert day["strength_working_sets"] == 0
    assert day["steady_cardio_seconds"] == 0
    assert day["interval_elapsed_seconds"] == 150
    assert day["interval_work_seconds"] == 84
    assert day["interval_rest_seconds"] == 66


def test_scenario_c_mixed_day_is_consistent_across_interfaces(client):
    c, db = client
    training(c, strength_session() + [steady_cardio(), hiit_exercise()])
    ps = period_summary(db, "u", 30)
    assert ps["training_sessions"] == 1
    assert ps["strength_working_sets"] == 6
    assert ps["strength_volume_kg"] == 3300
    assert ps["steady_cardio_seconds"] == 1200
    assert ps["interval_work_seconds"] == 84
    assert ps["interval_rest_seconds"] == 66
    assert ps["interval_elapsed_seconds"] == 150
    assert ps["classification"]["classes"] == {
        "strength": 6, "steady_cardio": 1, "interval": 1}

    cal = month_calendar(db, "u", YEAR, MONTH)
    day = next(d for d in cal["days"] if d["date"] == TODAY)
    for key in ("training_sessions", "strength_working_sets", "strength_volume_kg",
                "steady_cardio_seconds", "steady_cardio_distance_m",
                "interval_work_seconds", "interval_rest_seconds",
                "interval_elapsed_seconds"):
        assert day[key] == ps[key], key

    assert exercise_sessions(db, "u", BENCH)[0]["working_sets"] == 3
    assert exercise_sessions(db, "u", ROW)[0]["working_sets"] == 3
    assert exercise_sessions(db, "u", RUN)[0]["steady_cardio_seconds"] == 1200
    assert exercise_sessions(db, "u", HIIT)[0]["interval_work_seconds"] == 84

    facts = get_training_facts(db, "u", 30)["facts"]
    session_facts = {f["metric"]: f["value"] for f in facts
                     if f.get("measurement_type") == "session"
                     and f["metric"] in {
                         "training_sessions", "strength_working_sets",
                         "strength_volume_kg", "steady_cardio_seconds",
                         "interval_work_seconds", "interval_rest_seconds",
                         "interval_elapsed_seconds"}}
    assert session_facts == {
        "training_sessions": 1,
        "strength_working_sets": 6,
        "strength_volume_kg": 3300,
        "steady_cardio_seconds": 1200,
        "interval_work_seconds": 84,
        "interval_rest_seconds": 66,
        "interval_elapsed_seconds": 150,
    }
    # 混合会话仍只有 1 次训练；没有因三类记录而重复计会话
    assert fact_value(db, "sessions") == 1


def test_scenario_d_correction_recomputes_and_invalidates_insight(client):
    c, db = client
    cid = training(c, [steady_cardio(), hiit_exercise()])
    task = task_dispatcher.enqueue(db, "u", "training_science",
                                   "post-workout-review", "UserRequested",
                                   {"checkin_id": cid})
    old_insight = task_dispatcher.run_task(db, task).get("insight")
    assert old_insight and old_insight["status"] == "ready"
    old_amount = period_summary(db, "u", 30)["steady_cardio_distance_m"]
    assert old_amount == 5000

    cur = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    new_meta = {**HIIT_META, "completed_rounds": 4,
                "work_seconds_done": 120, "rest_seconds_done": 120,
                "skipped": [], "ended_early": False,
                "end_reason": "全部计划完成"}
    data = {
        **cur["data"],
        "exercises": [
            {**steady_cardio(), "set_logs": [
                {"type": "distance_time", "distance_m": 6000,
                 "duration_seconds": 1200, "rpe": 6}]},
            hiit_exercise(new_meta),
        ],
        "session_meta": {**cur["data"]["session_meta"], "local_date": TODAY},
    }
    resp = c.post(f"/api/users/u/checkins/{cid}/correct", json={
        "expected_revision": cur["revision"], "data": data,
        "reason": "补录实际完成轮次与距离", "evidence": "用户确认 HIIT 完成 4 轮、跑了 6km"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"] == 1
    assert resp.json()["data"]["exercises"][0]["set_logs"][0]["distance_m"] == 6000

    ps = period_summary(db, "u", 30)
    assert ps["steady_cardio_distance_m"] == 6000
    assert ps["interval_completed_rounds"] == 4
    assert ps["interval_skipped_rounds"] == 0
    assert ps["interval_work_seconds"] == 120
    assert ps["interval_rest_seconds"] == 120
    assert ps["interval_elapsed_seconds"] == 240
    assert ps["classification"]["inferred_records"] == 0

    from coach.experts import insight_service
    stale = insight_service.get_insight(db, "u", old_insight["id"])
    assert stale["status"] == "invalidated" and "纠错" in stale["status_reason"]

    new_insight = training_science.analyze_post_workout(db, "u", {"checkin_id": cid})
    assert new_insight["source_revision"]["checkins"][str(cid)] == 1
    assert any("120" in f["text"] for f in new_insight["findings"])
    assert any("6000" in f["text"] for f in new_insight["findings"])


def test_scenario_e_replacement_identity_and_plan_confirmation(client):
    c, db = client
    plan_before = c.get("/api/users/u/plan").json()
    day = next(d for d in plan_before["content"]["schedule"]
               if any(e["exercise_id"] == BENCH for e in d["exercises"]))
    idx = next(i for i, e in enumerate(day["exercises"])
               if e["exercise_id"] == BENCH)
    training(c, [{
        "name": "哑铃卧推", "exercise_id": "dumbbell_bench_press",
        "session_replacement_of": BENCH,
        "session_replacement": {
            "planned_exercise_id": BENCH, "planned_name": "杠铃平板卧推",
            "planned_index": idx, "actual_exercise_id": "dumbbell_bench_press",
            "actual_measurement": "weight_reps", "scope": "session"},
        "set_logs": [{"type": "weight_reps", "weight_kg": 20, "reps": 10}],
    }], mode="planned", day=day["day"],
        plan={"plan_id": plan_before["plan_id"], "plan_version": plan_before["version"]})
    assert c.get("/api/users/u/plan").json()["version"] == plan_before["version"]
    raw = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]["data"]["exercises"][0]
    assert raw["session_replacement"]["planned_name"] == "杠铃平板卧推"
    assert raw["session_replacement"]["scope"] == "session"
    assert raw["session_replacement"]["actual_measurement"] == "weight_reps"

    assert len(exercise_sessions(db, "u", "dumbbell_bench_press")) == 1
    assert exercise_sessions(db, "u", BENCH) == []
    assert period_summary(db, "u", 30)["strength_working_sets"] == 1
    facts = get_training_facts(db, "u", 30)["facts"]
    repl = next(f for f in facts if f["metric"] == "plan-replacement-sessions")
    assert repl["value"] == 1

    staged = c.post("/api/users/u/changes/ai", json={
        "target": "plan",
        "operations": [{"op": "replace_exercise", "day": day["day"],
                        "index": idx, "exercise": "dumbbell_bench_press"}],
        "reason": "长期改为哑铃卧推", "base_version": plan_before["base_version"]})
    assert staged.status_code == 200 and staged.json()["status"] == "pending"
    assert c.get("/api/users/u/plan").json()["version"] == plan_before["version"]
    confirmed = c.post(
        f"/api/users/u/changes/{staged.json()['proposal_id']}/confirm",
        json={"message": "确认长期改为哑铃卧推"})
    assert confirmed.status_code == 200
    assert c.get("/api/users/u/plan").json()["version"] == plan_before["version"] + 1


def test_action_distance_only_counts_steady_cardio(client):
    c, db = client
    hiit = {**HIIT_META, "planned_rounds": 1, "completed_rounds": 1,
            "work_seconds_done": 30, "rest_seconds_done": 30,
            "skipped": [], "ended_early": False, "end_reason": "完成",
            "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                        "work_seconds": 30, "rest_seconds": 30, "rounds": 1}]}
    db.record_checkin("u", "training", {
        "exercises": [{"name": "混合有氧", "exercise_id": "custom_hiit",
                       "set_logs": [
                           {"type": "distance_time", "distance_m": 1000,
                            "duration_seconds": 600},
                           {"type": "duration", "duration_seconds": 60,
                            "distance_m": 500, "hiit": hiit}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}})
    session = exercise_sessions(db, "u", "custom_hiit")[0]
    assert session["activity_class"] == "mixed"
    assert session["steady_cardio_distance_m"] == 1000
    assert session["distance_total_m"] == 1000
    assert session["farthest_set_m"] == 1000
    assert session["interval_elapsed_seconds"] == 60


def test_correction_reclassifies_changed_activity_snapshot(client):
    c, db = client
    cid = training(c, [{"name": "跑步", "exercise_id": RUN, "set_logs": [
        {"type": "distance_time", "distance_m": 3000, "duration_seconds": 900}]}])
    before = exercise_sessions(db, "u", RUN)[0]
    assert before["activity_class"] == CLASS_STEADY_CARDIO
    cur = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    hiit = {**HIIT_META, "planned_rounds": 1, "completed_rounds": 1,
            "work_seconds_done": 30, "rest_seconds_done": 30,
            "skipped": [], "ended_early": False, "end_reason": "完成",
            "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                        "work_seconds": 30, "rest_seconds": 30, "rounds": 1}]}
    resp = c.post(f"/api/users/u/checkins/{cid}/correct", json={
        "expected_revision": 0,
        "data": {**cur["data"], "exercises": [{
            "name": "跑步", "exercise_id": RUN,
            "set_logs": [{"type": "duration", "duration_seconds": 60,
                          "hiit": hiit}],
        }]},
        "reason": "实际做的是间歇跑", "evidence": "用户确认改为间歇记录"})
    assert resp.status_code == 200, resp.text
    log = resp.json()["data"]["exercises"][0]["set_logs"][0]
    assert log["activity_class"] == CLASS_INTERVAL
    assert log["activity_class_source"] == "correction_snapshot"
    after = exercise_sessions(db, "u", RUN)[0]
    assert after["activity_class"] == CLASS_INTERVAL
    assert after["steady_cardio_seconds"] is None
    assert after["interval_work_seconds"] == 30
    ps = period_summary(db, "u", 30)
    assert ps["steady_cardio_seconds"] == 0
    assert ps["interval_work_seconds"] == 30


def test_progress_analysis_uses_classified_metric_not_strength_formula():
    from coach.analytics.progress_analysis import analyze_progress
    interval = analyze_progress([
        {"date": "2026-09-01", "activity_class": "interval",
         "interval_work_seconds": 80},
        {"date": "2026-09-08", "activity_class": "interval",
         "interval_work_seconds": 82},
        {"date": "2026-09-15", "activity_class": "interval",
         "interval_work_seconds": 90},
        {"date": "2026-09-22", "activity_class": "interval",
         "interval_work_seconds": 96},
    ], measurement_type="duration", activity_class=CLASS_INTERVAL)
    assert interval["metric"] == "interval-work-seconds"
    assert interval["activity_class"] == CLASS_INTERVAL
    assert any("不代表有氧能力或力量水平" in x for x in interval["limitations"])

    cardio = analyze_progress([
        {"date": "2026-09-01", "activity_class": "steady_cardio",
         "steady_cardio_distance_m": 5000},
        {"date": "2026-09-08", "activity_class": "steady_cardio",
         "steady_cardio_distance_m": 5200},
        {"date": "2026-09-15", "activity_class": "steady_cardio",
         "steady_cardio_distance_m": 5400},
        {"date": "2026-09-22", "activity_class": "steady_cardio",
         "steady_cardio_distance_m": 5600},
    ], measurement_type="distance_time", activity_class=CLASS_STEADY_CARDIO)
    assert cardio["metric"] == "steady-cardio-distance"
    assert any("无距离记录不生成配速" in x for x in cardio["limitations"])


def test_scenario_f_unrelated_candidates_return_empty(client):
    c, _ = client
    locs = c.get("/api/users/u/locations").json()
    home = next(x for x in locs["locations"] if x["kind"] == "home")
    c.patch(f"/api/users/u/locations/{home['id']}", json={
        "required_equipment": ["band"], "optional_equipment": []})
    c.post(f"/api/users/u/locations/{home['id']}/select")
    result = c.get("/api/users/u/exercise-substitutes", params={
        "exercise_id": BENCH, "location_id": home["id"]}).json()
    assert result["candidates"] == []
    assert result["excluded"]["unrelated"] > 0


def test_snapshot_freezes_new_semantics_and_marks_old_inference(client):
    c, db = client
    doc = {"id": "my_cardio_shift", "name": "语义测试有氧",
           "pattern": "cardio", "primary": ["cardio"],
           "equipment": ["bodyweight"], "location": ["home"],
           "measurement": "duration", "level_min": "beginner",
           "activity": "cardio", "status": "approved", "scope": "user"}
    db.add_custom_exercise("u", "my_cardio_shift", doc)

    # 新记录：保存时快照为 steady_cardio
    training(c, [{"name": "语义测试有氧", "exercise_id": "my_cardio_shift",
                  "set_logs": [{"type": "duration", "duration_seconds": 300}]}])
    first = period_summary(db, "u", 30)
    assert first["steady_cardio_seconds"] == 300
    assert first["classification"]["inferred_records"] == 0
    assert period_summary(db, "u", 30)["classification"]["sources"][
        "saved_snapshot"] == 1

    # 动作库语义改变：新记录快照不变
    changed = {**doc, "activity": "strength"}
    db.conn.execute("UPDATE custom_exercises SET doc=? WHERE user_id=? AND ex_id=?",
                    (__import__("json").dumps(changed, ensure_ascii=False),
                     "u", "my_cardio_shift"))
    db.conn.commit()
    after = period_summary(db, "u", 30)
    assert after["steady_cardio_seconds"] == 300
    assert after["strength_working_sets"] == 0

    # 旧记录（无快照）会按现行动作库推断；来源明确标记，不冒充快照
    old_data = {"exercises": [{
        "name": "语义测试有氧", "exercise_id": "my_cardio_shift",
        "set_logs": [{"type": "duration", "duration_seconds": 120}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}
    db.record_checkin("u", "training", old_data)
    inferred = period_summary(db, "u", 30)
    assert inferred["strength_working_sets"] == 1
    assert inferred["steady_cardio_seconds"] == 300
    assert inferred["classification"]["inferred_records"] == 1
    assert any(source.endswith("_inferred")
               for source in inferred["classification"]["sources"])

    before_change = classify_training_record(
        doc, {"type": "duration", "duration_seconds": 120})
    assert before_change["class"] == CLASS_STEADY_CARDIO
    assert before_change["source"] == "exercise_activity_inferred"
    cls = classify_training_record(changed, old_data["exercises"][0]["set_logs"][0])
    assert cls["class"] == CLASS_STRENGTH
    assert cls["source"] == "legacy_default_inferred"
