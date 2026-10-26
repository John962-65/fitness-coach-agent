"""P5-C3：训练进阶闭环与个人尝试回归。

覆盖（总任务书 1.2/1.3/1.4）：
- 审计：服务端根据有效候选构造长期提案（不信任前端数值）、重复确认幂等、
  洞察失效（恢复数据变化）；
- PersonalTrial：候选→尝试（关联字段/基线快照/单活跃约束）、真实记录观察、
  复盘草稿（已观察/可能解释/无法确认）、用户决策（keep/adjust/stop/observe）
  且任何决策都不自动修改计划；
- 完整数据回归：普通组/递减组/单侧/超级组/有氧/HIIT/替换/纠错/自由与计划
  训练下，训练事实、洞察与个人尝试口径一致。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.experts import insight_service
from coach.plan import generate_plan
from coach.training_progression import trial_service
from test_p5c1 import bench_logs, bench_plan_context, d, option_ids, save_sets
from test_repair_regressions import profile

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5c3.db")
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


def bench_ctx(c):
    pctx, entry = bench_plan_context(c)
    return pctx, entry


def ready_bench(c, entry):
    """两次达标训练 → 出现加重候选（计划卧推目标 5-8 次）。"""
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"]), rpe=7), offset=6)
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"]), rpe=7), offset=3)


# ---- 审计：服务端构造长期提案 ----

def test_adopt_builds_proposal_server_side_and_confirms_once(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    ready_bench(c, entry)
    plan_version = c.get("/api/users/u/plan").json()["version"]

    # 前端只提交 option_id——操作由服务端按当前有效候选构造
    resp = c.post("/api/users/u/training-progression/barbell_bench_press/adopt",
                  json={"option_id": "consider-increase-load", **pctx})
    assert resp.status_code == 200, resp.text
    proposal_id = resp.json()["proposal_id"]
    assert resp.json()["status"] == "pending"
    # pending 期间计划版本不变
    assert c.get("/api/users/u/plan").json()["version"] == plan_version
    staged = db.get_proposal("u", proposal_id)
    assert staged["operations"][0]["op"] == "edit_set_prescription"
    assert staged["operations"][0]["index"] == pctx["index"]

    # 重复确认：第一次生效后再次确认被拒绝（幂等边界）
    ok = c.post(f"/api/users/u/changes/{proposal_id}/confirm",
                json={"message": "确认采用该长期修改"})
    assert ok.status_code == 200 and ok.json()["status"] == "applied"
    assert c.get("/api/users/u/plan").json()["version"] == plan_version + 1
    again = c.post(f"/api/users/u/changes/{proposal_id}/confirm",
                   json={"message": "再确认一次"})
    assert again.status_code == 422

    # 过期候选（旧计划版本的相同操作）不能提交
    stale = c.post("/api/users/u/training-progression/barbell_bench_press/adopt",
                   json={"option_id": "consider-increase-load",
                         **{**pctx, "plan_version": plan_version}})
    # adopt 会以当前计划重新计算候选——这里显式用旧 base_version 提交验证服务端拒绝
    old_ops = staged["operations"]
    replay = c.post("/api/users/u/changes/ai", json={
        "target": "plan", "operations": old_ops, "reason": "重放旧候选",
        "base_version": {"plan_id": pctx["plan_id"], "plan_version": plan_version}})
    assert replay.status_code == 422


def test_adopt_rejects_unknown_option_and_blocked_candidate(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    resp = c.post("/api/users/u/training-progression/barbell_bench_press/adopt",
                  json={"option_id": "consider-increase-load", **pctx})
    assert resp.status_code == 422  # 没有可比训练，候选不存在
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    resp2 = c.post("/api/users/u/training-progression/barbell_bench_press/adopt",
                   json={"option_id": "no-such-option", **pctx})
    assert resp2.status_code == 422


# ---- PersonalTrial：候选 → 尝试 → 观察 → 复盘 → 决策 ----

def test_trial_from_candidate_records_linkage_and_baseline(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    ready_bench(c, entry)
    resp = c.post("/api/users/u/training-progression/barbell_bench_press/trial",
                  json={"option_id": "consider-increase-load", **pctx,
                        "min_sessions": 2})
    assert resp.status_code == 200, resp.text
    out = resp.json()
    trial = out["trial"]
    # 关联字段完整
    assert trial["exercise_id"] == "barbell_bench_press"
    assert trial["plan_id"] == pctx["plan_id"]
    assert trial["plan_version"] == pctx["plan_version"]
    assert trial["origin"]["kind"] == "next_training_candidate"
    assert trial["origin"]["origin_option_id"] == "consider-increase-load"
    assert trial["origin"]["rules_version"]
    assert trial["chosen_target"]["weight_kg"] == 62.5
    assert trial["observation_metric"] == "target-completion"
    assert trial["min_sessions"] == 2
    # 基线快照：尝试前的真实表现与来源版本
    baseline = trial["baseline"]
    assert baseline["kind"] == "p5c_trial_baseline_v1"
    assert baseline["last_actual_performance"]["working_sets"] == int(entry["sets"])
    assert trial["baseline_source_revisions"]["plan"]["plan_id"] == pctx["plan_id"]
    assert trial["baseline_source_revisions"]["rules_version"]
    # 单活跃约束
    dup = c.post("/api/users/u/training-progression/barbell_bench_press/trial",
                 json={"option_id": "consider-increase-load", **pctx})
    assert dup.status_code == 422 and "进行中" in dup.json()["detail"]["error"]


def test_trial_observation_and_review_use_real_records(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    ready_bench(c, entry)
    trial_id = c.post(
        "/api/users/u/training-progression/barbell_bench_press/trial",
        json={"option_id": "consider-increase-load", **pctx, "min_sessions": 2}
    ).json()["trial"]["id"]
    # 观察期开始时还没有新记录
    detail = c.get(f"/api/users/u/trials/{trial_id}").json()
    assert detail["observation"]["sessions_total"] == 0
    assert detail["observation"]["due_for_review"] is False
    # 尝试期间真实训练：一次达标（8 次上沿）、一次未达标（5 次下沿之下）
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=62.5, sets=int(entry["sets"]), rpe=7),
              offset=0)
    save_sets(c, "barbell_bench_press",
              bench_logs(4, weight=62.5, sets=int(entry["sets"]), rpe=8),
              offset=0)
    detail = c.get(f"/api/users/u/trials/{trial_id}").json()
    obs = detail["observation"]
    assert obs["sessions_total"] == 2
    assert obs["sessions_met"] == 1
    assert obs["sessions_unmet"] == 1
    assert obs["sessions_due"] is True  # min_sessions=2 已到
    assert obs["due_for_review"] is True
    # 复盘草稿：已观察 / 无法确认，不宣称因果
    review = c.get(f"/api/users/u/trials/{trial_id}?review=1").json()["review"]
    assert any("尝试期间：2 次训练" in line for line in
               review["sections"]["observed"])
    assert any("混杂" in line or "不推广" in line
               for line in review["sections"]["unconfirmed"])
    assert {o["decision"] for o in review["decision_options"]} == \
        {"keep", "adjust", "stop", "observe"}


def test_trial_decisions_never_modify_plan_and_observe_extends(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    ready_bench(c, entry)
    trial_id = c.post(
        "/api/users/u/training-progression/barbell_bench_press/trial",
        json={"option_id": "consider-increase-load", **pctx}).json()["trial"]["id"]
    version = c.get("/api/users/u/plan").json()["version"]
    # 暂不判断，继续观察 → 保持 active，review_at 延长
    obs = c.post(f"/api/users/u/trials/{trial_id}/decision",
                 json={"decision": "observe"})
    assert obs.status_code == 200
    assert obs.json()["status"] == "active"
    assert obs.json()["trial"]["review_at"] > \
        (date.today() + timedelta(days=13)).isoformat()
    assert c.get("/api/users/u/plan").json()["version"] == version
    # 复盘后保留 → 结束，但计划同样不被自动修改
    done = c.post(f"/api/users/u/trials/{trial_id}/decision",
                  json={"decision": "keep", "note": "状态稳定，保留"})
    assert done.status_code == 200
    assert done.json()["status"] == "ended"
    assert done.json()["trial"]["decision"] == "keep"
    assert "不自动修改计划" in done.json()["note"]
    assert c.get("/api/users/u/plan").json()["version"] == version
    # 已结束的尝试不能再次决策
    again = c.post(f"/api/users/u/trials/{trial_id}/decision",
                   json={"decision": "stop"})
    assert again.status_code == 422


def test_trial_requires_applicable_candidate_with_targets(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    # 恢复观察候选没有目标字段，不构成尝试对象
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5, "sleep_hours": 5}})
    resp = c.post("/api/users/u/training-progression/barbell_bench_press/trial",
                  json={"option_id": "observe-recovery", **pctx})
    assert resp.status_code == 422
    # 安全阻断时不能创建尝试
    from coach.rehab import restriction_service
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推肩痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [],
                                "movements": ["barbell_bench_press"]}})
    resp2 = c.post("/api/users/u/training-progression/barbell_bench_press/trial",
                   json={"option_id": "keep-current", **pctx})
    assert resp2.status_code == 422


def test_next_review_invalidated_by_recovery_change(client):
    """审计：恢复数据变化后旧洞察失效（P5-C3 补充回归）。"""
    c, db = client
    pctx, entry = bench_ctx(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    insight = c.post("/api/users/u/experts/analysis", json={
        "specialist": "training_science",
        "task_type": "next-training-review",
        "params": {"exercise_id": "barbell_bench_press", **pctx}}).json()["insight"]
    assert insight["status"] == "ready"
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5, "muscle_soreness": 4}})
    stale = insight_service.get_insight(db, "u", insight["id"])
    assert stale["status"] == "invalidated"
    assert "恢复记录" in stale["status_reason"]


# ---- 完整数据回归：各训练形态下事实/洞察/尝试口径一致 ----

def test_full_forms_regression_facts_trials_consistency(client):
    c, db = client
    pctx, entry = bench_ctx(c)
    sets_n = int(entry["sets"])

    # 1 普通力量组（达标）→ 2 递减组 → 3 单侧 → 4 超级组
    save_sets(c, "barbell_bench_press", bench_logs(8, weight=60, sets=sets_n),
              offset=6)
    save_sets(c, "barbell_bench_press", bench_logs(8, weight=60, sets=sets_n),
              offset=4)
    drop = [{"method": "drop_set", "segments": [
        {"weight_kg": 60, "reps": 8}, {"weight_kg": 50, "reps": 6}]}] * 2
    save_sets(c, "barbell_bench_press", drop, offset=2)
    uni = [{"method": "unilateral", "segments": [
        {"side": "left", "weight_kg": 30, "reps": 8},
        {"side": "right", "weight_kg": 30, "reps": 8}]}] * 2
    save_sets(c, "barbell_bench_press", uni, offset=1)
    superset = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [
            {"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
             "superset_group": "A", "set_logs": bench_logs(8, weight=60,
                                                           sets=sets_n)},
            {"name": "哑铃卧推", "exercise_id": "dumbbell_bench_press",
             "superset_group": "A",
             "set_logs": bench_logs(10, weight=20, sets=3)},
        ],
        "session_meta": {"mode": "planned", "local_date": d(0),
                         "day": pctx["planned_day"],
                         "plan_id": pctx["plan_id"],
                         "plan_version": pctx["plan_version"]}}})
    assert superset.status_code == 200

    # 8 动作替代：分析对象是实际替换动作，且长期 scope 不开放
    replace = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{
            "name": "哑铃卧推", "exercise_id": "dumbbell_bench_press",
            "session_replacement_of": "barbell_bench_press",
            "session_replacement": {
                "planned_exercise_id": "barbell_bench_press",
                "planned_name": "杠铃平板卧推", "planned_index": pctx["index"],
                "actual_exercise_id": "dumbbell_bench_press",
                "actual_measurement": "weight_reps", "scope": "session"},
            "set_logs": bench_logs(10, weight=22, sets=3),
        }],
        "session_meta": {"mode": "planned", "local_date": d(0),
                         "day": pctx["planned_day"],
                         "plan_id": pctx["plan_id"],
                         "plan_version": pctx["plan_version"]}}})
    assert replace.status_code == 200
    prog = c.get("/api/users/u/training-progression/dumbbell_bench_press",
                 params={k: pctx[k] for k in
                         ("plan_id", "plan_version", "planned_day", "index")}
                 ).json()
    assert prog["context"]["data_quality"]["temporary_replacement"] is True
    assert all("plan" not in o["action_scope"] for o in prog["options"])

    # 6 有氧：用含跑步处方的计划让"维持"候选带可观察目标（时长）
    run_cid = save_sets(c, "running", [
        {"type": "distance_time", "distance_m": 5000,
         "duration_seconds": 1500}], offset=2)
    db.create_plan("u", {
        "template": "p5c3-cardio", "level": "beginner", "days_per_week": 1,
        "goal_version": 1, "schedule": [{
            "day": "有氧日", "focus": "有氧", "exercises": [{
                "exercise_id": "running", "name": "跑步",
                "sets": 1, "reps": "25分钟"}]}], "notes": []})
    plan2 = c.get("/api/users/u/plan").json()
    ctx_run = {"plan_id": plan2["plan_id"], "plan_version": plan2["version"],
               "planned_day": "有氧日", "index": 0,
               "planned_exercise_id": "running"}
    trial_cardio = c.post("/api/users/u/training-progression/running/trial",
                          json={"option_id": "keep-current", **ctx_run,
                                "min_sessions": 1})
    assert trial_cardio.status_code == 200, trial_cardio.text
    cardio_trial = trial_cardio.json()["trial"]
    assert cardio_trial["observation_metric"] == "steady-cardio-seconds"
    del plan2
    # 尝试期间的一次真实有氧（达标 25 分钟）
    run_cid2 = save_sets(c, "running", [
        {"type": "distance_time", "distance_m": 5000,
         "duration_seconds": 1500}], offset=0)

    hiit_meta = {"name": "四轮", "exercise_id": "custom_hiit",
                 "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                             "work_seconds": 30, "rest_seconds": 20,
                             "rounds": 4}],
                 "planned_rounds": 4, "completed_rounds": 3,
                 "work_seconds_done": 90, "rest_seconds_done": 50,
                 "skipped": [{"block": 0, "round": 4}], "ended_early": True,
                 "end_reason": "时间不够"}
    save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 140, "hiit": hiit_meta}],
        offset=0)
    prog_hiit = c.get(
        "/api/users/u/training-progression/custom_hiit").json()
    assert prog_hiit["context"]["activity_class"] == "interval"
    assert "complete-interval-plan" in option_ids(prog_hiit)

    # 12 历史纠错：修订号上升 → 尝试观察与事实同步反映新数据
    detail = c.get(f"/api/users/u/trials/{cardio_trial['id']}").json()
    assert detail["observation"]["sessions_total"] >= 1
    assert detail["observation"]["sessions_met"] >= 1
    target = next(x for x in c.get("/api/users/u/checkins?limit=50").json()[
        "checkins"] if x["id"] == run_cid2)
    new_data = {**target["data"], "exercises": [
        {**target["data"]["exercises"][0], "set_logs": [
            {"type": "distance_time", "distance_m": 6000,
             "duration_seconds": 1500}]}]}
    fixed = c.post(f"/api/users/u/checkins/{target['id']}/correct", json={
        "expected_revision": target["revision"], "data": new_data,
        "reason": "距离记错", "evidence": "用户确认实际 6km"})
    assert fixed.status_code == 200
    detail2 = c.get(f"/api/users/u/trials/{cardio_trial['id']}").json()
    obs2 = detail2["observation"]
    # 观察读取的是纠错后的修订（revision>=1）
    assert all(s["revision"] >= 1 for s in obs2["sessions"]
               if s["checkin_id"] == run_cid2)
    # 10 有计划训练：计划完成事实可用（洞察/复盘引用）
    insight = c.post("/api/users/u/experts/analysis", json={
        "specialist": "training_science", "task_type": "post-workout-review",
        "params": {"checkin_id": json.loads(
            c.get("/api/users/u/checkins?limit=1").text)["checkins"][0]["id"]}})
    assert insight.status_code == 200
    # 11 离线（断网保存）由前端离线队列回归覆盖；此处验证自由训练（9）
    free = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "俯卧撑", "exercise_id": "push_up",
                       "set_logs": [{"type": "bodyweight_reps", "reps": 15}] * 3}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert free.status_code == 200
    prog_free = c.get("/api/users/u/training-progression/push_up").json()
    assert prog_free["context"]["measurement_type"] == "bodyweight_reps"
    assert "consider-increase-load" not in option_ids(prog_free)
