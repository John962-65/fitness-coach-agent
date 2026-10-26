"""P6-A：跨领域事实包、协作任务与专家意见回归。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.collaboration.evidence_bundle import build_evidence_bundle
from coach.experts import insight_service
from coach.plan import generate_plan
from coach.rehab import restriction_service
from test_repair_regressions import profile

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p6a.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.create_plan("u", generate_plan(profile()))
        db.save_profile("v", profile())
        yield c, db


def bench_session(c, uid="u", offset=2, reps=12):
    logs = [{"type": "weight_reps", "weight_kg": 60, "reps": reps, "rpe": 7}] * 4
    return c.post("/api/users/u/checkins" if uid == "u" else
                  f"/api/users/{uid}/checkins", json={
        "type": "training", "data": {
            "exercises": [{"name": "杠铃平板卧推",
                           "exercise_id": "barbell_bench_press",
                           "set_logs": logs}],
            "session_meta": {"mode": "free",
                             "local_date": (date.today()
                                            - timedelta(days=offset)).isoformat()}}})


# ---- 事实包：按授权范围圈定，不越界 ----

def test_bundle_only_contains_requested_domains(client):
    c, db = client
    bench_session(c)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5, "sleep_hours": 5.5}})
    bundle = build_evidence_bundle(db, "u", ["training", "recovery"],
                                   window_days=14)
    assert bundle["kind"] == "cross_domain_evidence_bundle_v1"
    domains = {f["domain"] for f in bundle["facts"]}
    assert domains <= {"training", "recovery"}
    assert "nutrition" not in domains and "body" not in domains
    # 事实条目结构完整（可追溯）
    item = bundle["facts"][0]
    for key in ("fact_id", "domain", "metric", "value", "unit", "time_window",
                "source_ids", "source_revisions", "calculation",
                "data_quality", "limitations"):
        assert key in item
    # 版本指纹可失效判断
    assert "recovery_records_count" in bundle["source_revisions"]
    assert "equipment" in bundle["source_revisions"]
    # 未请求领域直接拒绝
    import pytest as _pytest
    with _pytest.raises(ValueError):
        build_evidence_bundle(db, "u", ["training", "weather"])


# ---- 三个场景：共享事实 → 各自观点 → 分歧保留 ----

def test_training_recovery_scenario_preserves_disagreement(client):
    c, db = client
    bench_session(c)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5, "muscle_soreness": 4,
        "sleep_hours": 5.5}})
    out = c.post("/api/users/u/collaboration/analysis",
                 json={"scenario": "training-recovery"})
    assert out.status_code == 200, out.text
    insight = out.json()["insight"]
    assert insight["insight_type"] == "collaboration-review"
    assert insight["specialist"] == "collaboration"
    report = insight["facts_snapshot"]["collaboration"]
    assert report["kind"] == "collaboration_report_v1"
    assert report["participants"] == ["training_science", "recovery",
                                      "rehabilitation"]
    # 每位专家独立观点（不合并成统一结论）
    assert len(report["specialist_opinions"]) == 3
    # 训练想推进 vs 恢复建议观察 → 分歧被并列保留（不是投票合并）
    kinds = [d["kind"] for d in report["disagreements"]]
    assert "training-vs-recovery" in kinds
    dg = next(d for d in report["disagreements"]
              if d["kind"] == "training-vs-recovery")
    assert {p["specialist"] for p in dg["positions"]} == \
        {"training_science", "recovery"}
    assert dg["missing_information"] and dg["maintain_option"]
    # 候选方案只读；维持现状在列
    assert any(o["option_id"] == "keep-current"
               for o in report["candidate_options"])
    # 任务复用 ExpertTask 基础设施
    tasks = c.get("/api/users/u/experts/tasks?specialist=collaboration").json()
    assert tasks["tasks"] and tasks["tasks"][0]["task_type"] == \
        "collaboration-review"


def test_movement_rehab_and_training_nutrition_scenarios(client):
    c, db = client
    bench_session(c)
    out = c.post("/api/users/u/collaboration/analysis",
                 json={"scenario": "movement-rehab"}).json()["insight"]
    report = out["facts_snapshot"]["collaboration"]
    assert report["participants"] == ["movement", "rehabilitation"]
    assert any("二维" in lim for o in report["specialist_opinions"]
               for lim in o["limitations"])

    out2 = c.post("/api/users/u/collaboration/analysis",
                  json={"scenario": "training-nutrition"}).json()["insight"]
    report2 = out2["facts_snapshot"]["collaboration"]
    assert report2["participants"] == ["training_science", "nutrition",
                                       "rehabilitation"]
    # 无饮食记录 → 数据不足如实呈现（不解释为 0 摄入）
    nutrition = next(o for o in report2["specialist_opinions"]
                     if o["specialist"] == "nutrition")
    assert nutrition["directions"] and \
        nutrition["directions"][0]["direction"] in ("records_incomplete",
                                                    "insufficient_data")
    assert any("记录了 0 天" in line
               for line in nutrition["observations"])
    assert any("未记录餐次不代表未摄入" in line
               for line in nutrition["interpretations"])
    # 未知场景 422
    bad = c.post("/api/users/u/collaboration/analysis",
                 json={"scenario": "no-such"})
    assert bad.status_code == 422


def test_safety_gate_overrides_and_cannot_be_voted_away(client):
    c, db = client
    bench_session(c)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5}})
    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "卧推肩痛",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [],
                                "movements": ["barbell_bench_press"]}})
    insight = c.post("/api/users/u/collaboration/analysis",
                     json={"scenario": "training-recovery"}).json()["insight"]
    report = insight["facts_snapshot"]["collaboration"]
    assert report["safety_gates"], "存在生效限制时必须出现安全门"
    assert insight["confidence"] == "low"
    # 方案收敛到只读观察类，不出现可执行训练调整
    assert {o["option_id"] for o in report["candidate_options"]} <= \
        {"keep-current", "observe-only"}


# ---- 用户决策与版本失效 ----

def test_decisions_and_invalidation_flow(client):
    c, db = client
    bench_session(c)
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5}})
    insight = c.post("/api/users/u/collaboration/analysis",
                     json={"scenario": "training-recovery"}).json()["insight"]
    iid = insight["id"]
    # propose 无提案操作 → 422（只读结果不创建修改）
    r1 = c.post(f"/api/users/u/collaboration/{iid}/decision",
                json={"decision": "propose", "option_id": "keep-current"})
    assert r1.status_code == 422
    # observe 只读；ignore 忽略（历史保留）
    r2 = c.post(f"/api/users/u/collaboration/{iid}/decision",
                json={"decision": "observe"})
    assert r2.status_code == 200 and r2.json()["status"] == "viewed"
    # 恢复数据纠错（同日更新，带原因与依据）→ 旧报告失效
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 3,
        "reason": "更正疲劳评分", "evidence": "用户确认实际为 3"}})
    stale = insight_service.get_insight(db, "u", iid)
    assert stale["status"] == "invalidated"
    assert "恢复记录" in stale["status_reason"]
    # 重新分析可用（regenerate 复用洞察生命周期）
    regen = c.post(f"/api/users/u/expert-insights/{iid}/regenerate", json={})
    assert regen.status_code == 200
    fresh_id = regen.json()["insight"]["id"]
    r3 = c.post(f"/api/users/u/collaboration/{fresh_id}/decision",
                json={"decision": "ignore"})
    assert r3.status_code == 200 and r3.json()["status"] == "dismissed"


def test_collaboration_user_isolation(client):
    c, db = client
    bench_session(c)  # 用户 u 的数据
    insight = c.post("/api/users/u/collaboration/analysis",
                     json={"scenario": "training-recovery"}).json()["insight"]
    # v 查看详情 404；v 自己的联合分析不含 u 的事实
    assert c.get(f"/api/users/v/expert-insights/{insight['id']}").status_code == 404
    own = c.post("/api/users/v/collaboration/analysis",
                 json={"scenario": "training-recovery"}).json()["insight"]
    facts = own["facts_snapshot"]["facts"]
    assert all("60" != str(f.get("value")) or f.get("metric") != "volume"
               for f in facts)
    training = next(o for o in own["facts_snapshot"]["collaboration"]
                    ["specialist_opinions"]
                    if o["specialist"] == "training_science")
    assert any("窗口内没有训练记录" in lim for lim in training["limitations"])
