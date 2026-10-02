"""二次审阅的反例：临时库 + 固定工具选择，不依赖真实 LLM。"""
import copy
import importlib
import json
from datetime import datetime, timedelta

import pytest

import coach.agent as agent_module
from coach.agent import CoachAgent
from coach.db import DEFAULT_PROFILE, Database
from coach.plan import generate_plan, plan_to_text
from coach.profile import _is_positive
from coach.review import strength_trend
from coach.safety import check_red_flags


def profile():
    p = copy.deepcopy(DEFAULT_PROFILE)
    p["basic"].update(age=30, gender="男", height_cm=175, weight_kg=75)
    p["experience"]["training_years"] = 4
    p["goal"]["primary"] = "muscle_gain"
    p["resources"]["days_per_week"] = 3
    p["conditions"].update(
        injuries_collected=True, injuries_evidence="没有伤病",
        health_screen_collected=True, health_screen_evidence="身体健康，无异常",
        health_screen={"heart": "无", "pregnancy": "不适用",
                       "medication": "无", "clearance": "无"})
    p["onboarding_done"] = True
    return p


def make_agent(tmp_path, uid="repair"):
    a = CoachAgent(uid, db_path=tmp_path / "test.db")
    a.profile = profile()
    a.db.save_profile(uid, a.profile)
    a.db.create_plan(uid, generate_plan(a.profile))
    return a


def chat_tools(a, text, *calls):
    """每次 LLM 请求返回一个固定工具调用，随后纯文本收尾。"""
    steps = iter(calls)

    def scripted(messages, tools=None, **kwargs):
        call = next(steps, None)
        if call is None:
            return {"content": "已处理。", "tool_calls": []}
        name, args = call
        args = args(a) if callable(args) else args
        return {"content": "", "tool_calls": [{
            "id": f"test-{len(a._turn_tool_results)}", "name": name,
            "arguments": json.dumps(args, ensure_ascii=False)}]}

    a.llm.chat = scripted
    return a.chat(text)


def pending(a, action):
    return next(s for s in a.profile["pending_adjustments"] if s["action"] == action)


@pytest.mark.parametrize("value", [
    "无心脏病，但有高血压", "有：高血压，目前控制正常",
    "没有冠心病但是服用降压药", "血压不正常",
])
def test_mixed_health_positive_is_not_erased(value):
    assert _is_positive(value)


@pytest.mark.parametrize("clearance", [
    "医生不允许运动", "医生允许散步，但禁止大重量和高强度运动",
    "医生允许中等强度运动", "医生未同意恢复力量训练",
])
def test_medical_permission_never_implies_unrestricted_training(clearance):
    p = profile()
    p["conditions"]["health_screen"].update(heart="冠心病史", clearance=clearance)
    text = plan_to_text(generate_plan(p))
    assert "RPE 9" not in text and "RPE 8-9" not in text


def test_explicit_prohibition_alone_blocks_prescription():
    p = profile()
    p["conditions"]["health_screen"]["clearance"] = "医生禁止任何运动"
    assert generate_plan(p)["schedule"] == []


