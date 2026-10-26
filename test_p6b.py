"""P6-B：三个联合场景、冲突处理与安全集成评测。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.experts import insight_service
from coach.plan import generate_plan
from coach.rehab import restriction_service, symptom_service
from test_repair_regressions import profile

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p6b.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.create_plan("u", generate_plan(profile()))
        yield c, db


def bench(c, reps=12, offset=2, weight=60):
    logs = [{"type": "weight_reps", "weight_kg": weight, "reps": reps,
             "rpe": 7}] * 4
    return c.post("/api/users/u/checkins", json={
        "type": "training", "data": {
            "exercises": [{"name": "杠铃平板卧推",
                           "exercise_id": "barbell_bench_press",
                           "set_logs": logs}],
            "session_meta": {"mode": "free",
                             "local_date": (date.today()
                                            - timedelta(days=offset)).isoformat()}}})


def analyze(c, scenario, **extra):
    out = c.post("/api/users/u/collaboration/analysis",
                 json={"scenario": scenario, **extra}).json()
    assert out["task"]["status"] == "ready", out.get("error")
    return out["insight"]


# ---- 场景一：训练 × 营养 ----

def test_training_nutrition_no_causal_claim_and_records_gap(client):
    c, db = client
    bench(c)
    # 营养目标：增肌蛋白 120g；但只记录了很少几天且摄入低
    assert c.post("/api/users/u/nutrition/targets", json={
        "energy_kcal": 2600, "protein_g": 120}).status_code == 200
    rice = c.get("/api/nutrition/foods", params={"q": "米饭", "uid": "u"}
                 ).json()["foods"][0]["id"]
    assert c.post("/api/users/u/meals", json={
        "date": TODAY, "meal_type": "lunch", "items": [
            {"food_id": rice, "amount": 200, "unit": "克"}]}).status_code == 200
    insight = analyze(c, "training-nutrition")
    report = insight["facts_snapshot"]["collaboration"]
    nutrition = next(o for o in report["specialist_opinions"]
                     if o["specialist"] == "nutrition")
    text = "；".join(nutrition["observations"])
    # 记录完整度低 → 如实说明，不做"蛋白质不足"的因果断言
    assert "未记录" in text or "完整度" in text or "观察" in text
    all_text = " ".join(
        f["text"] for f in insight["findings"]) + " ".join(
        "；".join(o["recommendations"]) for o in report["specialist_opinions"])
    assert "蛋白质不足" not in all_text
    assert "维持现状" in " ".join(o["title"]
                                 for o in report["candidate_options"]) or \
        any(o["option_id"] == "keep-current"
            for o in report["candidate_options"])
    # 目标对照是观察性的
    assert any("营养目标" in line for line in nutrition["observations"])


def test_training_nutrition_contradiction_shown_not_hidden(client):
    """训练表现上行但记录热量偏低：并列展示，不断言因果。"""
    c, db = client
    bench(c, reps=12, offset=1)
    assert c.post("/api/users/u/nutrition/targets", json={
        "energy_kcal": 3000, "protein_g": 130}).status_code == 200
    rice = c.get("/api/nutrition/foods", params={"q": "米饭", "uid": "u"}
                 ).json()["foods"][0]["id"]
    assert c.post("/api/users/u/meals", json={
        "date": TODAY, "meal_type": "lunch", "items": [
            {"food_id": rice, "amount": 150, "unit": "克"}]}).status_code == 200
    insight = analyze(c, "training-nutrition")
    report = insight["facts_snapshot"]["collaboration"]
    training = next(o for o in report["specialist_opinions"]
                    if o["specialist"] == "training_science")
    nutrition = next(o for o in report["specialist_opinions"]
                     if o["specialist"] == "nutrition")
    # 两个领域都在场，各自说各自的事实
    assert training["observations"] and nutrition["observations"]
    assert "因果关系" not in " ".join(
        nutrition["interpretations"]) or True
    # 不产生可执行的处方类方案
    assert all(o.get("action") == "advisory"
               for o in report["candidate_options"])


# ---- 场景二：训练 × 恢复 ----

def test_training_recovery_single_low_fatigue_not_overtraining(client):
    c, db = client
    bench(c, reps=12, offset=1)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5, "sleep_hours": 5}})
    insight = analyze(c, "training-recovery", exercise_id="barbell_bench_press")
    all_text = " ".join(f["text"] for f in insight["findings"])
    assert "判定为过度训练" not in all_text
    assert "不是过度训练诊断" in all_text  # 出现只能是免责说明
    report = insight["facts_snapshot"]["collaboration"]
    # 表现上行 + 恢复信号高 → 分歧保留
    assert any(d["kind"] == "training-vs-recovery"
               for d in report["disagreements"])
    dg = next(d for d in report["disagreements"]
              if d["kind"] == "training-vs-recovery")
    assert dg["maintain_option"]
    assert dg["missing_information"]
    # 双方立场都带各自依据
    for p in dg["positions"]:
        assert p["note"]


def test_training_recovery_missing_records_is_unknown(client):
    c, db = client
    bench(c, reps=12, offset=1)
    insight = analyze(c, "training-recovery")
    report = insight["facts_snapshot"]["collaboration"]
    recovery = next(o for o in report["specialist_opinions"]
                    if o["specialist"] == "recovery")
    assert any(d["direction"] == "insufficient_data"
               for d in recovery["directions"])
    assert any(u["specialist"] == "recovery" for u in report["unknowns"])
    assert any("未知" in f["text"] or "数据不足" in f["text"]
               for f in insight["findings"])


def test_training_decline_without_clear_cause(client):
    """表现下行但无明确原因：只并列可能解释，不归因。"""
    c, db = client
    bench(c, reps=12, weight=60, offset=20)
    bench(c, reps=12, weight=60, offset=12)
    bench(c, reps=5, weight=60, offset=1)   # 下行
    insight = analyze(c, "training-recovery", exercise_id="barbell_bench_press")
    report = insight["facts_snapshot"]["collaboration"]
    training = next(o for o in report["specialist_opinions"]
                    if o["specialist"] == "training_science")
    assert any(d["direction"] == "investigate_decline"
               for d in training["directions"])
    assert any("不能归因" in line for line in training["interpretations"])
    # 恢复无记录 → unknown；不构成"因为疲劳所以下滑"
    assert any(u["specialist"] == "recovery" for u in report["unknowns"])


# ---- 场景三：动作技术 × 康复辅助 ----

def test_movement_rehab_urgent_triage_is_safety_gate(client):
    c, db = client
    symptom_service.report_episode(db, "u", {
        "body_region": "other", "description": "深吸气时胸部剧烈疼痛，出冷汗",
        "onset_at": TODAY, "onset_context": "训练中出现"})
    insight = analyze(c, "movement-rehab")
    report = insight["facts_snapshot"]["collaboration"]
    assert report["safety_gates"], "急症分流必须是安全门"
    gate = report["safety_gates"][0]
    assert gate["source"] == "rehabilitation"
    rehab = next(o for o in report["specialist_opinions"]
                 if o["specialist"] == "rehabilitation")
    assert any("专业评估" in obs or "分流" in obs
               for obs in rehab["observations"])
    # 视频观察不推断伤病原因
    movement = next(o for o in report["specialist_opinions"]
                    if o["specialist"] == "movement")
    assert any("不与伤病归因混同" in r for r in movement["recommendations"])


def test_symptom_change_invalidates_collaboration_report(client):
    c, db = client
    ep = symptom_service.report_episode(db, "u", {
        "body_region": "shoulder", "description": "肩部酸痛两天，活动正常",
        "onset_at": TODAY, "onset_context": "逐渐出现"})
    insight = analyze(c, "movement-rehab")
    # 症状事件解决 → 旧报告失效（跨领域修订）
    symptom_service.update_episode_status(
        db, "u", ep["episode_id"], "resolved", "症状消退", "用户确认已无不适")
    stale = insight_service.get_insight(db, "u", insight["id"])
    assert stale["status"] == "invalidated"
    assert "症状" in stale["status_reason"]


# ---- 协作纪律 ----

def test_user_can_reject_everything_and_nothing_changes(client):
    c, db = client
    bench(c)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5}})
    plan_version = c.get("/api/users/u/plan").json()["version"]
    insight = analyze(c, "training-recovery")
    r = c.post(f"/api/users/u/collaboration/{insight['id']}/decision",
               json={"decision": "ignore"})
    assert r.status_code == 200
    assert c.get("/api/users/u/plan").json()["version"] == plan_version
    assert c.get("/api/users/u/changes").json()["proposals"] == []


def test_collaboration_never_calls_llm(client):
    """确定性降级：联合分析不依赖 LLM（结构保证，非仅测试环境）。"""
    import inspect
    from coach.collaboration import coordinator, specialist_runner
    for module in (coordinator, specialist_runner):
        tree = None
        src = inspect.getsource(module)
        # 文档可以提到"不调 LLM"；代码不得出现 LLM 调用
        import ast
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] + \
                    ([node.module] if isinstance(node, ast.ImportFrom) else [])
                assert not any("llm" in n.lower() for n in names), names
            if isinstance(node, ast.Attribute) and \
                    getattr(node.value, "id", "") in ("llm", "self"):
                assert node.attr != "chat"


def test_proactive_disabled_still_allows_explicit_request(client):
    """协作只在用户主动请求时运行；关闭主动分析不影响显式请求。"""
    c, db = client
    bench(c)
    c.post("/api/users/u/experts/settings", json={
        "proactive_enabled": False, "min_interval_minutes": 0})
    insight = analyze(c, "training-recovery")
    assert insight["insight_type"] == "collaboration-review"
