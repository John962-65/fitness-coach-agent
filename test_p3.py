"""P3 回归：症状记录 / 安全分流 / 训练限制 / 专业安排 / 跨专家协作。

覆盖任务书五场景与 §八 安全测试：
A 一般不适记录（历史保留、观察不覆盖、来源与修订）
B 危险症状 → urgent 提示优先，训练建议不能覆盖
C 训练限制服务端强制（手动编辑也被拦截；AI 不能解除专业人员限制）
D 康复×动作技术协作边界（数据隔离断言）
E 长期记录与复核（多次观察→洞察失效→专业安排跟踪）
"""
import json
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.changes import ProposalRejected, submit_manual
from coach.db import Database
from coach.experts import insight_service, task_dispatcher
from coach.plan import generate_plan
from coach.rehab import restriction_service, symptom_service, triage_rules
from test_repair_regressions import profile

TODAY = date.today().isoformat()
D = lambda n: (date.today() - timedelta(days=n)).isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p3.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.save_profile("other", profile())
        db.create_plan("u", generate_plan(profile()))
        db.create_plan("other", generate_plan(profile()))
        yield c, db


def plan_base(db, uid="u"):
    rec = db.get_active_plan_record(uid)
    return {"plan_id": rec["id"], "plan_version": rec["version"]}


# ---- P3-2 分流规则资产 ----

def test_triage_rules_asset_and_versions():
    assert triage_rules.RULES_VERSION == "rehab-rules-1"
    assert triage_rules.REVIEW_STATUS  # 审核状态必须显式标注
    for rule in triage_rules.RULES:
        assert rule["rule_id"] and rule["action"] in (
            "urgent_evaluation", "professional_evaluation")
        assert rule["terms"] and rule["message"] and "restriction_hint" in rule
    # 确定性：同输入同输出
    t1 = triage_rules.triage("膝盖肿起来了", severity=6, onset_at=D(3))
    t2 = triage_rules.triage("膝盖肿起来了", severity=6, onset_at=D(3))
    assert t1 == t2 and t1["action"] == "urgent_evaluation"
    # severity 不单独定级：高分级无红旗 → uncertain
    assert triage_rules.triage("膝盖有点不舒服", severity=9, onset_at=D(1))["action"] \
        == "uncertain"
    # 信息不足 → uncertain（不把未知当无风险）
    assert triage_rules.triage("")["action"] == "uncertain"
    assert "不代表" in triage_rules.triage("")["message"] \
        or "未报告危险症状" in triage_rules.triage("")["message"]


def test_triage_classification_matrix():
    cases = [
        ("跑步时胸闷头晕", "urgent_evaluation"),
        ("脚崴了站不起来", "urgent_evaluation"),
        ("膝盖越来越肿发烫", "urgent_evaluation"),
        ("夜里痛醒", "professional_evaluation"),
        ("手臂发麻窜到手指", "professional_evaluation"),
        ("膝盖有时卡住打软腿", "professional_evaluation"),
        ("腰不舒服,走路受影响", "professional_evaluation"),  # 日常功能受限
    ]
    for text, expected in cases:
        result = triage_rules.triage(text, severity=5, onset_at=D(1))
        assert result["action"] == expected, f"{text!r} → {result['action']}"
    # mild 路径：低分级 + 无红旗 + 短病程
    assert triage_rules.triage("练后肌肉有点酸,活动正常", severity=3,
                               onset_at=D(1))["action"] == "general_information"


# ---- 场景 A：一般不适记录 ----

