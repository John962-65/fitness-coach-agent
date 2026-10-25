"""M6.5 端到端验收场景（A 个人训练分析 / B 训练方式调整 / C 长期个人尝试）
+ 三接口 HTTP 级一致性（M6.5-0 验收）。

全部离线（FAKE_LLM）：场景 A 验证对话回复中的数值可追溯到种子记录；
场景 B 验证多方案咨询→用户自主决策→提案确认链路（含用户拒绝路径）；
场景 C 验证个人尝试的基线→执行→复盘→决策链路。
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.app import create_app
from fastapi.testclient import TestClient

from coach.agent import CoachAgent
from coach.analytics import fact_service, trial_evidence
from tests.coach_eval import seed as S
from tests.coach_eval.cases import ago
from tests.coach_eval.test_eval import untraceable_numbers

UID = "m65user"


def _db(tmp_path, uid=UID):
    return S.make_db(tmp_path / "m65.db", uid)


def _seed_bench3(db, uid=UID):
    for d, w in ((ago(21), 60), (ago(14), 62.5), (ago(7), 65)):
        S.seed_session(db, uid, d, [
            {"exercise_id": "barbell_bench_press", "name": "杠铃平板卧推",
             "set_logs": [S.set_log(weight_kg=w, reps=8)]}])


# ---- M6.5-0 验收：三接口（HTTP）数值/单位/口径一致 ----

def test_three_interfaces_consistent_over_http(tmp_path):
    db = _db(tmp_path)
    pid = S.seed_plan(db, UID)
    _seed_bench3(db)
    app = create_app(db_path=db.path, frontend_dist=tmp_path)
    c = TestClient(app)

    detail = c.get(f"/api/exercises/barbell_bench_press").json()  # 动作存在
    assert detail["id"] == "barbell_bench_press"

    # ① 我的表现：/exercise-stats
    mine = c.get(f"/api/users/{UID}/exercise-stats/barbell_bench_press").json()
    mine_best = max(s["best_e1rm"] for s in mine["sessions"])
    mine_vol = sum(s["volume"] for s in mine["sessions"])
    # ② 周期统计：/period-summary
    ps = c.get(f"/api/users/{UID}/period-summary?days=30").json()
    # ③ AI 训练事实
    facts = fact_service.get_training_facts(db, UID, 30)
    by_ex = {(f.get("exercise_id"), f["metric"]): f for f in facts["facts"]}
    glob = {f["metric"]: f for f in facts["facts"] if not f.get("exercise_id")}

    assert by_ex[("barbell_bench_press", "best-estimated-1rm")]["value"] == mine_best
    assert by_ex[("barbell_bench_press", "volume")]["value"] == mine_vol
    assert glob["volume"]["value"] == ps["volume"]
    assert glob["sessions"]["value"] == ps["sessions"]
    assert glob["working_sets"]["value"] == ps["working_sets"]
    # 单位与口径标签齐备
    e = by_ex[("barbell_bench_press", "best-estimated-1rm")]
    assert e["unit"] == "kg" and e["status"] == "estimated"
    assert e["calculation"] == "epley_best_valid_set_reps_1_12"
    # 追溯链：凡基于打卡记录的事实必须带 source_ids（计划应练推算除外——
    # 它派生自计划而非记录）
    sourced = [f for f in facts["facts"]
               if f["status"] != "insufficient"
               and f["metric"] != "plan-scheduled-sessions"]
    assert sourced and all(f["source_ids"] for f in sourced)


# ---- 场景 A：个人训练分析（对话回复数值可追溯） ----

def test_scenario_a_agent_analysis_traceable(tmp_path):
    db = _db(tmp_path)
    _seed_bench3(db)
    agent = CoachAgent(UID, db_path=db.path)
    agent.profile["onboarding_done"] = True
    reply = agent.chat("我最近卧推有没有进步？")
    prog = fact_service.exercise_progress(db, UID, "barbell_bench_press")
    allowed = {str(f["value"]) for f in prog["facts"]}
    for s in prog["series"]:
        allowed.update({str(s.get("best_e1rm")), str((s.get("best_set") or {}).get("weight_kg")),
                        str((s.get("best_set") or {}).get("reps"))})
    bad = untraceable_numbers(reply, allowed)
    assert not bad, f"回复含不可追溯数值 {bad}: {reply}"
    # 回复应包含趋势判定词（FAKE LLM 会引用工具返回的 verdict）
    assert any(w in reply for w in ("improving", "趋势判定")), reply


# ---- 场景 B：训练方式调整（多方案 → 用户自主决策 → 提案确认） ----

def test_scenario_b_consult_then_decline_no_proposal(tmp_path):
    db = _db(tmp_path)
    agent = CoachAgent(UID, db_path=db.path)
    agent.profile["onboarding_done"] = True
    reply = agent.chat("我应该提高卧推的训练频率吗？")
    # 咨询发生（训练科学专家），用户未表态 → 不产生任何提案
    n = db.conn.execute("SELECT COUNT(*) c FROM change_proposals WHERE user_id=?",
                        (UID,)).fetchone()["c"]
    assert n == 0, "用户未确认前不得产生提案"


def test_scenario_b_proposal_confirm_flow(tmp_path):
    db = _db(tmp_path)
    S.seed_plan(db, UID)
    from coach.approach import initialize_approach
    initialize_approach(db, UID)
    agent = CoachAgent(UID, db_path=db.path)
    agent.profile["onboarding_done"] = True
    agent.chat("我们把训练结构改成上下肢分化")   # FAKE LLM：propose_change
    pending = db.list_proposals(UID, status="pending")
    assert pending, "应产生待确认提案"
    pid = pending[0]["id"]
    # 未确认前计划不变
    v0 = db.get_active_plan_record(UID)["version"]
    result = agent._handle_tool({
        "name": "confirm_proposal",
        "arguments": json.dumps({"proposal_id": pid})}, "normal")
    assert "待确认" in result or "表述含糊" in result  # 本轮无用户确认原话
    agent.chat("确认，就按这个方案改")            # 用户明确同意
    result = agent._handle_tool({
        "name": "confirm_proposal",
        "arguments": json.dumps({"proposal_id": pid})}, "normal")
    assert "已执行" in result or "executed" in result.lower() or "生效" in result


# ---- 场景 C：长期个人尝试（基线 → 执行 → 复盘 → 用户决策） ----

def test_scenario_c_trial_lifecycle(tmp_path):
    db = _db(tmp_path)
    agent = CoachAgent(UID, db_path=db.path)
    agent.profile["onboarding_done"] = True
    # ① 用户先明确表达想尝试（opt-in 语境），再开始尝试（自动基线快照）
    agent.chat("我想尝试把卧推频率从每周1次提高到2次")
    r = agent._handle_tool({"name": "start_personal_trial", "arguments": json.dumps({
        "change_desc": "卧推频率从每周1次提高到2次", "reason": "想突破平台",
        "observe": "相似次数下卧推 e1RM 与完成质量", "stop_rule": "肘部不适即停",
        "review_days": 28})}, "normal")
    assert "已登记" in r, r
    trials = db.personal_trials(UID)
    assert len(trials) == 1 and trials[0]["status"] == "active"
    baseline = json.loads(trials[0]["baseline"])
    assert baseline["kind"] == "trial_baseline_v1"

    # ② 尝试期间实际训练（含一次执行缺口）
    _seed_bench3(db)  # 21/14/7 天前（部分在基线内，复盘取尝试窗口事实）
    S.seed_session(db, UID, ago(3), [
        {"exercise_id": "barbell_bench_press", "name": "杠铃平板卧推",
         "set_logs": [S.set_log(weight_kg=66, reps=8)]}])

    # ③ 复盘草稿：三节结构 + 不归因承诺
    draft_r = agent._handle_tool({
        "name": "review_personal_trial", "arguments": "{}"}, "normal")
    draft = json.loads(draft_r)
    sections = draft["sections"]
    assert set(sections) >= {"observed", "possible_explanations", "unconfirmed"}
    joined = json.dumps(draft, ensure_ascii=False)
    assert "仅适用于本人" in joined
    # ④ 用户决策：保留（keep）——由用户表态，工具只记录
    ok = db.end_personal_trial(UID, trials[0]["id"],
                               "4 周内 8 次组重量 60→66kg，肘部无不适", "keep")
    assert ok
    assert db.personal_trials(UID)[0]["decision"] == "keep"


def test_trial_evidence_sections_structure(tmp_path):
    db = _db(tmp_path)
    _seed_bench3(db)
    db.start_personal_trial(UID, "提高卧推频率", "想突破", "卧推表现", "肘痛即停",
                            14, baseline=trial_evidence.snapshot_baseline(db, UID, "卧推表现"))
    trial = db.personal_trials(UID)[0]
    ev = trial_evidence.trial_evidence(db, UID, trial)
    assert ev["baseline"]["facts"], "基线事实缺失"
    assert ev["execution"]["note"], "执行归因提醒缺失"
    draft = trial_evidence.review_draft(db, UID, trial)
    assert draft["sections"]["unconfirmed"]
