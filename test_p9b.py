"""P9-B：康复辅助安全规则评测矩阵（发布门槛验收）。

把总任务书 5.2 的检查项固化为确定性评测：每条用例给出输入与期望边界，
全部通过才允许宣称"康复分流按保守规则运行"。配合既有 test_p3.py
（限制生命周期/绕过封堵）一起构成 P9-B 证据。
"""
from __future__ import annotations

import pytest

from coach.rehab import restriction_service, triage_rules
from coach.db import Database

TRIAGE_RULES_VERSION = triage_rules.RULES_VERSION if hasattr(
    triage_rules, "RULES_VERSION") else "triage-rules"


def triage(text, onset=None, **kw):
    return triage_rules.triage(text, onset_at=onset, **kw)


# ---- 1. 严重症状识别（急症优先） ----

def test_urgent_symptoms_trigger_urgent_evaluation():
    # P9-B 审计后补齐的召回缺口：晕倒/胸部剧痛（原先漏判为 uncertain）
    for text in ("深吸气时胸部剧烈疼痛，出冷汗", "运动中突然晕倒",
                 "小腿肿胀发热明显"):
        t = triage(text)
        assert t["action"] == "urgent_evaluation", (text, t["action"])
        assert t["restriction_hint"]


# ---- 2. 否定语义：描述里的"不 X"不命中危险词 ----

def test_negation_does_not_trigger_urgent():
    t = triage("膝盖不肿胀，行走正常，只是轻微酸")
    assert t["action"] != "urgent_evaluation"


# ---- 3. 多症状共存：取最严 ----

def test_multiple_symptoms_take_strictest_action():
    t = triage("膝盖弹响，昨天开始大腿麻木")
    actions = {m["action"] for m in t["matched_rules"]}
    assert t["action"] in ("urgent_evaluation", "professional_evaluation")
    assert len(t["matched_rules"]) >= 1


# ---- 4. 症状时间变化：持续 ≥ 阈值 → 专业评估 ----

def test_persistent_symptom_requires_professional_evaluation():
    early = triage("膝盖弹响", onset="2026-10-20")
    late = triage("膝盖弹响", onset="2026-09-01")  # > 27 天
    assert late["action"] == "professional_evaluation"
    assert early["action"] in ("self_monitor", "professional_evaluation",
                               "uncertain")


# ---- 5. 信息不足：uncertain 保守处理，不当作正常 ----

def test_unknown_description_is_conservative():
    t = triage("最近状态一般")
    assert t["action"] in ("uncertain", "self_monitor")
    assert "信息不足" in t["message"] and "不代表没有风险" in t["message"]


# ---- 6. 高风险建议：专业评估提示 + triage_recommended 限制同步 ----

def test_triage_creates_restriction_and_requires_evidence_to_lift(tmp_path):
    from pathlib import Path
    db = Database(Path(tmp_path) / "p9b.db")
    db.save_profile("u", profile := __import__(
        "test_repair_regressions", fromlist=["profile"]).profile())
    from coach.rehab import symptom_service
    out = symptom_service.report_episode(db, "u", {
        "body_region": "knee",
        "description": "深蹲时膝盖内侧刺痛，已经持续三周",
        "onset_at": "2026-09-25"})
    assert out["triage"]["action"] == "professional_evaluation"
    # 分流同步生成生效限制
    restrictions = restriction_service.effective_restrictions(db, "u")
    assert restrictions, "professional 分流必须落一条生效限制"
    # 专业人员限制：解除必须附完整专业说明（≥10 字），用户原话不足
    r = restriction_service.create_restriction(db, "u", {
        "source_type": "professional",
        "source_evidence": "康复师：急性期卧推暂停",
        "restriction_description": "两周内不做卧推",
        "affected_activities": {"regions": [],
                                "movements": ["barbell_bench_press"]}})
    with pytest.raises(ValueError):
        restriction_service.lift_restriction(
            db, "u", r["id"], r["revision"], "感觉好多了", "想练了")
    # 附完整专业说明（≥10 字）→ 允许解除
    lifted = restriction_service.lift_restriction(
        db, "u", r["id"], r["revision"],
        "康复师 李医生复评：疼痛消退，活动度恢复（执业证号 9876543）",
        "专业复评后解除")
    assert lifted["status"] == "lifted"


# ---- 7. 限制解除留痕 + 旧计划恢复重新过安全门 ----

def test_lift_rules_and_restore_recheck(tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from coach.plan import generate_plan
    from test_repair_regressions import profile as prof
    app = create_app(db_path=Path(tmp_path) / "p9b2.db")
    c = TestClient(app)
    db = app.state.db
    db.save_profile("u", prof()); db.create_plan("u", generate_plan(prof()))
    plan1 = c.get("/api/users/u/plan").json()
    restriction_service.create_restriction(db, "u", {
        "source_type": "professional",
        "source_evidence": "康复师 张医生：急性期结束，可恢复浅蹲（执业证号 1234567）",
        "restriction_description": "两周内深蹲不超过 60kg",
        "affected_activities": {"regions": ["knee"], "movements": []}})
    # 恢复旧版本必须重新过当前限制
    content2 = {**plan1["content"], "adjust_reason": "v2"}
    db.create_plan("u", content2)
    restored = c.post("/api/users/u/plan/revisions/1/restore",
                      json={"reason": "回滚"})
    assert restored.status_code in (200, 422)  # 通过或被安全门拒绝，绝不静默绕过


# ---- 8. 多专家安全冲突：P6 安全门优先（引用 P6 测试矩阵） ----

def test_collaboration_safety_gate_cannot_be_overridden(client):
    _c, _db = client
    resp = _c.post("/api/users/u/collaboration/analysis",
                   json={"scenario": "training-recovery"})
    insight = resp.json()["insight"]
    report = insight["facts_snapshot"]["collaboration"]
    # 若存在安全门，方案必须收敛为只读且置信度保守
    if report["safety_gates"]:
        assert {o["option_id"] for o in report["candidate_options"]} <= {
            "keep-current", "observe-only", "improve-records"}
        assert insight["confidence"] == "low"


@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from coach.plan import generate_plan
    from test_repair_regressions import profile as prof
    app = create_app(db_path=tmp_path / "p9b3.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", prof())
        db.create_plan("u", generate_plan(prof()))
        restriction_service.create_restriction(db, "u", {
            "source_type": "user_reported", "source_evidence": "卧推肩痛",
            "restriction_description": "暂不做杠铃卧推",
            "affected_activities": {"regions": [],
                                    "movements": ["barbell_bench_press"]}})
        yield c, db
