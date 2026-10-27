"""P5-C2：训练进阶服务集成——只读 API、next-training-review 洞察、生命周期。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.experts import insight_service, task_dispatcher
from coach.plan import generate_plan
from coach.rehab import restriction_service
from coach.training_progression import get_next_training_options
from coach.training_progression.progression_service import (
    PROGRESSION_RULES_VERSION,
)
from test_p5c1 import bench_logs, bench_plan_context, d, option_ids, save_sets
from test_repair_regressions import profile


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5c2.db")
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


def get_progression(c, pctx, exercise_id="barbell_bench_press", uid="u"):
    params = {k: pctx[k] for k in ("plan_id", "plan_version", "planned_day",
                                   "index", "planned_exercise_id")
              if k in pctx and pctx[k] is not None}
    return c.get(f"/api/users/{uid}/training-progression/{exercise_id}",
                 params=params)


def request_next_review(c, pctx, exercise_id="barbell_bench_press", uid="u"):
    return c.post(f"/api/users/{uid}/experts/analysis", json={
        "specialist": "training_science",
        "task_type": "next-training-review",
        "params": {"exercise_id": exercise_id, **pctx}})


# ---- 只读 API：契约、只读性、隔离 ----

def test_progression_api_returns_contract_and_is_read_only(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    plan_version = c.get("/api/users/u/plan").json()["version"]
    proposals_before = len(c.get("/api/users/u/changes").json()["proposals"])
    resp = get_progression(c, pctx)
    assert resp.status_code == 200, resp.text
    result = resp.json()
    for key in ("rules_version", "context", "options",
                "recommendations_allowed", "blocked_reasons",
                "source_revisions"):
        assert key in result
    assert result["rules_version"] == PROGRESSION_RULES_VERSION
    ctx = result["context"]
    # 保留事实引用与数据质量字段
    assert ctx["fact_refs"]
    assert ctx["data_quality"]["comparable_session_count"] == 1
    assert ctx["plan_prescription_applies"] is True
    assert ctx["planned_index"] == pctx["index"]
    assert "keep-current" in option_ids(result)
    # 只查看建议：不创建提案、不创建 next-training-review 洞察、计划版本不变
    # （保存打卡时的 post-workout-review 是既有事件链路，与本接口无关）
    assert result["insight"] is None
    assert c.get("/api/users/u/plan").json()["version"] == plan_version
    assert len(c.get("/api/users/u/changes").json()["proposals"]) == \
        proposals_before
    assert not [i for i in db.list_expert_insights("u")
                if i["insight_type"] == "next-training-review"]


def test_progression_api_user_isolation(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press", bench_logs(8, weight=60, sets=4),
              offset=2)
    # 其他用户：读到的只有自己的数据（这里为空），绝不是 u 的记录
    db.save_profile("v", profile())
    resp = get_progression(c, pctx, uid="v")
    assert resp.status_code == 200
    ctx = resp.json()["context"]
    assert ctx["recent_sessions"] == []
    assert ctx["data_quality"]["comparable_session_count"] == 0
    assert ctx["last_actual_performance"] is None
    # v 没有生效计划 → 不会套用任何计划处方
    assert ctx["plan_prescription_applies"] is False
    assert ctx["current_prescription"] == {}
    # 不存在的用户 404
    assert c.get("/api/users/ghost/training-progression/"
                 "barbell_bench_press").status_code == 404
    # 不在用户动作库的动作 404
    assert get_progression(c, pctx,
                           exercise_id="not_an_exercise").status_code == 404


def test_progression_api_stale_plan_context_flags_without_prescription(client):
    c, db = client
    pctx, _entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press", bench_logs(8, weight=60, sets=4),
              offset=2)
    stale = {**pctx, "plan_version": pctx["plan_version"] + 5}
    resp = get_progression(c, stale)
    assert resp.status_code == 200
    result = resp.json()
    assert result["context"]["plan_prescription_applies"] is False
    assert result["context"]["current_prescription"] == {}
    assert any("计划上下文" in r for r in result["blocked_reasons"])
    assert "consider-increase-load" not in option_ids(result)


def test_progression_api_rehab_restriction_blocks_candidates(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=2)
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推时肩部疼痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [],
                                "movements": ["barbell_bench_press"]},
    })
    result = get_progression(c, pctx).json()
    assert result["recommendations_allowed"] is False
    assert result["options"] == []
    assert any("限制" in r or "安全" in r for r in result["blocked_reasons"])
    # 直接调用修改 API 尝试违规加重 → 服务端拒绝（统一校验，不因面板存在而放开）
    plan = c.get("/api/users/u/plan").json()
    denied = c.post("/api/users/u/changes/ai", json={
        "target": "plan",
        "operations": [{"op": "edit_set_prescription",
                        "day": pctx["planned_day"], "index": pctx["index"],
                        "weight_kg": 65}],
        "reason": "绕过限制加重", "base_version": plan["base_version"]})
    assert denied.status_code == 422


# ---- next-training-review 洞察 ----

def test_next_review_mirrors_engine_and_never_invents_targets(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=2)
    engine = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    resp = request_next_review(c, pctx)
    assert resp.status_code == 200, resp.text
    insight = resp.json()["insight"]
    assert insight["insight_type"] == "next-training-review"
    assert insight["specialist"] == "training_science"
    assert insight["status"] == "ready"
    # AI 解释不得引入规则引擎没有批准的可执行目标：
    # 方案集合与候选引擎一致；proposed_targets 逐字相同
    engine_opts = {o["option_id"]: o for o in engine["options"]}
    assert [o["option_id"] for o in insight["options"]] == list(engine_opts)
    for opt in insight["options"]:
        assert opt["proposed_targets"] == engine_opts[opt["option_id"]][
            "proposed_targets"]
        assert opt["action"] == ("proposal"
                                 if engine_opts[opt["option_id"]].get("plan_proposal")
                                 else "advisory")
        hint = opt.get("proposal_hint")
        if hint:
            assert hint["operations"] == \
                engine_opts[opt["option_id"]]["plan_proposal"]["operations"]
        else:
            assert "proposal_hint" not in opt
    # 每条发现引用真实事实（fact_ids ⊆ 快照）且无孤儿引用
    snap_ids = {f["fact_id"] for f in insight["facts_snapshot"]["facts"]}
    for finding in insight["findings"]:
        assert all(fid in snap_ids for fid in finding["fact_ids"])
    # 加重候选的数值只能来自候选引擎（这里 62.5 = 60 + 已验证档位 2.5）
    load = next(o for o in insight["options"]
                if o["option_id"] == "consider-increase-load")
    assert load["proposed_targets"].get("weight_kg") == \
        engine_opts["consider-increase-load"]["proposed_targets"]["weight_kg"]
    # 版本引用齐全
    rev = insight["source_revision"]
    assert rev["rules_version"] == PROGRESSION_RULES_VERSION
    assert rev["plan_version"] == pctx["plan_version"]
    assert rev["restrictions"]
    assert rev["equipment"]
    # GET 接口现在带出洞察状态
    assert get_progression(c, pctx).json()["insight"]["id"] == insight["id"]


def test_next_review_requires_exercise_id(client):
    c, _db = client
    resp = c.post("/api/users/u/experts/analysis", json={
        "specialist": "training_science",
        "task_type": "next-training-review", "params": {}})
    assert resp.status_code == 422
    assert "exercise_id" in resp.json()["detail"]["error"]


def test_next_review_lifecycle_and_data_correction_invalidation(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    cid = save_sets(c, "barbell_bench_press",
                    bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    resp = request_next_review(c, pctx)
    insight = resp.json()["insight"]
    insight_id = insight["id"]

    # 查看 / 忽略 / 重新分析生命周期
    viewed = c.post(f"/api/users/u/expert-insights/{insight_id}/view", json={})
    assert viewed.json()["status"] == "viewed"
    dismissed = c.post(f"/api/users/u/expert-insights/{insight_id}/dismiss",
                       json={})
    assert dismissed.json()["status"] == "dismissed"
    regen = c.post(f"/api/users/u/expert-insights/{insight_id}/regenerate",
                   json={})
    assert regen.status_code == 200
    fresh = c.get(f"/api/users/u/expert-insights/{insight_id}").json()
    assert fresh["status"] == "dismissed"  # 旧洞察保留为历史，状态不变
    all_now = insight_service.list_insights(db, "u",
                                            specialist="training_science")
    newest = [i for i in all_now if i["insight_type"] == "next-training-review"
              and i["id"] != insight_id]
    assert newest and newest[0]["status"] == "ready"  # 重新分析生成新洞察
    regen_id = newest[0]["id"]

    # 用户纠错历史训练 → 有效洞察失效（修订号漂移，懒失效在读取时判定）
    cur = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    assert cur["id"] == cid
    data = {**cur["data"],
            "exercises": [{**cur["data"]["exercises"][0],
                           "set_logs": bench_logs(10, weight=60,
                                                  sets=int(entry["sets"]))}],
            "session_meta": cur["data"]["session_meta"]}
    fixed = c.post(f"/api/users/u/checkins/{cid}/correct", json={
        "expected_revision": cur["revision"], "data": data,
        "reason": "次数记错", "evidence": "用户更正为每组 10 次"})
    assert fixed.status_code == 200, fixed.text
    latest = insight_service.list_insights(db, "u",
                                           specialist="training_science")
    regen_after = next(i for i in latest if i["id"] == regen_id)
    assert regen_after["status"] == "invalidated"
    assert "纠错" in regen_after["status_reason"]
    # 纠错后候选数据源版本同步变化（不沿用旧修订号）
    engine = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert engine["context"]["source_revisions"]["checkins"][str(cid)] >= 1
    assert engine["context"]["data_quality"]["comparable_session_count"] == 1


def test_next_review_invalidated_by_plan_change_and_restriction(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=2)
    insight = request_next_review(c, pctx).json()["insight"]
    rev = insight["source_revision"]
    assert rev["plan_version"] == pctx["plan_version"]

    # 计划被其他操作更新 → 旧候选不能继续作为有效提案依据
    plan = c.get("/api/users/u/plan").json()
    content = plan["content"]
    day = next(x for x in content["schedule"] if x["day"] == pctx["planned_day"])
    day["exercises"][pctx["index"]]["weight_kg"] = 62.5
    db.create_plan("u", content)
    stale = insight_service.get_insight(db, "u", insight["id"])
    assert stale["status"] == "invalidated"
    assert "计划已更新" in stale["status_reason"]
    # 旧洞察的提案操作基于旧计划 → 服务端拒绝过期 base_version
    proposal_hint = next(o for o in insight["options"]
                         if o.get("proposal_hint"))["proposal_hint"]
    denied = c.post("/api/users/u/changes/ai", json={
        "target": "plan", "operations": proposal_hint["operations"],
        "reason": "基于旧候选", "base_version": plan["base_version"]})
    assert denied.status_code == 422

    # 训练限制变化 → 限制版本漂移同样使洞察失效
    insight2 = request_next_review(
        c, {**pctx, "plan_version": pctx["plan_version"] + 1}).json()["insight"]
    assert insight2["status"] == "ready"
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推时肩部疼痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [],
                                "movements": ["barbell_bench_press"]},
    })
    stale2 = insight_service.get_insight(db, "u", insight2["id"])
    assert stale2["status"] == "invalidated"
    assert "限制" in stale2["status_reason"]


def test_next_review_invalidated_by_equipment_change(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    insight = request_next_review(c, pctx).json()["insight"]
    assert insight["status"] == "ready"
    # 切换当前地点（器械配置指纹变化）→ 候选可执行性必须重查
    places = c.get("/api/users/u/locations").json()
    home = next(x for x in places["locations"] if x["kind"] == "home")
    c.post(f"/api/users/u/locations/{home['id']}/select", json={})
    stale = insight_service.get_insight(db, "u", insight["id"])
    assert stale["status"] == "invalidated"
    assert "器械" in stale["status_reason"] or "地点" in stale["status_reason"]
    # 读取进阶接口：地点不可执行时如实阻断
    result = get_progression(c, pctx).json()
    assert result["recommendations_allowed"] is False
    assert any("地点" in r or "器械" in r for r in result["blocked_reasons"])


def test_next_review_recovery_is_shown_as_fact_not_diagnosis(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(8, weight=60, sets=int(entry["sets"])), offset=2)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": date.today().isoformat(), "sleep_hours": 5,
        "fatigue": 5, "muscle_soreness": 4}})
    insight = request_next_review(c, pctx).json()["insight"]
    snap_ids = {f["fact_id"] for f in insight["facts_snapshot"]["facts"]}
    recovery_findings = [f for f in insight["findings"]
                         if f["kind"] == "recovery-context"]
    assert recovery_findings, "恢复事实应独立呈现"
    text = "".join(f["text"] for f in recovery_findings)
    assert "不是确定因果关系" in text and "过度训练" not in text
    assert all(fid in snap_ids for f in recovery_findings
               for fid in f["fact_ids"])
    # 有恢复信号 → 引擎给出恢复观察方向（而非自动判定)
    engine = get_next_training_options(db, "u", "barbell_bench_press", pctx)
    assert "observe-recovery" in option_ids(engine)


def test_next_review_interval_uses_interval_metrics(client):
    c, db = client
    meta = {"name": "四轮", "exercise_id": "custom_hiit",
            "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
                        "work_seconds": 30, "rest_seconds": 20, "rounds": 4}],
            "planned_rounds": 4, "completed_rounds": 3,
            "work_seconds_done": 90, "rest_seconds_done": 50,
            "skipped": [{"block": 0, "round": 4}], "ended_early": True,
            "end_reason": "时间不够"}
    save_sets(c, "custom_hiit", [
        {"type": "duration", "duration_seconds": 140, "hiit": meta}], offset=1)
    insight = request_next_review(c, {"exercise_id": "custom_hiit"}).json()[
        "insight"]
    recent = next(f for f in insight["findings"]
                  if f["finding_id"] == "f-next-recent")
    assert "HIIT" in recent["text"] and "完成 3/4 轮" in recent["text"]
    assert "e1RM" not in recent["text"]
    engine_opt_ids = [o["option_id"] for o in insight["options"]]
    assert "complete-interval-plan" in engine_opt_ids
    assert all("weight_kg" not in (o.get("proposed_targets") or {})
               for o in insight["options"])


# ---- 长期修改：统一 ChangeProposal 协议 ----

def test_long_term_adoption_goes_through_proposal_confirmation(client):
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=2)
    result = get_progression(c, pctx).json()
    plan_version = c.get("/api/users/u/plan").json()["version"]
    load = next(o for o in result["options"]
                if o["option_id"] == "consider-increase-load")
    assert load["plan_proposal"], "加重候选应带长期提案操作"
    ops = load["plan_proposal"]["operations"]
    assert ops[0]["weight_kg"] == load["proposed_targets"]["weight_kg"]

    # 创建 pending 提案：计划版本保持不变
    staged = c.post("/api/users/u/changes/ai", json={
        "target": "plan", "operations": ops,
        "reason": "采用训练建议：加重一档",
        "base_version": result["context"]["source_revisions"]["plan"]})
    assert staged.status_code == 200, staged.text
    proposal_id = staged.json()["proposal_id"]
    assert staged.json()["status"] == "pending"
    assert c.get("/api/users/u/plan").json()["version"] == plan_version

    # 用户明确确认 → 校验通过后提交新版本
    confirmed = c.post(f"/api/users/u/changes/{proposal_id}/confirm", json={
        "message": "确认采用加重建议"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "applied"
    new_plan = c.get("/api/users/u/plan").json()
    assert new_plan["version"] == plan_version + 1
    day = next(x for x in new_plan["content"]["schedule"]
               if x["day"] == pctx["planned_day"])
    assert day["exercises"][pctx["index"]]["weight_kg"] == \
        load["proposed_targets"]["weight_kg"]

    # 旧候选（旧版本）再提交 → 服务端拒绝过期计划版本
    stale = c.post("/api/users/u/changes/ai", json={
        "target": "plan", "operations": ops, "reason": "重放旧候选",
        "base_version": result["context"]["source_revisions"]["plan"]})
    assert stale.status_code == 422


def test_proposal_rejected_when_plan_changes_before_confirmation(client):
    """确认前计划被其他操作更新 → 旧提案拒绝生效（关键要求）。"""
    c, db = client
    pctx, entry = bench_plan_context(c)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=4)
    save_sets(c, "barbell_bench_press",
              bench_logs(12, weight=60, sets=int(entry["sets"])), offset=2)
    result = get_progression(c, pctx).json()
    load = next(o for o in result["options"]
                if o["option_id"] == "consider-increase-load")
    staged = c.post("/api/users/u/changes/ai", json={
        "target": "plan", "operations": load["plan_proposal"]["operations"],
        "reason": "候选提案", "base_version": result["context"][
            "source_revisions"]["plan"]})
    proposal_id = staged.json()["proposal_id"]
    # 确认前计划被其他操作更新
    plan = c.get("/api/users/u/plan").json()
    content = plan["content"]
    day = next(x for x in content["schedule"] if x["day"] == pctx["planned_day"])
    day["exercises"][pctx["index"]]["note"] = "确认前被改动"
    db.create_plan("u", content)
    confirmed = c.post(f"/api/users/u/changes/{proposal_id}/confirm", json={
        "message": f"确认采用提案 {proposal_id}"})
    assert confirmed.status_code == 422
    assert c.get("/api/users/u/plan").json()["version"] == plan["version"] + 1