def test_scenario_a_general_symptom_history(client):
    c, db = client
    resp = c.post("/api/users/u/symptom-episodes", json={"data": {
        "body_region": "knee", "side": "right", "onset_at": D(2),
        "onset_context": "上周加深蹲量后出现",
        "description": "深蹲后膝盖外侧有点酸,走路正常",
        "severity": 3, "functional_limitations": []}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["triage"]["action"] == "general_information"
    ep_id = body["episode_id"]
    # 无自动诊断:分流消息不包含具体疾病名
    assert "诊断" in body["triage"]["disclaimer"]
    # 追加观察：历史保留（不覆盖）
    obs = c.post(f"/api/users/u/symptom-episodes/{ep_id}/observations", json={
        "data": {"severity": 4, "symptom_description": "下楼时明显一点",
                 "functional_limitations": ["下楼"], "user_notes": "昨天练完"}})
    assert obs.status_code == 200
    detail = c.get(f"/api/users/u/symptom-episodes/{ep_id}").json()
    assert len(detail["observations"]) == 2
    assert detail["observations"][0]["severity"] == 3
    assert detail["observations"][1]["severity"] == 4  # 不被覆盖
    # 校验：非法区域/空描述/越界 severity
    assert c.post("/api/users/u/symptom-episodes", json={
        "data": {"body_region": "head", "onset_at": TODAY,
                 "description": "x"}}).status_code == 422
    assert c.post("/api/users/u/symptom-episodes", json={
        "data": {"body_region": "knee", "onset_at": TODAY,
                 "description": ""}}).status_code == 422
    assert c.post(f"/api/users/u/symptom-episodes/{ep_id}/observations", json={
        "data": {"severity": 11}}).status_code == 422


# ---- 场景 B：需要进一步评估的症状 ----

def test_scenario_b_urgent_triage_priority(client):
    c, db = client
    resp = c.post("/api/users/u/symptom-episodes", json={"data": {
        "body_region": "knee", "side": "left", "onset_at": D(1),
        "description": "膝盖越来越肿,还有点发烫,走路困难",
        "severity": 8, "functional_limitations": ["走路"]}})
    body = resp.json()
    assert body["triage"]["action"] == "urgent_evaluation"
    assert "就医" in body["triage"]["message"] or "专业评估" in body["triage"]["message"]
    # 自动创建 triage_recommended 限制（收紧）
    assert body["restriction_id"]
    r = db.get_restriction("u", body["restriction_id"])
    assert r["source_type"] == "triage_recommended" and r["status"] == "active"
    # 观察缓解 → 限制不自动解除，仅设复核
    c.post(f"/api/users/u/symptom-episodes/{body['episode_id']}/observations", json={
        "data": {"severity": 2, "symptom_description": "消肿了,走路正常"}})
    still = db.get_restriction("u", body["restriction_id"])
    assert still["status"] == "active" and still["review_at"]


# ---- 场景 C：训练限制生效 ----

def test_scenario_c_restriction_blocks_plan_change(client):
    c, db = client
    # 用户自行报告限制：膝
    c.post("/api/users/u/training-restrictions", json={
        "source_type": "user_reported",
        "source_evidence": "我左膝最近不舒服,先不练腿部",
        "affected_activities": {"regions": ["knee"]},
        "restriction_description": "左膝不适期间不做下肢大负荷动作"})
    day = db.get_active_plan("u")["schedule"][0]["day"]
    # 手动编辑也被服务端拦截
    with pytest.raises(ProposalRejected) as exc:
        submit_manual(db, "u", "plan",
                      [{"op": "add_exercise", "day": day, "exercise": "杠铃深蹲",
                        "sets": 3, "reps": 5}], "想加深蹲", plan_base(db))
    assert "训练限制冲突" in str(exc.value.errors[0])
    # 不受限制的动作可以加入（用户保留训练安排决策权）
    ok = submit_manual(db, "u", "plan",
                       [{"op": "add_exercise", "day": day, "exercise": "哑铃卧推",
                         "sets": 3, "reps": 10}], "上肢不受限", plan_base(db))
    assert ok["status"] == "applied"
    # 限制通过确认协议生效后 base_version 已变，重新取
    # AI 不能解除专业人员限制
    prof = c.post("/api/users/u/training-restrictions", json={
        "source_type": "professional",
        "source_evidence": "李医生:两周内禁止跑跳",
        "affected_activities": {"regions": ["ankle"], "movements": []},
        "restriction_description": "两周内禁止跑跳类活动"}).json()
    short = c.post(f"/api/users/u/training-restrictions/{prof['id']}/lift", json={
        "expected_revision": 0, "lift_evidence": "感觉好了", "reason": "想练"})
    assert short.status_code == 422 and "专业人员" in short.json()["detail"]["error"]
    lifted = c.post(f"/api/users/u/training-restrictions/{prof['id']}/lift", json={
        "expected_revision": 0,
        "lift_evidence": "复诊时李医生确认两周期满,踝关节恢复良好,可以逐步恢复跑跳",
        "reason": "复诊结论"})
    assert lifted.status_code == 200 and lifted.json()["status"] == "lifted"
    # 修订历史保留
    assert db.conn.execute(
        "SELECT COUNT(*) FROM training_restriction_revisions WHERE restriction_id=?",
        (prof["id"],)).fetchone()[0] == 1


def test_restriction_cannot_be_bypassed_via_ai_stage(client):
    """AI 提案路径同样被限制校验拦截（stage_ai 走同一套 validate_change）。"""
    c, db = client
    c.post("/api/users/u/training-restrictions", json={
        "source_type": "professional",
        "source_evidence": "物理治疗师王:腰部急性期避免负重屈曲",
        "affected_activities": {"regions": ["lower_back"]},
        "restriction_description": "腰部急性期避免负重屈曲动作"})
    day = db.get_active_plan("u")["schedule"][0]["day"]
    from coach.changes import stage_ai
    with pytest.raises(ProposalRejected):
        stage_ai(db, "u", "plan",
                 [{"op": "add_exercise", "day": day, "exercise": "硬拉",
                   "sets": 3, "reps": 5}],
                 "AI 建议加硬拉", plan_base(db))


# ---- 场景 D：康复×动作技术协作边界 ----

def test_scenario_d_rehab_movement_data_isolation(client):
    """康复模块与（未来 P4 的）动作技术数据互不越界：症状/限制记录
    不引用视频分析，动作分析结果不生成诊断。"""
    c, db = client
    resp = c.post("/api/users/u/symptom-episodes", json={"data": {
        "body_region": "knee", "onset_at": D(1),
        "description": "深蹲时膝盖内侧不适",
        "severity": 4, "functional_limitations": []}})
    ep_id = resp.json()["episode_id"]
    # 康复洞察 finding 不做伤病诊断（不含损伤术语断言）
    task = task_dispatcher.enqueue(db, "u", "rehabilitation", "symptom-review",
                                   "UserRequested", {"episode_id": ep_id})
    ins = task_dispatcher.run_task(db, task)["insight"]
    text_all = " ".join(f["text"] for f in ins["findings"]) + ins["summary"]
    for dx in ("半月板", "韧带撕裂", "关节炎", "滑囊炎", "肌腱炎"):
        assert dx not in text_all
    assert "不构成医学诊断" in " ".join(ins["limitations"])
    # 用户隔离
    assert c.get("/api/users/other/symptom-episodes").json()["episodes"] == []
    assert c.get(f"/api/users/other/symptom-episodes/{ep_id}").status_code == 404
    assert c.get("/api/users/other/training-restrictions").json()["restrictions"] == []


# ---- 场景 E：长期记录与复核 ----

def test_scenario_e_history_and_care_plan(client):
    c, db = client
    ep = c.post("/api/users/u/symptom-episodes", json={"data": {
        "body_region": "lower_back", "onset_at": D(20),
        "description": "腰有点紧,提重物时明显", "severity": 4,
        "functional_limitations": ["提东西"]}}).json()
    ins1 = task_dispatcher.run_task(db, task_dispatcher.enqueue(
        db, "u", "rehabilitation", "symptom-review", "UserRequested",
        {"episode_id": ep["episode_id"]}))["insight"]
    # 多次更新
    for sev, note in ((5, "弯腰多了"), (3, "好一些了")):
        c.post(f"/api/users/u/symptom-episodes/{ep['episode_id']}/observations", json={
            "data": {"severity": sev, "user_notes": note}})
    # 旧洞察失效
    stale = insight_service.get_insight(db, "u", ins1["id"])
    assert stale["status"] == "invalidated" and "症状记录" in stale["status_reason"]
    detail = c.get(f"/api/users/u/symptom-episodes/{ep['episode_id']}").json()
    assert len(detail["observations"]) == 3  # 完整历史
    # 专业安排录入与执行跟踪
    plan = c.post("/api/users/u/care-plans", json={
        "title": "腰部活动度练习", "professional_source": "物理治疗师王(2026-10-20 面诊)",
        "related_episode_id": ep["episode_id"],
        "activities": [{"name": "猫牛式", "frequency": "每天 2 组 x10"},
                       {"name": "死虫式", "frequency": "隔天 3 组 x8"}]}).json()
    assert plan["plan_id"]
    plans = c.get("/api/users/u/care-plans").json()["plans"]
    assert plans[0]["professional_source"] and len(plans[0]["activities"]) == 2
    log = c.post(f"/api/users/u/care-activities/{plans[0]['activities'][0]['id']}/log",
                 json={"local_date": TODAY, "completed": True,
                       "feedback": "做完腰部轻松一点"})
    assert log.status_code == 200
    again = c.post(f"/api/users/u/care-activities/{plans[0]['activities'][0]['id']}/log",
                   json={"local_date": TODAY, "completed": True})
    assert again.status_code == 422  # 同活动同天幂等
    # 专业安排必填来源
    assert c.post("/api/users/u/care-plans", json={
        "title": "无来源安排"}).status_code == 422


# ---- 分流与任务解耦 / 事件不重复 ----

def test_triage_independent_of_background_tasks(client, monkeypatch):
    """安全分流同步完成；专家任务失败不影响记录与分流结果。"""
    c, db = client
    import coach.experts.task_dispatcher as td

    def boom(*a, **k):
        raise RuntimeError("dispatch down")
    monkeypatch.setattr(td, "on_event", boom)
    resp = c.post("/api/users/u/symptom-episodes", json={"data": {
        "body_region": "ankle", "onset_at": D(1),
        "description": "崴脚后肿了", "severity": 6}})
    assert resp.status_code == 200
    assert resp.json()["triage"]["action"] == "urgent_evaluation"  # 分流即时可用
    assert db.list_symptom_episodes("u")  # 记录已保存
    monkeypatch.undo()


def test_repeated_symptom_events_dedup(client):
    """同一事件多次更新只触发必要的重分析（版本锚去重）。"""
    c, db = client
    resp = c.post("/api/users/u/symptom-episodes", json={"data": {
        "body_region": "hip", "onset_at": D(3), "description": "髋部紧",
        "severity": 3}})
    ep_id = resp.json()["episode_id"]
    task_dispatcher.run_pending(db, "u")
    n1 = len([t for t in db.list_expert_tasks("u", specialist="rehabilitation")
              if t["status"] == "ready"])
    # 无新数据时重放同一事件 refs → dedup 不新增
    task_dispatcher.on_event(db, "u", "SymptomReported", {
        "episode_id": ep_id, "symptoms_version": db.symptoms_version("u")})
    n2 = len(db.list_expert_tasks("u", specialist="rehabilitation"))
    assert n2 == n1
