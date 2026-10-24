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
        "reason": "加核心"}).json()
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