@pytest.mark.parametrize("text", [
    "我以前没有胸闷但现在胸闷了", "我是不是练过头了现在胸口疼",
    "我现在胸闷是什么意思", "以前胸闷好了现在又胸闷", "我现在胸口疼怎么预防",
])
def test_current_symptoms_block_at_chat_entry(tmp_path, text):
    a = make_agent(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("当前红旗症状不应交给 LLM 软化")
    a.llm.chat = forbidden
    a.chat(text)
    assert any(f["status"] == "open" for f in a.profile["conditions"]["pain_flags"])


@pytest.mark.parametrize("text", ["我现在没有胸闷", "胸闷是什么意思", "我会不会胸闷啊"])
def test_negative_or_educational_input_stays_soft(text):
    assert check_red_flags(text).mode == "soft"


def test_flag_identity_survives_filtered_onboarding_list(tmp_path):
    a = make_agent(tmp_path)
    a.profile["onboarding_done"] = False
    a.db.save_profile(a.user_id, a.profile)
    chat_tools(a, "心悸是什么原因引起的")
    a.chat("膝关节突然刺痛")
    a.chat("我现在胸闷")
    flags = a.profile["conditions"]["pain_flags"]
    assert [f["status"] for f in flags] == ["noted", "open", "open"]
    chest_id = flags[2].get("flag_id")
    assert chest_id and chest_id != flags[1].get("flag_id")
    chat_tools(a, "建档继续")
    assert chest_id in a.messages[0]["content"]
    assert flags[1]["flag_id"] in a.messages[0]["content"]
    chat_tools(a, "胸部已经检查，医生确认无碍", (
        "resolve_pain_flag", {"flag_id": chest_id, "note": "胸部已就医无碍"}))
    assert flags[1]["status"] == "open"
    assert flags[2]["status"] == "resolved"


def test_medical_update_suspends_existing_plan_and_adjustments(tmp_path):
    a = make_agent(tmp_path)
    chat_tools(a, "医生禁止高强度运动，冠心病尚未评估", ("update_profile", {
        "patch": {"conditions": {
            "health_screen": {"heart": "冠心病", "clearance": "医生禁止高强度运动"},
            "health_screen_evidence": "医生禁止高强度运动，冠心病尚未评估"}}}))
    assert "RPE 9" not in plan_to_text(a.db.get_active_plan(a.user_id))
    assert a.profile.get("pending_adjustments") or a.db.get_active_plan(a.user_id).get("medical_status")
    chat_tools(a, "查看计划", ("get_plan", {}))
    assert "RPE 9" not in a._turn_tool_results[-1]
    chat_tools(a, "继续加重吗", ("get_adjustment_suggestions", {}))
    assert not any(s["action"] == "increase_weight" for s in a.profile.get("pending_adjustments", []))


def test_get_suggestions_does_not_erase_feedback_regeneration(tmp_path):
    a = make_agent(tmp_path)
    chat_tools(a, "以后先不练卧推", ("record_exercise_feedback", {
        "exercise": "卧推", "status": "avoid", "evidence": "以后先不练卧推"}))
    sid = pending(a, "regenerate_plan")["id"]
    chat_tools(a, "有哪些调整建议", ("get_adjustment_suggestions", {}))
    assert pending(a, "regenerate_plan")["id"] == sid


def rule_suggestions(*args):
    return [
        {"action": "increase_weight", "target": "深蹲", "reason": "进步"},
        {"action": "reduce_frequency", "target": "计划频率", "reason": "时间不够"},
    ]


def test_new_pending_cannot_reuse_consumed_list_index(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    chat_tools(a, "调整建议", ("get_adjustment_suggestions", {}))
    old_ids = {s["id"] for s in a.profile["pending_adjustments"]}
    inc = pending(a, "increase_weight")["id"]
    chat_tools(a, "确认加重", ("apply_adjustment", {"suggestion_id": inc}))
    chat_tools(a, "以后先不练深蹲", ("record_exercise_feedback", {
        "exercise": "深蹲", "status": "avoid", "evidence": "以后先不练深蹲"}))
    regen = pending(a, "regenerate_plan")["id"]
    assert regen not in old_ids
    ids = [s["id"] for s in a.profile["pending_adjustments"]]
    assert len(ids) == len(set(ids))
    chat_tools(a, "确认重排", ("apply_adjustment", {"suggestion_id": regen}))
    plan = a.db.get_active_plan(a.user_id)
    assert plan["adjust_action"] == "regenerate_plan"
    assert all(e["name"] != "杠铃深蹲" for d in plan["schedule"] for e in d["exercises"])


def test_old_version_suggestion_cannot_change_replaced_plan(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    chat_tools(a, "调整建议", ("get_adjustment_suggestions", {}))
    sid = pending(a, "reduce_frequency")["id"]
    p = copy.deepcopy(a.profile)
    p["resources"]["days_per_week"] = 2
    a.db.create_plan(a.user_id, generate_plan(p))
    before = a.db.get_active_plan(a.user_id)
    chat_tools(a, "确认旧降频建议", ("apply_adjustment", {"suggestion_id": sid}))
    assert a.db.get_active_plan(a.user_id) == before


def test_first_confirmation_after_restart_works(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    chat_tools(a, "调整建议", ("get_adjustment_suggestions", {}))
    sid = pending(a, "increase_weight")["id"]
    path, uid = a.db.path, a.user_id
    a.db.conn.close()
    restarted = CoachAgent(uid, db_path=path)
    chat_tools(restarted, "确认你上次的加重建议", (
        "apply_adjustment", {"suggestion_id": sid}))
    assert restarted.db.get_active_plan(uid).get("adjust_action") == "increase_weight"


def test_same_turn_confirmation_still_rejected(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    before = a.db.get_active_plan(a.user_id)
    chat_tools(a, "给我建议", ("get_adjustment_suggestions", {}), (
        "apply_adjustment", lambda x: {"suggestion_id": pending(x, "increase_weight")["id"]}))
    assert a.db.get_active_plan(a.user_id) == before


def test_unknown_variant_does_not_feed_deadlift_trend(tmp_path):
    a = make_agent(tmp_path)
    for days, name, weight in [(2, "传统硬拉", 100), (0, "相扑硬拉", 180)]:
        chat_tools(a, f"{name}{weight}kg做了5次", ("save_checkin", {
            "type": "training", "data": {"exercises": [{
                "name": name, "weight_kg": weight, "reps": 5}]}}))
        a.db.conn.execute("UPDATE checkins SET created_at=? WHERE id=(SELECT MAX(id) FROM checkins)",
                          ((datetime.now() - timedelta(days=days)).isoformat(),))
        a.db.conn.commit()
    trend = strength_trend(a.db.list_checkins(a.user_id), "硬拉")
    assert [v for _, v in trend] == [116.7]
    chat_tools(a, "有没有进步", ("get_adjustment_suggestions", {}))
    assert not any(s["action"] == "increase_weight" and s["target"] == "硬拉"
                   for s in a.profile.get("pending_adjustments", []))


def test_import_real_smoke_is_inert(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("导入真实冒烟不得实例化 Agent 或读取环境")
    monkeypatch.setattr(agent_module, "CoachAgent", forbidden)
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", forbidden)
    import real_test
    importlib.reload(real_test)


def test_real_database_is_forbidden():
    from coach.db import DB_PATH
    with pytest.raises(RuntimeError, match="非临时数据库"):
        Database(DB_PATH)


def test_medical_recovery_requires_confirmation_and_preserves_weights(tmp_path):
    a = make_agent(tmp_path)
    original = a.db.get_active_plan(a.user_id)
    for day in original["schedule"]:
        for ex in day["exercises"]:
            if ex.get("exercise_id") == "barbell_back_squat":
                ex["weight_kg"] = 100
    a.db.create_plan(a.user_id, original)
    chat_tools(a, "冠心病，医生禁止运动", ("update_profile", {"patch": {"conditions": {
        "health_screen": {"heart": "冠心病", "clearance": "医生禁止运动"},
        "health_screen_evidence": "冠心病，医生禁止运动"}}}))
    suspended = a.db.get_active_plan(a.user_id)
    assert suspended["schedule"] == []
    assert a.db.get_plan_content(a.user_id, suspended["resume_plan_id"]) == original
    chat_tools(a, "复查后医生允许恢复正常力量训练", ("update_profile", {"patch": {"conditions": {
        "health_screen": {"clearance": "医生允许恢复正常力量训练"},
        "health_screen_evidence": "复查后医生允许恢复正常力量训练"}}}))
    assert a.db.get_active_plan(a.user_id)["schedule"] == []
    sid = pending(a, "regenerate_plan")["id"]
    chat_tools(a, "查看恢复建议", ("get_adjustment_suggestions", {}))
    assert pending(a, "regenerate_plan")["id"] == sid
    chat_tools(a, "确认恢复", ("apply_adjustment", {"suggestion_id": sid}))
    restored = a.db.get_active_plan(a.user_id)
    assert restored["medical_status"] == "allowed" and restored["schedule"]
    squat = next(ex for d in restored["schedule"] for ex in d["exercises"]
                 if ex.get("exercise_id") == "barbell_back_squat")
    assert squat["weight_kg"] == 100


def test_repeated_suggestion_query_keeps_identity(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    chat_tools(a, "调整建议", ("get_adjustment_suggestions", {}))
    first = copy.deepcopy(a.profile["pending_adjustments"])
    chat_tools(a, "再看一次", ("get_adjustment_suggestions", {}))
    assert a.profile["pending_adjustments"] == first


def test_expired_suggestion_stays_expired_after_restart(tmp_path, monkeypatch):
    from datetime import timezone
    a = make_agent(tmp_path)
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    chat_tools(a, "调整建议", ("get_adjustment_suggestions", {}))
    inc = pending(a, "increase_weight")
    inc["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    a.db.save_profile(a.user_id, a.profile)
    before = a.db.get_active_plan(a.user_id)
    path, uid = a.db.path, a.user_id
    a.db.conn.close()
    a = CoachAgent(uid, db_path=path)
    chat_tools(a, "确认", ("apply_adjustment", {"suggestion_id": inc["id"]}))
    assert "过期" in a._turn_tool_results[-1]
    assert a.db.get_active_plan(uid) == before


def test_foreign_user_cannot_apply_copied_suggestion(tmp_path, monkeypatch):
    a = make_agent(tmp_path, "a")
    b = make_agent(tmp_path, "b")
    monkeypatch.setattr(agent_module, "suggest_adjustments", rule_suggestions)
    chat_tools(a, "调整建议", ("get_adjustment_suggestions", {}))
    inc = copy.deepcopy(pending(a, "increase_weight"))
    b.profile["pending_adjustments"] = [inc]
    before = b.db.get_active_plan("b")
    chat_tools(b, "确认", ("apply_adjustment", {"suggestion_id": inc["id"]}))
    assert "失效" in b._turn_tool_results[-1]
    assert b.db.get_active_plan("b") == before


def test_legacy_pending_without_version_fails_closed(tmp_path):
    a = make_agent(tmp_path)
    a.profile["pending_adjustments"] = [{"id": "adj-1", "action": "increase_weight",
                                         "target": "深蹲", "reason": "旧建议", "created_turn": 10}]
    before = a.db.get_active_plan(a.user_id)
    chat_tools(a, "确认旧建议", ("apply_adjustment", {"suggestion_id": "adj-1"}))
    assert "已作废" in a._turn_tool_results[-1]
    assert a.db.get_active_plan(a.user_id) == before


def test_legacy_flag_ids_are_stable_across_restarts(tmp_path):
    a = make_agent(tmp_path)
    a.profile["conditions"]["pain_flags"] = ["旧的胸闷记录", {"kw": "刺痛", "status": "resolved"}]
    a.db.save_profile(a.user_id, a.profile)
    path, uid = a.db.path, a.user_id
    a.db.conn.close()
    a = CoachAgent(uid, db_path=path)
    flags = copy.deepcopy(a.profile["conditions"]["pain_flags"])
    assert len({f["flag_id"] for f in flags}) == 2
    assert [f["status"] for f in flags] == ["open", "resolved"]
    a.db.conn.close()
    a = CoachAgent(uid, db_path=path)
    assert a.profile["conditions"]["pain_flags"] == flags


def test_plan_and_pending_commit_roll_back_together(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    record = a.db.get_active_plan_record(a.user_id)
    before_profile = a.db.get_profile(a.user_id)
    def fail(*args):
        raise RuntimeError("模拟事务失败")
    monkeypatch.setattr(a.db, "_write_profile", fail)
    with pytest.raises(RuntimeError, match="模拟事务失败"):
        a.db.create_plan(a.user_id, {"schedule": []}, profile={"pending_adjustments": []},
                         expected_plan_id=record["id"])
    assert a.db.get_active_plan_record(a.user_id) == record
    assert a.db.get_profile(a.user_id) == before_profile


def test_stale_plan_commit_is_rejected(tmp_path):
    a = make_agent(tmp_path)
    record = a.db.get_active_plan_record(a.user_id)
    a.db.create_plan(a.user_id, record["content"])
    before = a.db.get_active_plan_record(a.user_id)
    with pytest.raises(ValueError, match="版本已变化"):
        a.db.create_plan(a.user_id, {"schedule": []}, expected_plan_id=record["id"])
    assert a.db.get_active_plan_record(a.user_id) == before


def test_unrecognized_variant_cannot_supply_its_own_id(tmp_path):
    a = make_agent(tmp_path)
    chat_tools(a, "相扑硬拉180kg", ("save_checkin", {"type": "training", "data": {
        "exercises": [{"name": "相扑硬拉", "exercise_id": "deadlift", "weight_kg": 180, "reps": 5}]}}))
    rows = a.db.list_checkins(a.user_id)
    assert rows[0]["data"]["exercises"][0]["exercise_id"] is None
    assert strength_trend(rows, "硬拉") == []


def test_read_side_prefers_confirmed_id_to_display_name():
    from coach.review import _same_exercise
    assert _same_exercise("硬拉", {"exercise_id": "deadlift", "name": "旧显示名"})
    assert not _same_exercise("硬拉", {"exercise_id": None, "name": "硬拉"})
    assert not _same_exercise("硬拉", {"exercise_id": [], "name": "硬拉"})


def test_clear_medical_permission_can_restore_normal_plan():
    p = profile()
    p["conditions"]["health_screen"].update(
        heart="高血压", clearance="医生允许恢复正常力量训练")
    plan = generate_plan(p)
    assert plan["medical_status"] == "allowed" and plan["schedule"]


def test_recovery_suggestion_can_be_requested_again_after_expiry(tmp_path):
    a = make_agent(tmp_path)
    a.profile["conditions"]["health_screen"].update(
        heart="冠心病", clearance="医生禁止运动")
    a.db.save_profile(a.user_id, a.profile)
    a._enforce_medical_permission()
    a.profile["conditions"]["health_screen"]["clearance"] = "医生允许恢复正常力量训练"
    a.db.save_profile(a.user_id, a.profile)
    chat_tools(a, "重新获取恢复建议", ("get_adjustment_suggestions", {}))
    sid = pending(a, "regenerate_plan")["id"]
    assert a.db.get_active_plan(a.user_id)["schedule"] == []
    chat_tools(a, "确认恢复", ("apply_adjustment", {"suggestion_id": sid}))
    assert a.db.get_active_plan(a.user_id)["schedule"]
