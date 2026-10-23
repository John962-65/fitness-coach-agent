"""R3 测试：调整引擎状态机（A1-A6）+ 个体数据（user_exercise / 教练笔记）"""
import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from coach.adjust import apply_adjustment, is_deload_active, suggest_adjustments
from coach.agent import CoachAgent
from coach.db import Database
from coach.plan import plan_to_text


def ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def _agent(uid="s"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


PPL_PLAN = {
    "days_per_week": 3,
    "template": "三分化推拉蹲",
    "schedule": [
        {"day": "周一", "focus": "推", "exercises": [
            {"name": "杠铃平板卧推", "sets": 4, "reps": "8-12"},
            {"name": "杠铃上斜卧推", "sets": 3, "reps": "8-12"},
            {"name": "侧平举", "sets": 3, "reps": "12-15"}]},
        {"day": "周三", "focus": "拉", "exercises": [
            {"name": "硬拉", "sets": 4, "reps": "6-10"},
            {"name": "坐姿划船", "sets": 4, "reps": "10-12"}]},
        {"day": "周五", "focus": "蹲", "exercises": [
            {"name": "杠铃深蹲", "sets": 4, "reps": "8-12"},
            {"name": "倒蹬", "sets": 3, "reps": "10-15"}]},
    ],
    "notes": [],
}

AB_PLAN = {
    "days_per_week": 3,
    "template": "新手全身 A/B",
    "schedule": [
        {"day": "周一", "focus": "全身A",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5", "note": ""}]},
        {"day": "周三", "focus": "全身B",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5", "note": ""}]},
        {"day": "周五", "focus": "全身A",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5", "note": ""}]},
    ],
}


# ---------- A1：deload 带到期日的状态 ----------

def test_deload_is_expiring_state():
    new = apply_adjustment(PPL_PLAN, "deload", "整体", "疲劳")
    assert is_deload_active(new)
    assert new["deload"]["factor"] == 0.5
    # 到期日 = 7 天后
    assert new["deload"]["until"] == (
        date.today() + timedelta(days=7)).isoformat()


def test_deload_reentry_refused():
    once = apply_adjustment(PPL_PLAN, "deload", "整体", "疲劳")
    with pytest.raises(ValueError, match="已在卸载周"):
        apply_adjustment(once, "deload", "整体", "又累了")


def test_deload_expires_and_plan_text_renders():
    plan = dict(PPL_PLAN)
    plan["schedule"] = [dict(d, exercises=[dict(e) for e in d["exercises"]])
                        for d in PPL_PLAN["schedule"]]
    plan["schedule"][0]["exercises"][0]["weight_kg"] = 60.0
    new = apply_adjustment(plan, "deload", "整体", "疲劳")
    text = plan_to_text(new)
    assert "30.0kg（卸载周" in text  # 60 × 0.5
    # 过期后不再渲染卸载
    new["deload"]["until"] = (date.today() - timedelta(days=1)).isoformat()
    assert not is_deload_active(new)
    text2 = plan_to_text(new)
    assert "卸载周" not in text2.split("·")[0]  # 动作行没有卸载标记
    assert "60.0kg" in text2  # 原处方重量还在，没被改坏


# ---------- A2：降频 = 主项重组，不是删最后一天 ----------

def test_reduce_frequency_keeps_leg_day():
    new = apply_adjustment(PPL_PLAN, "reduce_frequency", "计划频率", "执行率低")
    assert len(new["schedule"]) == 2
    names = [e["name"] for d in new["schedule"] for e in d["exercises"]]
    # 推拉蹲三天的主项（卧推/上斜/硬拉/深蹲）都必须还在
    for main in ("杠铃平板卧推", "硬拉", "杠铃深蹲"):
        assert main in names
    assert all("全身" in d["focus"] for d in new["schedule"])


def test_reduce_frequency_single_day_refused():
    one_day = dict(PPL_PLAN, schedule=PPL_PLAN["schedule"][:1])
    with pytest.raises(ValueError, match="只有 1 天"):
        apply_adjustment(one_day, "reduce_frequency", "计划频率", "x")


# ---------- A3：add_volume 批量修改全部出现 ----------

def test_add_volume_modifies_all_occurrences():
    new = apply_adjustment(AB_PLAN, "add_volume", "深蹲", "停滞")
    sets = [d["exercises"][0]["sets"] for d in new["schedule"]]
    assert sets == [7, 7, 7]


# ---------- A5：处方重量字段 ----------

def test_increase_weight_writes_prescription():
    new = apply_adjustment(PPL_PLAN, "increase_weight", "杠铃深蹲", "进步",
                           last_weight=100.0)
    squat = new["schedule"][2]["exercises"][0]
    assert squat["weight_kg"] == 105.0
    assert "下次" not in (squat.get("note") or "")  # 不再堆备注


def test_increase_weight_accumulates_on_field():
    first = apply_adjustment(PPL_PLAN, "increase_weight", "杠铃深蹲", "进步",
                             last_weight=100.0)
    second = apply_adjustment(first, "increase_weight", "杠铃深蹲", "又进步")
    squat = second["schedule"][2]["exercises"][0]
    assert squat["weight_kg"] == 110.0


def test_increase_weight_upper_body_increment():
    new = apply_adjustment(PPL_PLAN, "increase_weight", "卧推", "进步",
                           last_weight=60.0)
    bench = new["schedule"][0]["exercises"][0]
    assert bench["weight_kg"] == 62.5


def test_decrease_weight_prescription():
    new = apply_adjustment(PPL_PLAN, "decrease_weight", "硬拉", "状态差",
                           last_weight=140.0)
    dl = new["schedule"][1]["exercises"][0]
    assert dl["weight_kg"] == 126.0


# ---------- A6：两步确认 ----------

def _agent_with_progress(uid="s"):
    """造一个有连续进步打卡的 agent（深蹲 60→65）"""
    agent = _agent(uid)
    agent.profile["onboarding_done"] = True
    agent.db.create_plan(uid, dict(AB_PLAN))
    for i, w in enumerate((60, 62.5, 65)):
        agent.db.add_checkin(uid, "training", {"exercises": [
            {"name": "杠铃深蹲", "weight_kg": w, "sets": 5, "reps": 5}]})
        agent.db.conn.execute(
            "UPDATE checkins SET created_at=? WHERE user_id=? AND id=?",
            (ago(9 - i * 3), uid, i + 1))
    agent.db.conn.commit()
    return agent


def test_evidence_backfill_from_user_message():
    agent = _agent()
    agent.messages.append({"role": "user", "content": "我膝盖以前受过伤"})
    agent._handle_tool({"name": "update_profile",
                        "arguments": json.dumps({"patch": {
                            "conditions": {"injuries": ["膝伤"]}}})}, "onboarding")
    c = agent.profile["conditions"]
    assert c["injuries_evidence"] == "我膝盖以前受过伤"


def test_evidence_backfill_keeps_explicit():
    """2026-10-11 规格变更（评审 P0-3）：LLM 自附 evidence 必须出现在真实用户消息中。"""
    agent = _agent()
    agent.messages.append({"role": "user", "content": "我膝盖有伤，这是用户的明确原话"})
    agent._handle_tool({"name": "update_profile",
                        "arguments": json.dumps({"patch": {
                            "conditions": {"injuries": ["膝伤"],
                                           "injuries_evidence": "我膝盖有伤"}}})},
                       "onboarding")
    assert agent.profile["conditions"]["injuries_evidence"] == "我膝盖有伤"


def test_auto_finalize_when_profile_complete():
    """兜底：档案齐了但 LLM 没调 finish_onboarding，代码自己收尾出计划"""
    agent = _agent()
    # 2026-10-11（评审 P0-3）：evidence 须为用户原话子串——原"没伤/没事"为编造依据，已废弃
    agent.messages.append({"role": "user",
                           "content": "男28岁178cm85kg，没有伤病，健康筛查没事"})
    complete = {"patch": {
        "basic": {"age": 28, "gender": "男", "height_cm": 178, "weight_kg": 85},
        "goal": {"primary": "fat_loss"},
        "resources": {"days_per_week": 3},
        "conditions": {"injuries": [], "injuries_evidence": "没有伤病",
                       "health_screen": {"heart": "无", "pregnancy": "不适用",
                                         "medication": "无", "clearance": "无"},
                       "health_screen_evidence": "没事"},
    }}
    result = agent._handle_tool({"name": "update_profile",
                                 "arguments": json.dumps(complete)}, "onboarding")
    assert agent.profile["onboarding_done"] is True
    assert agent.db.get_active_plan("s") is not None
    assert "建档完成" in result or "计划" in result


def test_finalize_is_idempotent():
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.db.create_plan("s", {"template": "X", "level": "beginner",
                               "days_per_week": 3, "schedule": [], "notes": []})
    v_before = agent.db.conn.execute(
        "SELECT MAX(version) FROM plans WHERE user_id='s'").fetchone()[0]
    agent._finalize_onboarding()
    v_after = agent.db.conn.execute(
        "SELECT MAX(version) FROM plans WHERE user_id='s'").fetchone()[0]
    assert v_before == v_after


def test_two_step_flow():
    agent = _agent_with_progress()
    # 1. 获取建议 → pending 落库（记录生成轮次）
    result = agent._handle_tool({"name": "get_adjustment_suggestions",
                                 "arguments": "{}"}, "normal")
    assert "adj-" in result and "increase_weight" in result
    pending = agent.profile["pending_adjustments"]
    inc = next(s for s in pending if s["action"] == "increase_weight")
    # 2. 错误 id 拒绝
    bad = agent._handle_tool({"name": "apply_adjustment",
                              "arguments": '{"suggestion_id": "adj-99"}'}, "normal")
    assert "没有待执行的建议" in bad
    # 3. 用户下一轮确认（轮次前进），正确 id 执行 → 新版本 + pending 消费
    agent.db.add_message(agent.user_id, "user", "确认执行")
    ok = agent._handle_tool({"name": "apply_adjustment",
                             "arguments": json.dumps(
                                 {"suggestion_id": inc["id"]})}, "normal")
    assert "计划已更新" in ok
    plan = agent.db.get_active_plan("s")
    assert plan["adjust_action"] == "increase_weight"
    assert plan["schedule"][0]["exercises"][0]["weight_kg"] == 70.0  # 65+5
    assert all(s["action"] != "increase_weight"
               for s in agent.profile["pending_adjustments"])


def test_same_turn_apply_refused():
    """2026-09-29：LLM 同轮 suggest 完立刻 apply（中间没有用户确认）→ 拒绝"""
    agent = _agent_with_progress()
    result = agent._handle_tool({"name": "get_adjustment_suggestions",
                                 "arguments": "{}"}, "normal")
    inc = next(s for s in agent.profile["pending_adjustments"]
               if s["action"] == "increase_weight")
    refused = agent._handle_tool({"name": "apply_adjustment",
                                  "arguments": json.dumps(
                                      {"suggestion_id": inc["id"]})}, "normal")
    assert "本轮刚生成" in refused and "下一轮" in refused
    # 计划没有被改
    assert agent.db.get_active_plan("s").get("adjust_action") is None


def test_pending_suggestion_expires():
    """建议超过 PENDING_EXPIRE_TURNS 轮未确认 → 作废"""
    from coach.agent import PENDING_EXPIRE_TURNS
    agent = _agent_with_progress()
    agent._handle_tool({"name": "get_adjustment_suggestions",
                        "arguments": "{}"}, "normal")
    inc = next(s for s in agent.profile["pending_adjustments"]
               if s["action"] == "increase_weight")
    for _ in range(PENDING_EXPIRE_TURNS + 1):
        agent.db.add_message(agent.user_id, "user", "新的对话轮次")
    expired = agent._handle_tool({"name": "apply_adjustment",
                                  "arguments": json.dumps(
                                      {"suggestion_id": inc["id"]})}, "normal")
    assert "已作废" in expired


def test_apply_without_suggest_refused():
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.db.create_plan("s", dict(AB_PLAN))
    result = agent._handle_tool({"name": "apply_adjustment",
                                 "arguments": '{"suggestion_id": "adj-1"}'}, "normal")
    assert "没有待执行的建议" in result


# ---------- A6 输出侧护栏：未落库的"计划已更新"声称 ----------

def test_plan_claim_guard_strong_claim():
    """强计划声称 + 计划没变 → 更正"""
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.db.create_plan("s", {"template": "X", "level": "beginner",
                               "days_per_week": 3, "schedule": [], "notes": []})
    agent._plan_before = agent._plan_snapshot()
    out = agent._guard_plan_claim("好的，计划已更新 ✅ 深蹲下次 52.5kg")
    assert "还没有写进你的计划" in out


def test_plan_claim_guard_soft_claim_with_pending():
    """软完成声称（已落库）+ 有待执行建议 + 计划没变 → 更正"""
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.profile["pending_adjustments"] = [{"id": "adj-1", "action": "increase_weight"}]
    agent.db.create_plan("s", {"template": "X", "level": "beginner",
                               "days_per_week": 3, "schedule": [], "notes": []})
    agent._plan_before = agent._plan_snapshot()
    out = agent._guard_plan_claim("已落库，深蹲下次 52.5kg 5×5")
    assert "还没有写进你的计划" in out


def test_plan_claim_guard_soft_claim_without_pending_passes():
    """软声称但没有待执行建议（如打卡已落库）→ 不误伤"""
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.db.create_plan("s", {"template": "X", "level": "beginner",
                               "days_per_week": 3, "schedule": [], "notes": []})
    agent._plan_before = agent._plan_snapshot()
    out = agent._guard_plan_claim("打卡已落库，今天练得不错")
    assert "更正" not in out


def test_plan_claim_guard_passes_when_plan_changed():
    """计划确实变了（apply 生效）→ 放行"""
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.db.create_plan("s", {"template": "X", "level": "beginner",
                               "days_per_week": 3, "schedule": [], "notes": []})
    agent._plan_before = agent._plan_snapshot()
    agent.db.create_plan("s", {"template": "Y", "level": "beginner",
                               "days_per_week": 3, "schedule": [], "notes": []})
    out = agent._guard_plan_claim("计划已更新 ✅")
    assert "更正" not in out


def test_plan_claim_guard_passes_without_claim():
    agent = _agent()
    agent._plan_before = agent._plan_snapshot()
    out = agent._guard_plan_claim("这次练得不错，继续保持")
    assert "更正" not in out


# ---------- user_exercise 自动状态（18.1 第③层） ----------

def test_checkin_auto_updates_exercise_state():
    agent = _agent()
    agent._handle_tool({"name": "save_checkin", "arguments": json.dumps({
        "type": "training",
        "data": {"exercises": [{"name": "深蹲", "weight_kg": 80, "sets": 5,
                                "reps": 5, "rpe": 8}]},
    })}, "normal")
    row = agent.db.get_user_exercise("s", "barbell_back_squat")
    assert row["last_weight"] == 80.0 and row["last_rpe"] == 8.0
    assert row["best_e1rm"] == 93.3
    # 再练更轻的一次，best 不被拉低
    agent._handle_tool({"name": "save_checkin", "arguments": json.dumps({
        "type": "training",
        "data": {"exercises": [{"name": "深蹲", "weight_kg": 60, "reps": 5}]},
    })}, "normal")
    row = agent.db.get_user_exercise("s", "barbell_back_squat")
    assert row["last_weight"] == 60.0 and row["best_e1rm"] == 93.3


# ---------- record_exercise_feedback（18.1 第②层） ----------

def test_record_feedback_requires_evidence_and_known_exercise():
    agent = _agent()
    r = agent._handle_tool({"name": "record_exercise_feedback",
                            "arguments": '{"exercise": "保加利亚分腿蹲"}'}, "normal")
    assert "evidence" in r
    r = agent._handle_tool({"name": "record_exercise_feedback",
                            "arguments": '{"exercise": "不知道啥动作", "evidence": "x"}'},
                           "normal")
    assert "未识别动作" in r
    agent.db.add_message("s", "user", "保加利亚分腿蹲找不到臀的感觉")
    r = agent._handle_tool({"name": "record_exercise_feedback",
                            "arguments": json.dumps({
                                "exercise": "保加利亚分腿蹲", "feel": 1,
                                "evidence": "找不到臀的感觉"})}, "normal")
    assert "已记录" in r
    row = agent.db.get_user_exercise("s", "bulgarian_split_squat")
    assert row["feel"] == 1 and "臀" in row["evidence"]


def test_feedback_surfaces_in_system_prompt():
    agent = _agent()
    agent.db.add_message("s", "user", "杠铃卧推推完肩膀不舒服")
    agent._handle_tool({"name": "record_exercise_feedback",
                        "arguments": json.dumps({
                            "exercise": "杠铃卧推", "discomfort": "肩前侧不适",
                            "status": "avoid", "evidence": "推完肩膀不舒服"})},
                       "normal")
    prompt = agent._build_system_prompt()
    assert "杠铃平板卧推" in prompt and "肩前侧不适" in prompt and "避开" in prompt


# ---------- 教练笔记（18.3） ----------

def test_coach_note_lifecycle():
    agent = _agent()
    r = agent._handle_tool({"name": "add_coach_note",
                            "arguments": json.dumps({
                                "note": "硬拉时下背先酸", "evidence": "用户打卡原话",
                                "expires_days": 30})}, "normal")
    assert "#" in r
    assert "硬拉时下背先酸" in agent._coach_notes_text()
    note_id = agent.db.open_coach_notes("s")[0]["id"]
    r = agent._handle_tool({"name": "close_coach_note",
                            "arguments": json.dumps({"note_id": note_id})}, "normal")
    assert "已关闭" in r
    assert agent._coach_notes_text() == "（暂无）"


def test_coach_note_requires_evidence():
    agent = _agent()
    r = agent._handle_tool({"name": "add_coach_note",
                            "arguments": '{"note": "随便记点啥"}'}, "normal")
    assert "evidence" in r
    assert agent.db.open_coach_notes("s") == []


def test_coach_note_expiry():
    agent = _agent()
    agent.db.add_coach_note("s", "临时观察", "依据", expires_days=-1)
    assert agent.db.open_coach_notes("s") == []


# ---------- login_recap 安全跟进 ----------

def test_login_recap_shows_open_pain_flags():
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.chat("我训练时胸闷心慌")
    from coach.review import login_recap
    recap = login_recap(agent.db, "s", None)
    assert "安全记录" in recap and "胸闷" in recap


# ---------- 个性化闭环：重排计划建议（2026-09-29） ----------

def _agent_with_plan(uid="s"):
    agent = _agent(uid)
    agent.profile["onboarding_done"] = True
    agent.db.create_plan(uid, dict(PPL_PLAN))
    return agent


def test_avoid_feedback_offers_regenerate():
    """用户说"先不练它"（avoid）→ 生成重排建议（pending），走两步确认"""
    agent = _agent_with_plan()
    agent.db.add_message(agent.user_id, "user", "杠铃卧推先不练它")
    result = agent._handle_tool({"name": "record_exercise_feedback",
                                 "arguments": json.dumps({
                                     "exercise": "杠铃卧推", "status": "avoid",
                                     "evidence": "先不练它"})}, "normal")
    assert "重排" in result
    regen = next(s for s in agent.profile["pending_adjustments"]
                 if s["action"] == "regenerate_plan")
    # 同轮不能执行；下一轮确认后 apply → 新版本中杠铃平板卧推被替换
    agent.db.add_message(agent.user_id, "user", "确认执行")
    ok = agent._handle_tool({"name": "apply_adjustment",
                             "arguments": json.dumps(
                                 {"suggestion_id": regen["id"]})}, "normal")
    assert "整体重排" in ok
    plan = agent.db.get_active_plan("s")
    names = [e["name"] for d in plan["schedule"] for e in d["exercises"]]
    assert "杠铃平板卧推" not in names
    assert plan["adjust_action"] == "regenerate_plan"


def test_regenerate_preserves_prescription_weights():
    """重排保留已有处方重量：旧计划深蹲 100kg，重排后同动作仍是 100kg"""
    agent = _agent_with_plan()
    plan = agent.db.get_active_plan("s")
    plan["schedule"][2]["exercises"][0]["weight_kg"] = 100.0  # 周五杠铃深蹲
    agent.db.create_plan("s", plan)
    agent.db.add_message(agent.user_id, "user", "杠铃卧推肩膀不舒服，先不练")
    agent._handle_tool({"name": "record_exercise_feedback",
                        "arguments": json.dumps({
                            "exercise": "杠铃卧推", "status": "avoid",
                            "evidence": "肩膀不舒服，先不练"})}, "normal")
    regen = next(s for s in agent.profile["pending_adjustments"]
                 if s["action"] == "regenerate_plan")
    agent.db.add_message(agent.user_id, "user", "确认执行")
    agent._handle_tool({"name": "apply_adjustment",
                        "arguments": json.dumps(
                            {"suggestion_id": regen["id"]})}, "normal")
    new_plan = agent.db.get_active_plan("s")
    weights = {e["name"]: e.get("weight_kg")
               for d in new_plan["schedule"] for e in d["exercises"]}
    assert weights.get("杠铃深蹲") == 100.0


def test_profile_injury_change_offers_regenerate():
    """normal 模式新增伤病 → 生成重排建议"""
    agent = _agent_with_plan()
    # 2026-10-11（评审二轮 P0-3 收口）：依据绑定每一次变更——档案旧依据不再让新变更免检
    agent.db.add_message(agent.user_id, "user", "我腰受伤了")
    agent.profile["conditions"]["injuries_collected"] = True
    result = agent._handle_tool({"name": "update_profile",
                                 "arguments": json.dumps({"patch": {
                                     "conditions": {"injuries": ["腰"],
                                                    "injuries_evidence": "我腰受伤了"}}})},
                                "normal")
    assert "重排" in result
    assert any(s["action"] == "regenerate_plan"
               for s in agent.profile["pending_adjustments"])


def test_regenerate_not_duplicated():
    """已有一条待确认的重排建议时不重复生成"""
    agent = _agent_with_plan()
    agent.db.add_message(agent.user_id, "user", "杠铃卧推先不练它")
    for _ in range(2):
        agent._handle_tool({"name": "record_exercise_feedback",
                            "arguments": json.dumps({
                                "exercise": "杠铃卧推", "status": "avoid",
                                "evidence": "先不练它"})}, "normal")
    regens = [s for s in agent.profile["pending_adjustments"]
              if s["action"] == "regenerate_plan"]
    assert len(regens) == 1
