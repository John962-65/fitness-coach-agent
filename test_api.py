"""2.0 B4 FastAPI 服务层回归（TASKBOOK_2.0 §五端点表）。

全部离线：TestClient 进程内 ASGI，临时库，FAKE_LLM（conftest 已固定）。
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.plan import generate_plan
from test_repair_regressions import profile


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "api.db")
    with TestClient(app) as c:
        p = profile()
        app.state.db.save_profile("api_user", p)
        app.state.db.create_plan("api_user", generate_plan(p))
        yield c, app


def test_health_and_exercises(client):
    c, _ = client
    body = c.get("/api/health").json()
    assert body["status"] == "ok" and body["exercises"] > 60
    search = c.get("/api/exercises", params={"q": "深蹲"}).json()
    assert search["count"] >= 1
    assert any(e["id"] == "barbell_back_squat" for e in search["exercises"])
    by_id = c.get("/api/exercises", params={"q": "plank"}).json()
    assert [e["id"] for e in by_id["exercises"]] == ["plank"]
    chest = c.get("/api/exercises", params={"muscle": "chest", "status": "approved"}).json()
    assert chest["exercises"] and all(
        "chest" in (e["primary"] + e.get("secondary", [])) for e in chest["exercises"])


def test_profile_404_then_summary(client):
    c, _ = client
    assert c.get("/api/users/ghost/profile").status_code == 404
    body = c.get("/api/users/api_user/profile").json()
    assert body["profile"]["goal"]["primary"] == "muscle_gain"
    assert "muscle_gain" in body["summary"]
    assert body["medical"]["allows_prescription"] is True


def test_today_brief_deterministic(client):
    c, _ = client
    body = c.get("/api/users/api_user/today").json()
    assert body["medical"]["allows_prescription"] is True
    assert body["plan"]["template"]
    assert body["days_since_last_training"] is None
    assert body["sessions_last_7_days"] == 0
    # 打卡后：最近训练日出现
    c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [{"name": "杠铃卧推", "weight_kg": "84.5kg",
                                "sets": "5x5", "reps": 5}]}})
    body = c.get("/api/users/api_user/today").json()
    assert body["last_training_date"] and body["sessions_last_7_days"] == 1


def test_checkin_pipeline_normalizes_and_warns(client):
    c, app = client
    resp = c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [
            {"name": "杠铃卧推", "weight_kg": "84.5kg", "reps": 5},
            {"name": "量子波动蹲", "weight_kg": 60}]}})
    body = resp.json()
    assert resp.status_code == 200
    exs = app.state.db.list_checkins("api_user", 5)[0]["data"]["exercises"]
    assert exs[0]["exercise_id"] == "barbell_bench_press" and exs[0]["weight_kg"] == 84.5
    assert any("未识别动作" in w for w in body["warnings"])
    # 纠错：原话 + 原因 + 版本
    cid = body["id"]
    fixed = c.post(f"/api/users/api_user/checkins/{cid}/correct", json={
        "expected_revision": 0,
        "data": {"exercises": [{"name": "杠铃卧推", "weight_kg": 85, "reps": 5}]},
        "reason": "写错了", "evidence": "刚才那组其实是 85"}).json()
    assert fixed["revision"] == 1
    # M6.1.1：列表携带最近一次修订原因（供历史页展示追溯）
    assert app.state.db.list_checkins("api_user", 5)[0]["last_reason"] == "写错了"
    assert c.post(f"/api/users/api_user/checkins/{cid}/correct", json={
        "expected_revision": 0, "data": {}, "reason": "x", "evidence": "y"}
    ).status_code == 422


def test_approach_lifecycle_via_api(client):
    c, _ = client
    assert c.get("/api/users/api_user/approach").json() == {"initialized": False}
    view = c.post("/api/users/api_user/approach/initialize").json()
    assert view["initialized"] and view["approach"]["structure"]["value"] == "ppl"
    assert view["referenced"]["goal"]["primary"] == "muscle_gain"
    # 再初始化幂等
    assert c.post("/api/users/api_user/approach/initialize").json()["approach"]["revision"] == 1
    revs = c.get("/api/users/api_user/approach/revisions").json()["revisions"]
    assert revs[0]["revision"] == 1 and revs[0]["initiator"] == "system_migration"


def test_manual_change_and_restore_via_api(client):
    c, _ = client
    c.post("/api/users/api_user/approach/initialize")
    result = c.post("/api/users/api_user/changes", json={
        "target": "approach",
        "operations": [{"op": "set_dimension", "dimension": "structure",
                        "value": {"value": "full_body", "note": "时间紧"}}],
        "reason": "想改全身",
        "base_version": {"approach_revision": 1}}).json()
    assert result["status"] == "applied" and result["approach_revision"] == 2
    # 版本漂移 → 422
    resp = c.post("/api/users/api_user/changes", json={
        "target": "approach",
        "operations": [{"op": "set_dimension", "dimension": "structure",
                        "value": {"value": "ppl"}}],
        "reason": "x", "base_version": {"approach_revision": 1}})
    assert resp.status_code == 422 and resp.json()["detail"]["details"]
    # 恢复 v1
    restored = c.post("/api/users/api_user/approach/revisions/1/restore",
                      json={"reason": "还是推拉腿"}).json()
    assert restored["approach"]["revision"] == 3
    assert restored["approach"]["structure"]["value"] == "ppl"


def test_plan_get_and_manual_edit_via_api(client):
    c, _ = client
    plan = c.get("/api/users/api_user/plan").json()
    assert plan["base_version"]["plan_version"] == 1
    day = plan["content"]["schedule"][0]["day"]
    edited = c.post("/api/users/api_user/plan/edits", json={
        "operations": [{"op": "add_exercise", "day": day, "exercise": "plank",
                        "sets": 3, "reps": "45秒", "role": "accessory"}],
        "reason": "加核心",
        "base_version": plan["base_version"]}).json()
    assert edited["plan_version"] == 2 and edited["warnings"] == []
    new_plan = c.get("/api/users/api_user/plan").json()
    assert any(e["exercise_id"] == "plank"
               for e in new_plan["content"]["schedule"][0]["exercises"])
    assert new_plan["content"].get("approach_revision") is None  # 尚未初始化 approach
    # 篡改 base → 422
    resp = c.post("/api/users/api_user/plan/edits", json={
        "operations": [{"op": "rename_day", "day": day, "new_name": "推日"}],
        "base_version": {"plan_id": 999, "plan_version": 1}})
    assert resp.status_code == 422


def test_ai_stage_and_confirm_via_api(client):
    c, _ = client
    c.post("/api/users/api_user/approach/initialize")
    staged = c.post("/api/users/api_user/changes/ai", json={
        "target": "approach",
        "operations": [{"op": "set_dimension", "dimension": "structure",
                        "value": {"value": "full_body"}}],
        "reason": "建议改全身", "base_version": {"approach_revision": 1}}).json()
    assert staged["status"] == "pending"
    pid = staged["proposal_id"]
    unclear = c.post(f"/api/users/api_user/changes/{pid}/confirm",
                     json={"message": "再想想"}).json()
    assert unclear["status"] == "pending"
    ok = c.post(f"/api/users/api_user/changes/{pid}/confirm",
                json={"message": "同意，改成全身"}).json()
    assert ok["status"] == "applied"
    listing = c.get("/api/users/api_user/changes", params={"status": "applied"}).json()
    assert any(p["id"] == pid for p in listing["proposals"])


def test_chat_endpoint_fake_llm(client):
    c, app = client
    body = c.post("/api/users/api_user/chat", json={"message": "今天练什么"}).json()
    assert "reply" in body and body["reply"]
    # 对话历史留痕
    msgs = app.state.db.recent_messages("api_user", 5)
    assert msgs and msgs[-1]["role"] == "assistant"
    # 空消息 400
    assert c.post("/api/users/api_user/chat", json={"message": " "}).status_code == 400


def test_validation_errors_have_details(client):
    c, _ = client
    resp = c.post("/api/users/api_user/changes", json={
        "target": "plan", "operations": [], "reason": "x",
        "base_version": {"plan_id": 1, "plan_version": 1}})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] and isinstance(detail["details"], list)


# ---- B6：前端支撑端点（表单化建档 / 动作状态 / 尝试 / 动作详情 / SPA 托管）----

def _onboard_payload(**over):
    payload = {
        "basic": {"age": 30, "gender": "男", "height_cm": 175, "weight_kg": 75},
        "goal": {"primary": "muscle_gain"},
        "experience": {"training_years": 2},
        "resources": {"location": "gym", "days_per_week": 3, "session_minutes": 60},
        "conditions": {
            "injuries": [], "injuries_evidence": "没有伤病",
            "health_screen": {"heart": "无", "pregnancy": "不适用",
                              "medication": "无", "clearance": "无"},
            "health_screen_evidence": "身体健康，无心血管疾病，未用药，医生未限制运动",
        },
    }
    payload["conditions"].update(over.pop("conditions", {}) or {})
    payload.update(over)
    return payload


def test_onboarding_form_generates_plan_without_llm(client):
    c, app = client
    resp = c.post("/api/users/newbie/onboarding", json=_onboard_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["suspended"] is False and body["level"] == "intermediate"
    record = app.state.db.get_active_plan_record("newbie")
    assert record["content"]["goal_version"] == 0
    saved = app.state.db.get_existing_profile("newbie")
    assert saved["onboarding_done"] and saved["experience"]["level"] == "intermediate"
    assert saved["conditions"]["health_screen_collected"]
    # 重复建档 409
    assert c.post("/api/users/newbie/onboarding",
                  json=_onboard_payload()).status_code == 409


def test_onboarding_requires_full_parq_and_answers(client):
    c, _ = client
    payload = _onboard_payload()
    del payload["conditions"]["health_screen"]["clearance"]
    resp = c.post("/api/users/pq/onboarding", json=payload)
    assert resp.status_code == 422
    assert any("clearance" in d for d in resp.json()["detail"]["details"])
    payload2 = _onboard_payload()
    payload2["conditions"]["injuries_evidence"] = ""
    resp2 = c.post("/api/users/pq2/onboarding", json=payload2)
    assert resp2.status_code == 422
    assert any("injuries_evidence" in d for d in resp2.json()["detail"]["details"])


def test_onboarding_parq_positive_lands_medical_pause(client):
    c, _ = client
    payload = _onboard_payload(conditions={
        "injuries": [], "injuries_evidence": "无伤病",
        "health_screen": {"heart": "冠心病史", "pregnancy": "不适用",
                          "medication": "降压药", "clearance": "医生未明确能否运动"},
        "health_screen_evidence": "有冠心病史，服降压药，医生未明确能否运动"})
    body = c.post("/api/users/cardiac/onboarding", json=payload).json()
    assert body["suspended"] is True and body["medical_status"] == "pending"


def test_exercise_states_serve_last_weights(client):
    c, _ = client
    c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [{"name": "杠铃卧推", "weight_kg": 80, "reps": 5}]}})
    states = c.get("/api/users/api_user/exercise-states").json()["states"]
    bench = next(s for s in states if s["exercise_id"] == "barbell_bench_press")
    assert bench["last_weight"] == 80
    assert c.get("/api/users/ghost/exercise-states").status_code == 404


def test_trials_and_exercise_detail(client):
    c, app = client
    app.state.db.start_personal_trial("api_user", "改上下肢", "想试",
                                      "恢复情况", "疼痛即停", review_days=7)
    trials = c.get("/api/users/api_user/trials").json()["trials"]
    assert trials and trials[0]["change_desc"] == "改上下肢"
    detail = c.get("/api/exercises/barbell_back_squat").json()
    assert detail["name"] == "杠铃深蹲" and detail["joint_stress"]["knee"] == 3
    assert c.get("/api/exercises/nope").status_code == 404
    draft = next(e["id"] for e in c.get("/api/exercises").json()["exercises"]
                 if e["status"] == "draft")
    assert "尚未经审核" in c.get(f"/api/exercises/{draft}").json()["notes"][-1]


def test_spa_fallback_serves_index(tmp_path):
    import pathlib
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa-ok</html>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = create_app(db_path=tmp_path / "spa.db", frontend_dist=dist)
    with TestClient(app) as c:
        assert "spa-ok" in c.get("/today").text          # SPA 路由回退
        assert "spa-ok" in c.get("/").text
        assert c.get("/assets/app.js").text == "console.log(1)"   # 静态资源
        assert c.get("/api/health").json()["status"] == "ok"      # API 优先
        assert c.get("/api/users/ghost/profile").status_code == 404


# ---- M1.1：训练数据完整性 / 离线可靠性 / 前后端一致性（外部审查 P0）----

def test_plan_edits_require_explicit_base_version(client):
    """P0-1：缺 base_version 拒绝（不得自动补最新版绕过乐观锁）。"""
    c, _ = client
    day = c.get("/api/users/api_user/plan").json()["content"]["schedule"][0]["day"]
    ops = [{"op": "rename_day", "day": day, "new_name": "推日"}]
    resp = c.post("/api/users/api_user/plan/edits", json={"operations": ops, "reason": "x"})
    assert resp.status_code == 422
    assert "base_version" in resp.json()["detail"]["error"]


def test_concurrent_edit_stale_submission_rejected(client):
    """P0-1 双页面并发：A 基于 v1 提交前，B 已把计划推进到 v2 → A 被 422 拒绝。"""
    c, _ = client
    plan = c.get("/api/users/api_user/plan").json()
    stale_base = plan["base_version"]
    day = plan["content"]["schedule"][0]["day"]
    # 页面 B：基于最新版完成一次编辑
    ok = c.post("/api/users/api_user/plan/edits", json={
        "operations": [{"op": "edit_set_prescription", "day": day, "index": 0, "sets": 5}],
        "reason": "B 的修改", "base_version": stale_base})
    assert ok.status_code == 200
    # 页面 A：仍基于 v1 的旧版本提交 → 拒绝，数据未变
    resp = c.post("/api/users/api_user/plan/edits", json={
        "operations": [{"op": "edit_set_prescription", "day": day, "index": 0, "sets": 6}],
        "reason": "A 的修改", "base_version": stale_base})
    assert resp.status_code == 422
    current = c.get("/api/users/api_user/plan").json()
    assert current["content"]["schedule"][0]["exercises"][0]["sets"] == 5


def test_checkin_submission_id_is_idempotent(client):
    """P0-2：响应丢失后重试同一 submission_id → 返回同一条，不重复入库。"""
    c, app = client
    payload = {"type": "training", "submission_id": "sub-e2e-001",
               "data": {"exercises": [{"name": "杠铃卧推",
                                       "set_logs": [{"weight_kg": 60, "reps": 10, "rpe": 7}]}]}}
    first = c.post("/api/users/api_user/checkins", json=payload).json()
    again = c.post("/api/users/api_user/checkins", json=payload).json()
    assert first["id"] == again["id"] and again["existing"] is True
    rows = [x for x in app.state.db.list_checkins("api_user", 50)
            if x["type"] == "training"]
    assert len(rows) == 1
    # 不同 ID 正常新增
    other = c.post("/api/users/api_user/checkins", json={**payload, "submission_id": "sub-2"})
    assert other.json()["id"] != first["id"] and "existing" not in other.json()


def test_set_logs_persist_every_set(client):
    """P0-4：每组数据完整保存；聚合字段由服务端从正式组派生（兼容旧引擎）。"""
    c, app = client
    resp = c.post("/api/users/api_user/checkins", json={
        "type": "training", "submission_id": "sub-sets-1",
        "data": {"exercises": [{"name": "杠铃卧推", "set_logs": [
            {"weight_kg": 40, "reps": 10, "warmup": True, "at": "t0"},
            {"weight_kg": 60, "reps": 10, "rpe": 7, "at": "t1"},
            {"weight_kg": 65, "reps": 8, "rpe": 8, "at": "t2"},
            {"weight_kg": 70, "reps": 6, "rpe": 9, "at": "t3"},
        ]}]}})
    assert resp.status_code == 200
    saved = app.state.db.list_checkins("api_user", 5)[0]["data"]["exercises"][0]
    logs = saved["set_logs"]
    assert len(logs) == 4                                  # 每组都在（含热身组）
    assert [l["weight_kg"] for l in logs] == [40, 60, 65, 70]
    assert logs[0]["warmup"] is True and logs[3]["at"] == "t3"
    # 聚合派生：热身不计组数；代表组取容量最大（60×10）
    assert saved["sets"] == 3 and saved["weight_kg"] == 60
    assert saved["reps"] == 10 and saved["rpe"] == 7
    # 派生量能被旧引擎消费（e1RM 输入形状不变）
    states = c.get("/api/users/api_user/exercise-states").json()["states"]
    bench = next(s for s in states if s["exercise_id"] == "barbell_bench_press")
    assert bench["last_weight"] == 60


def test_set_logs_bad_rows_cleaned_with_warning(client):
    c, app = client
    resp = c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [{"name": "杠铃卧推", "set_logs": [
            {"weight_kg": 60, "reps": 10},
            {"weight_kg": -5, "reps": 8},
            {"weight_kg": 70, "reps": "abc"},
            "not-a-dict",
        ]}]}})
    body = resp.json()
    assert body["id"] and len(body["warnings"]) >= 3
    saved = [x for x in app.state.db.list_checkins("api_user", 5)
             if x["id"] == body["id"]][0]["data"]["exercises"][0]
    assert len(saved["set_logs"]) == 1                     # 只剩干净的第一组


@pytest.mark.parametrize("op,keyword", [
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": 0, "reps": 10}, "组数"),
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": 99, "reps": 10}, "组数"),
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": "abc", "reps": 10}, "组数"),
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": 3, "reps": "12-8"}, "区间"),
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": 3, "reps": 101}, "范围"),
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": 3, "reps": 10,
      "weight_kg": -2.5}, "重量"),
    ({"op": "add_exercise", "day": "周一", "exercise": "plank", "sets": 3, "reps": 10,
      "weight_kg": 2000}, "重量"),
])
def test_prescription_validation_rejects_bad_values(client, op, keyword):
    """P1-2：异常组数/次数/重量进不了计划（编辑接口层拦截）。"""
    c, _ = client
    plan = c.get("/api/users/api_user/plan").json()
    base = plan["base_version"]
    resp = c.post("/api/users/api_user/plan/edits",
                  json={"operations": [op], "reason": "x", "base_version": base})
    assert resp.status_code == 422
    assert any(keyword in d for d in resp.json()["detail"]["details"])


def test_prescription_accepts_duration_and_range(client):
    c, _ = client
    plan = c.get("/api/users/api_user/plan").json()
    day = plan["content"]["schedule"][0]["day"]
    ok = c.post("/api/users/api_user/plan/edits", json={
        "operations": [{"op": "add_exercise", "day": day, "exercise": "plank",
                        "sets": 3, "reps": "45秒", "role": "accessory"}],
        "reason": "时长型次数合法", "base_version": plan["base_version"]})
    assert ok.status_code == 200


def test_access_token_required_when_configured(tmp_path):
    """P0-3：配置令牌后，无/错令牌 401，对令牌 200；health 保持开放供探测。"""
    from backend.app import create_app as _create
    app = _create(db_path=tmp_path / "auth.db", access_token="secret-token")
    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/users/x/profile").status_code == 401
        assert c.get("/api/users/x/profile",
                     headers={"X-Access-Token": "wrong"}).status_code == 401
        assert c.post("/api/users/x/checkins",
                      headers={"X-Access-Token": "secret-token"},
                      json={"type": "body", "data": {"weight_kg": 75}}).status_code == 200


def test_access_token_guard_on_non_loopback_host(tmp_path, monkeypatch):
    """P0-3：非回环主机且未设令牌 → __main__ 拒绝启动。"""
    import importlib
    import subprocess
    import sys
    code = ("import os, sys; os.environ['API_HOST']='0.0.0.0'; "
            "sys.path.insert(0, '.'); "
            "from backend.__main__ import main; main()")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            cwd=str(importlib.import_module("pathlib").Path(".").resolve()))
    assert result.returncode != 0
    assert "API_ACCESS_TOKEN" in result.stderr


# ---- M2：咨询留痕 / 计划版本历史与恢复 / 提案操作预览 ----

def test_consultations_endpoint_empty_and_via_chat(client):
    c, app = client
    assert c.get("/api/users/api_user/consultations").json() == {"consultations": []}
    body = c.post("/api/users/api_user/chat", json={"message": "蛋白粉怎么选"}).json()
    assert "已咨询专家" in body["reply"] and "营养" in body["reply"]
    rows = c.get("/api/users/api_user/consultations").json()["consultations"]
    assert rows[0]["specialists"] == ["nutrition"]
    assert rows[0]["advices"][0]["options"]                # 结构化建议可追溯


def test_plan_revisions_list_and_restore(client):
    c, _ = client
    plan = c.get("/api/users/api_user/plan").json()
    day = plan["content"]["schedule"][0]["day"]
    # v2：改名一天
    edited = c.post("/api/users/api_user/plan/edits", json={
        "operations": [{"op": "rename_day", "day": day, "new_name": "推日"}],
        "reason": "改名", "base_version": plan["base_version"]}).json()
    assert edited["plan_version"] == 2
    revs = c.get("/api/users/api_user/plan/revisions").json()["revisions"]
    assert [r["version"] for r in revs] == [2, 1]
    assert revs[0]["action"] == "manual_edit" and revs[1]["active"] is False
    # 恢复 v1 → v3，内容回到原名
    restored = c.post("/api/users/api_user/plan/revisions/1/restore",
                      json={"reason": "还是原名好"}).json()
    assert restored["plan_version"] == 3 and restored["restored_from"] == 1
    current = c.get("/api/users/api_user/plan").json()
    assert current["content"]["schedule"][0]["day"] == day
    # 恢复当前版本 → 422
    assert c.post("/api/users/api_user/plan/revisions/3/restore",
                  json={"reason": ""}).status_code == 422


def test_plan_restore_blocked_when_fenced(client):
    c, app = client
    p = app.state.db.get_existing_profile("api_user")
    p["plan_fence"] = {"reason": "E2E", "safety_flag_ids": []}
    app.state.db.save_profile("api_user", p)
    resp = c.post("/api/users/api_user/plan/revisions/1/restore",
                  json={"reason": ""})
    assert resp.status_code == 422 and "隔离" in resp.json()["detail"]["error"]


def test_pending_proposals_expose_operations_for_preview(client):
    c, _ = client
    c.post("/api/users/api_user/approach/initialize")
    staged = c.post("/api/users/api_user/changes/ai", json={
        "target": "approach",
        "operations": [{"op": "set_dimension", "dimension": "structure",
                        "value": {"value": "full_body"}}],
        "reason": "建议全身", "base_version": {"approach_revision": 1}}).json()
    listing = c.get("/api/users/api_user/changes", params={"status": "pending"}).json()
    prop = next(p for p in listing["proposals"] if p["id"] == staged["proposal_id"])
    assert prop["operations"][0]["dimension"] == "structure"   # 前端预览数据


# ---- M5：个人尝试闭环 + 方式版本内容 ----

def test_trial_start_and_end_flow(client):
    c, app = client
    bad = c.post("/api/users/api_user/trials", json={"change_desc": "x"})
    assert bad.status_code == 422 and "五要素" in bad.json()["detail"]["error"]
    ok = c.post("/api/users/api_user/trials", json={
        "change_desc": "改上下肢分化", "reason": "时间紧",
        "observe": "恢复与执行率", "stop_rule": "膝痛即停",
        "review_days": 14, "baseline": "当前每周 3 练基本完成"})
    assert ok.status_code == 200 and ok.json()["status"] == "active"
    # 单 active:第二个被拒
    second = c.post("/api/users/api_user/trials", json={
        "change_desc": "又改饮食", "reason": "x", "observe": "y", "stop_rule": "z"})
    assert second.status_code == 422
    # 结束复盘:缺 outcome 拒;decision 非法拒;成功落库
    tid = ok.json()["trial_id"]
    assert c.post(f"/api/users/api_user/trials/{tid}/end",
                  json={"decision": "keep"}).status_code == 422
    assert c.post(f"/api/users/api_user/trials/{tid}/end",
                  json={"decision": "maybe", "outcome": "x"}).status_code == 422
    done = c.post(f"/api/users/api_user/trials/{tid}/end",
                  json={"decision": "keep", "outcome": "两周执行 6/8，膝无不适"})
    assert done.status_code == 200
    trials = app.state.db.personal_trials("api_user")
    assert trials[0]["status"] == "ended" and trials[0]["decision"] == "keep"
    assert trials[0]["baseline"].startswith("当前每周")
    # 结束后可再开新尝试
    again = c.post("/api/users/api_user/trials", json={
        "change_desc": "饮食份量法", "reason": "不想算热量",
        "observe": "体重趋势", "stop_rule": "连续两周暴冲"})
    assert again.status_code == 200


def test_approach_revision_content_endpoint(client):
    c, _ = client
    c.post("/api/users/api_user/approach/initialize")
    snap = c.get("/api/users/api_user/approach/revisions/1")
    assert snap.status_code == 200
    body = snap.json()
    assert body["content"]["structure"]["value"]  # 完整快照可取(对比用)
    assert c.get("/api/users/api_user/approach/revisions/99").status_code == 404


def test_exercise_detail_includes_teaching(client):
    """M6.2：动作详情带 teaching（knowledge_refs 人工整理内容；无关联为空表）。"""
    c, _app = client
    body = c.get("/api/exercises/barbell_bench_press").json()
    assert body["teaching"], "已关联动作应返回教学文档"
    assert body["teaching"][0]["topic"] == "卧推技术细节"
    assert "谭成义-胸部教学" in body["teaching"][0]["source"]
    no_ref = c.get("/api/exercises/leg_press").json()
    assert no_ref["teaching"] == []


def test_checkin_preserves_valid_exercise_id(client):
    """M6.3：自由训练/临时替换携带的 exercise_id，合法则保留，非法仍由名称系统判定。"""
    c, app = client
    body = c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [
            {"name": "卧推", "exercise_id": "barbell_bench_press",
             "set_logs": [{"weight_kg": 60, "reps": 10}]},
            {"name": "深蹲", "exercise_id": "not_an_exercise",
             "set_logs": [{"weight_kg": 100, "reps": 5}]},
        ]}}).json()
    assert body["warnings"] == []
    exs = app.state.db.list_checkins("api_user", 5)[0]["data"]["exercises"]
    assert exs[0]["exercise_id"] == "barbell_bench_press"   # 合法 id 保留（别名不改写）
    assert exs[0]["name"] == "卧推"
    assert exs[1]["exercise_id"] == "barbell_back_squat"    # 非法 id → 名称派生
    assert exs[1]["name"] == "杠铃深蹲"


def test_checkins_limit_cap_raised_to_50(client):
    """M6.3：历史列表需要 50 条窗口（422 修复回归）。"""
    c, _app = client
    resp = c.get("/api/users/api_user/checkins", params={"limit": 50})
    assert resp.status_code == 200
    assert c.get("/api/users/api_user/checkins", params={"limit": 51}).status_code == 422


def test_exercise_stats_calendar_period_endpoints(client):
    """M6.3：动作历史 / 日历 / 周期汇总三个只读端点。"""
    c, app = client
    c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [{"name": "卧推", "exercise_id": "barbell_bench_press",
                                "set_logs": [
                                    {"weight_kg": 60, "reps": 10, "at": "2026-10-05T10:00:00"},
                                    {"weight_kg": 65, "reps": 8, "at": "2026-10-05T10:03:00"}]}]}})
    stats = c.get("/api/users/api_user/exercise-stats/barbell_bench_press").json()
    assert stats["sessions"][0]["working_sets"] == 2
    assert stats["sessions"][0]["volume"] == 600 + 520
    assert stats["records"]["heaviest"]["weight_kg"] == 65
    empty = c.get("/api/users/api_user/exercise-stats/leg_press").json()
    assert empty["sessions"] == [] and empty["records"]["heaviest"] is None

    cal = c.get("/api/users/api_user/training-calendar",
                params={"year": stats["sessions"][0]["date"][:4],
                        "month": int(stats["sessions"][0]["date"][5:7])}).json()
    assert any(d["working_sets"] == 2 for d in cal["days"])

    summary = c.get("/api/users/api_user/period-summary", params={"days": 30}).json()
    assert summary["sessions"] >= 1
    assert summary["by_muscle"].get("chest") == 2


def test_checkins_filter_by_date(client):
    """M6.3.1：日历当日详情按日期查询（带非法日期 422）。"""
    c, app = client
    c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [{"name": "卧推", "set_logs": [{"weight_kg": 60, "reps": 10}]}]}})
    day = app.state.db.list_checkins("api_user", 1)[0]["at"][:10]
    hit = c.get("/api/users/api_user/checkins", params={"limit": 50, "date": day}).json()
    assert len(hit["checkins"]) == 1
    miss = c.get("/api/users/api_user/checkins", params={"limit": 50, "date": "1999-01-01"}).json()
    assert miss["checkins"] == []
    assert c.get("/api/users/api_user/checkins",
                 params={"limit": 50, "date": "not-a-date"}).status_code == 422
    # offset 分页
    page2 = c.get("/api/users/api_user/checkins", params={"limit": 1, "offset": 1}).json()
    assert isinstance(page2["checkins"], list)


def test_training_templates_crud(client):
    """M6.4-A 场景 A：模板保存/列表/更新/删除；与计划、会话相互独立。"""
    c, _app = client
    body = c.post("/api/users/api_user/training-templates", json={
        "name": "胸背超级组日",
        "entries": [
            {"exercise_id": "barbell_bench_press", "name": "杠铃平板卧推",
             "measurement": "weight_reps", "superset_group": "A"},
            {"exercise_id": "barbell_row", "name": "杠铃划船",
             "measurement": "weight_reps", "superset_group": "A"},
        ]}).json()
    assert body["name"] == "胸背超级组日"
    tid = body["id"]

    listed = c.get("/api/users/api_user/training-templates").json()["templates"]
    assert [t["name"] for t in listed] == ["胸背超级组日"]
    assert listed[0]["entries"][1]["superset_group"] == "A"

    c.post("/api/users/api_user/training-templates", json={
        "id": tid, "name": "胸背超级组日 v2", "entries": listed[0]["entries"]})
    listed = c.get("/api/users/api_user/training-templates").json()["templates"]
    assert len(listed) == 1 and listed[0]["name"] == "胸背超级组日 v2"

    assert c.post("/api/users/api_user/training-templates",
                  json={"name": "空", "entries": []}).status_code == 422

    assert c.delete(f"/api/users/api_user/training-templates/{tid}").json()["deleted"] == tid
    assert c.get("/api/users/api_user/training-templates").json()["templates"] == []


def test_typed_set_logs_pass_through_and_stay_separate(client):
    """M6.4-A 场景 B 数据层：类型化逐组记录透传落库，聚合派生不混用。"""
    c, app = client
    body = c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [
            {"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
             "set_logs": [
                 {"type": "weight_reps", "weight_kg": 60, "reps": 10,
                  "warmup": False, "at": "2026-10-25T10:00:00"}]},
            {"name": "引体向上", "exercise_id": "pull_up",
             "set_logs": [
                 {"type": "bodyweight_reps", "reps": 8,
                  "added_weight_kg": 5, "at": "2026-10-25T10:05:00"},
                 {"type": "bodyweight_reps", "reps": 6, "at": "2026-10-25T10:08:00"}]},
            {"name": "平板支撑", "exercise_id": "plank",
             "set_logs": [{"type": "duration", "duration_seconds": 90,
                           "at": "2026-10-25T10:12:00"}]},
        ]}}).json()
    assert body["warnings"] == []
    exs = app.state.db.list_checkins("api_user", 5)[0]["data"]["exercises"]
    bench, pull, plank = exs
    assert bench["weight_kg"] == 60 and bench["reps"] == 10
    assert pull["weight_kg"] == 5 and pull["reps"] == 8
    assert pull["set_logs"][1].get("added_weight_kg") is None
    assert plank["weight_kg"] is None and plank["reps"] is None
    assert plank["set_logs"][0]["duration_seconds"] == 90

    stats = c.get("/api/users/api_user/exercise-stats/pull_up").json()
    s = stats["sessions"][0]
    assert s["volume"] == 40
    assert s["reps_total"] == 14
    assert s["best_e1rm"] is None
    assert stats["records"]["max_reps"]["reps"] == 8
    plank_stats = c.get("/api/users/api_user/exercise-stats/plank").json()
    assert plank_stats["sessions"][0]["duration_total_s"] == 90
    assert plank_stats["records"]["longest_set"]["duration_seconds"] == 90


def test_bad_set_type_rejected(client):
    c, _app = client
    body = c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [{"name": "卧推", "set_logs": [
            {"type": "magic", "weight_kg": 60, "reps": 10}]}]}}).json()
    assert any("无法识别" in w for w in body["warnings"])


def test_per_type_required_fields_enforced(client):
    """P1：缺本质量字段的组被剔除并说明（离线恢复/API/导入也走同一清洗）。"""
    c, app = client
    body = c.post("/api/users/api_user/checkins", json={
        "type": "training",
        "data": {"exercises": [
            {"name": "平板支撑", "exercise_id": "plank",
             "set_logs": [{"type": "duration", "at": "2026-10-25T10:00:00"}]},
            {"name": "辅助引体", "exercise_id": "assisted_pull_up",
             "set_logs": [{"type": "assisted_reps", "reps": 8,
                           "at": "2026-10-25T10:05:00"}]},
            {"name": "引体向上", "exercise_id": "pull_up",
             "set_logs": [{"type": "bodyweight_reps", "reps": 6,
                           "at": "2026-10-25T10:08:00"}]},
        ]}}).json()
    assert any("缺少时长" in w for w in body["warnings"])
    assert any("缺少辅助重量" in w for w in body["warnings"])
    exs = app.state.db.list_checkins("api_user", 5)[0]["data"]["exercises"]
    assert exs[0]["set_logs"] == []                    # duration 缺时长 → 剔除
    assert exs[1]["set_logs"] == []                    # assisted 缺辅助重量 → 剔除
    assert len(exs[2]["set_logs"]) == 1                # bodyweight 只缺额外负重（可选）→ 保留
