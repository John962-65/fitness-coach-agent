"""DESIGN 17/20/26: adversarial input and cross-turn state invariants."""
import copy
import json
from datetime import datetime, timedelta

import pytest

from coach.onboarding import can_finish
from coach.profile import merge_patch
from coach.review import build_summary, last_weight, rpe_drift
from test_repair_regressions import chat_tools, make_agent, pending, profile


@pytest.mark.parametrize("reply", ["今天练什么", "先不要重排", "我还没同意调整", "重排可以吗？",
                                  "今天天气很好", "我好久没练了", "今天做了行走弓步"])
def test_adjustment_requires_actual_consent(tmp_path, reply):
    a = make_agent(tmp_path)
    a._offer_regenerate("用户时间变化")
    sid = pending(a, "regenerate_plan")["id"]
    old = a.db.get_active_plan_record(a.user_id)
    chat_tools(a, reply, ("apply_adjustment", {"suggestion_id": sid}))
    assert a.db.get_active_plan_record(a.user_id) == old
    assert pending(a, "regenerate_plan")["id"] == sid


def test_goal_confirmation_commits_plan_and_goal_together(tmp_path):
    a = make_agent(tmp_path)
    old = a.db.get_active_plan_record(a.user_id)
    chat_tools(a, "我决定转为减脂", ("update_profile", {"patch": {"goal": {"primary": "fat_loss"}}}))
    entry = a.profile["pending_profile_changes"][0]
    chat_tools(a, "确认把目标改为减脂", ("confirm_profile_change", {"change_id": entry["id"], "accept": True}))
    saved = a.db.get_existing_profile(a.user_id)
    plan = a.db.get_active_plan_record(a.user_id)
    assert plan["id"] != old["id"]
    assert plan["content"]["goal_version"] == saved["goal"]["version"]
    assert any("减脂期" in n for n in plan["content"]["notes"])
    assert not saved.get("pending_adjustments")


def test_goal_commit_failure_keeps_old_goal_and_pending_confirmation(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    chat_tools(a, "我决定转减脂", ("update_profile", {"patch": {"goal": {"primary": "fat_loss"}}}))
    old = copy.deepcopy(a.profile)
    old_plan = a.db.get_active_plan_record(a.user_id)
    entry = old["pending_profile_changes"][0]
    def fail(*args, **kwargs):
        raise ValueError("synthetic write failure")
    monkeypatch.setattr(a.db, "create_plan", fail)
    chat_tools(a, "确认把目标改为减脂", ("confirm_profile_change", {"change_id": entry["id"], "accept": True}))
    assert a.profile == old
    assert a.db.get_existing_profile(a.user_id) == old
    assert a.db.get_active_plan_record(a.user_id) == old_plan


@pytest.mark.parametrize("patch", [
    {"conditions": {"health_screen": "无"}},
    {"conditions": {"injuries": "膝盖旧伤"}},
    {"experience": {"big3": "100kg"}},
    {"goal": {"primary": ["fat_loss"]}},
    {"resources": {"days_per_week": 8}},
    {"resources": {"days_per_week": 2.5}},
    {"resources": {"session_minutes": -30}},
    {"basic": {"weight_kg": float("inf")}},
    {"basic": {"weight_kg": float("nan")}},
    {"experience": []},
])
def test_bad_profile_patch_cannot_corrupt_current_profile(patch):
    original = profile()
    clean, report = merge_patch(original, patch)
    assert clean == original
    assert report["warnings"] or report["dropped"]


def test_alias_fields_receive_the_same_numeric_validation():
    p, _ = merge_patch(profile(), {"resources": {"days": "2天"}, "basic": {"体重": "150斤"}})
    assert p["resources"]["days_per_week"] == 2
    assert p["basic"]["weight_kg"] == 75


def test_partial_health_screen_does_not_finish_onboarding():
    p = profile()
    p["conditions"]["health_screen"] = {"heart": "无"}
    assert not can_finish(p)[0]


@pytest.mark.parametrize("arguments", ["null", "[]", '"hello"', '{"patch": {"conditions": "无"}}'])
def test_invalid_tool_arguments_return_a_recoverable_error(tmp_path, arguments):
    a = make_agent(tmp_path)
    before = copy.deepcopy(a.profile)
    result = a._handle_tool({"name": "update_profile", "arguments": arguments}, "normal")
    assert isinstance(result, str)
    assert a.profile == before


def test_same_day_latest_weight_and_rpe_use_actual_record_order():
    rows = [
        {"id": 2, "type": "training", "at": "2026-10-20T20:00:00", "data": {"exercises": [
            {"name": "深蹲", "weight_kg": 60, "rpe": 9}]}},
        {"id": 1, "type": "training", "at": "2026-10-20T09:00:00", "data": {"exercises": [
            {"name": "深蹲", "weight_kg": 60, "rpe": 7}]}},
    ]
    assert rpe_drift(rows, "深蹲") == "rising"
    rows[0]["data"]["exercises"][0]["weight_kg"] = 70
    assert last_weight(rows, "深蹲") == 70


def test_body_checkin_does_not_hide_a_training_layoff(tmp_path):
    a = make_agent(tmp_path)
    ck = a.db.add_checkin(a.user_id, "training", {"exercises": [{"name": "深蹲", "weight_kg": 60}]})
    a.db.conn.execute("UPDATE checkins SET created_at=? WHERE id=?",
                      ((datetime.now() - timedelta(days=20)).isoformat(), ck))
    a.db.conn.commit()
    a.db.add_checkin(a.user_id, "body", {"weight_kg": 75})
    summary = build_summary(a.db, a.user_id, a.db.get_active_plan(a.user_id))
    assert summary["days_since_last_training"] >= 19
    out = a._handle_tool({"name": "get_pre_training_brief", "arguments": "{}"}, "normal")
    assert "复训" in out


def test_profile_history_retains_more_than_the_last_change():
    p = profile()
    start = p["basic"]["weight_kg"]
    p, _ = merge_patch(p, {"basic": {"weight_kg": 80}})
    p, _ = merge_patch(p, {"basic": {"weight_kg": 82}})
    events = p["_history"]["basic.weight_kg"]["revisions"]
    assert [e["old"] for e in events] == [start, 80]


def test_personal_trial_cannot_bypass_a_safety_fence(tmp_path):
    a = make_agent(tmp_path)
    a.chat("我现在胸闷")
    result = a._handle_tool({"name": "start_personal_trial", "arguments": json.dumps({
        "change_desc": "提高卧推重量", "reason": "想进步", "observe": "表现",
        "stop_rule": "疼痛就停止", "review_days": 7})}, "normal")
    assert not a.db.personal_trials(a.user_id)
    assert "隔离" in result or "安全" in result


def test_successful_reply_is_not_duplicated_in_model_history(tmp_path):
    a = make_agent(tmp_path)
    reply = chat_tools(a, "你好")
    assert a.messages[-1] == {"role": "assistant", "content": reply}
    assert a.messages[-2]["role"] == "user"


def test_unrelated_quote_cannot_clear_medical_restrictions(tmp_path):
    a = make_agent(tmp_path)
    a.profile["conditions"]["health_screen"].update(heart="冠心病", clearance="医生禁止运动")
    a.db.save_profile(a.user_id, a.profile)
    before = copy.deepcopy(a.profile["conditions"]["health_screen"])
    chat_tools(a, "你好", ("update_profile", {"patch": {"conditions": {
        "health_screen": {"heart": "无", "clearance": "无"}, "health_screen_evidence": "你好"}}}))
    assert a.profile["conditions"]["health_screen"] == before


def test_fake_mode_does_not_invent_health_answers(tmp_path):
    from coach.agent import CoachAgent
    a = CoachAgent("new", db_path=tmp_path / "new.db")
    a.chat("我没有任何伤病")
    assert a.profile["conditions"]["injuries_collected"]
    assert not a.profile["conditions"]["health_screen_collected"]
    assert not a.profile["onboarding_done"]


def test_idempotent_onboarding_does_not_reveal_fenced_plan(tmp_path):
    a = make_agent(tmp_path)
    a.chat("我现在胸闷")
    text = a._finalize_onboarding()
    assert "计划已隔离" in text
    assert "杠铃平板卧推" not in text


def test_card_binding_and_quarantine_are_checked_at_runtime(monkeypatch):
    import coach.cards as cards
    from coach.claims import claim_store
    from coach.claim_review import content_fingerprint
    from test_cards import _card
    claim = {"id": "synthetic", "claim": "Original test content"}
    card = _card(bindings=[{"claim_id": claim["id"], "claim_fingerprint": content_fingerprint(claim)}])
    card["review"] = cards.approve_card(card, "合成审核员", "合成测试", "2026-10-22")
    monkeypatch.setattr(claim_store, "_by_id", {claim["id"]: claim})
    monkeypatch.setattr(cards, "load_cards", lambda: {card["card_id"]: card})
    monkeypatch.setattr(cards, "load_quarantined", lambda: [])
    assert cards.approved_cards()
    claim["claim"] = "Changed after approval"
    assert not cards.approved_cards()
    with pytest.raises(cards.CardError):
        cards.serve_card(card)
    claim["claim"] = "Original test content"
    monkeypatch.setattr(cards, "load_quarantined", lambda: [{"id": "synthetic"}])
    assert not cards.approved_cards()


def test_unapproved_card_cannot_claim_to_be_reviewed():
    from coach.cards import CardError, serve_card
    from test_cards import _card
    with pytest.raises(CardError):
        serve_card(_card())


def test_limited_activity_permission_is_not_resolution_of_symptoms():
    from coach.confirmation import classify_safety_resolution
    assert classify_safety_resolution("医生说可以散步") != "accept"


@pytest.mark.parametrize("frames", [[], [[]], [None, None], [[{}] * 33] * 3])
def test_video_without_visible_landmarks_is_not_a_clean_result(frames):
    from coach.vision_rules import analyze
    assert analyze("squat", frames)[0]["code"] == "INSUFFICIENT_DATA"


def test_video_rejects_unsupported_camera_view():
    from coach.vision_rules import analyze
    from test_vision import _bench_frames
    assert analyze("bench", _bench_frames(), "front")[0]["code"] == "UNSUPPORTED_VIEW"


def test_bench_low_visibility_does_not_generate_technique_findings():
    from coach.vision_rules import analyze
    from test_vision import _bench_frames
    frames = _bench_frames("half")
    for f in frames:
        for i in (11, 13, 15):
            f[i]["visibility"] = 0
    assert analyze("bench", frames)[0]["code"] == "INSUFFICIENT_DATA"


def test_front_view_does_not_run_side_view_depth_checks():
    from coach.vision_rules import check_squat
    from test_vision import _frame
    frames = [_frame((0.5, 0.3), (0.44, 0.55), (0.47, 0.68), (0.4, 0.85),
                     extra={24: (0.56, 0.55), 26: (0.56, 0.68), 28: (0.6, 0.85)})] * 4
    original = check_squat(frames, "front")
    mirror = copy.deepcopy(frames)
    for f in mirror:
        for point in f:
            point["x"] = 1 - point["x"]
    assert original == check_squat(mirror, "front")
    assert {f["code"] for f in original} == {"SQUAT_VALGUS"}


def test_video_angle_coordinates_use_image_aspect_ratio():
    from coach.vision_rules import _point
    assert _point([{"x": 0.5, "y": 0.2, "visibility": 0.9, "aspect_ratio": 2}], 0) == (1, 0.2)


def test_failed_checkin_does_not_leave_derived_state_or_partial_record(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    def fail(*args, **kwargs):
        raise ValueError("synthetic derived-state failure")
    monkeypatch.setattr(a.db, "_recompute_exercise_states", fail)
    chat_tools(a, "卧推60kg做5次", ("save_checkin", {"type": "training", "data": {
        "exercises": [{"name": "卧推", "weight_kg": 60, "reps": 5}]}}))
    assert not a.db.list_checkins(a.user_id)
    assert not a.db.all_exercise_states(a.user_id)


def test_new_checkin_invalidates_old_rule_suggestion(tmp_path):
    a = make_agent(tmp_path)
    a.profile["pending_adjustments"] = [{"id": "old", "source": "rule", "action": "increase_weight"}]
    a.db.save_profile(a.user_id, a.profile)
    chat_tools(a, "卧推60kg做5次", ("save_checkin", {"type": "training", "data": {
        "exercises": [{"name": "卧推", "weight_kg": 60, "reps": 5}]}}))
    assert not a.profile["pending_adjustments"]
    assert a.db.get_user_exercise(a.user_id, "barbell_bench_press")["last_weight"] == 60


def test_closing_expired_note_invalidates_its_suggestions(tmp_path):
    a = make_agent(tmp_path)
    nid = a.db.add_coach_note(a.user_id, "出差两周后恢复", "原话", expires_days=-1)
    a.profile["pending_adjustments"] = [{"id": "old", "reason": "出差两周后恢复，需要重排"}]
    a.db.save_profile(a.user_id, a.profile)
    a._handle_tool({"name": "close_coach_note", "arguments": json.dumps({"note_id": nid})}, "normal")
    assert not a.profile["pending_adjustments"]


@pytest.mark.parametrize("tool, args", [
    ("record_exercise_feedback", {"exercise": "卧推", "preference": -2, "evidence": "编造的原话"}),
    ("add_coach_note", {"note": "讨厌卧推", "note_type": "preference", "evidence": "编造的原话"}),
])
def test_fabricated_personal_memory_is_not_saved(tmp_path, tool, args):
    a = make_agent(tmp_path)
    chat_tools(a, "你好", (tool, args))
    assert not a.db.exercise_feedback_rows(a.user_id)
    assert not a.db.open_coach_notes(a.user_id)


@pytest.mark.parametrize("consent, review", [("我只想了解，不要记录尝试", 14), ("我想试试", None)])
def test_personal_trial_needs_opt_in_and_a_review_date(tmp_path, consent, review):
    a = make_agent(tmp_path)
    args = {"change_desc": "组间休息缩短30秒", "reason": "节省时间", "observe": "完成率",
            "stop_rule": "完成率下降就停止"}
    if review is not None:
        args["review_days"] = review
    chat_tools(a, consent, ("start_personal_trial", args))
    assert not a.db.personal_trials(a.user_id)


def test_return_to_training_reduces_real_weight_once_and_preserves_review_date():
    from coach.plan import generate_plan, regenerate_plan_preserve
    p = profile()
    old = generate_plan(p)
    for day in old["schedule"]:
        for ex in day["exercises"]:
            ex["weight_kg"] = 100
    p["experience"]["recent_layoff_weeks"] = 2
    first = regenerate_plan_preserve(p, [], old)
    assert all(ex["weight_kg"] == 70 for d in first["schedule"] for ex in d["exercises"])
    first["return_to_training"]["review_at"] = "2026-10-01"
    again = regenerate_plan_preserve(p, [], first)
    assert all(ex["weight_kg"] == 70 for d in again["schedule"] for ex in d["exercises"])
    assert again["return_to_training"]["review_at"] == "2026-10-01"
    p["experience"]["recent_layoff_weeks"] = 0
    resumed = regenerate_plan_preserve(p, [], again)
    assert not resumed.get("return_to_training")
    assert all(ex["weight_kg"] == 70 for d in resumed["schedule"] for ex in d["exercises"])


def test_new_layoff_blocks_old_plan_and_offers_regeneration(tmp_path):
    a = make_agent(tmp_path)
    chat_tools(a, "停训了两周，准备复训", ("update_profile", {"patch": {
        "experience": {"recent_layoff_weeks": 2}}}))
    assert a.profile.get("plan_fence")
    assert pending(a, "regenerate_plan")
    text = a._handle_tool({"name": "get_plan", "arguments": "{}"}, "normal")
    assert "计划已隔离" in text and "杠铃平板卧推" not in text


def test_return_to_training_cannot_increase_stimulus_before_review(tmp_path):
    from coach.adjust import apply_adjustment, suggest_adjustments
    from coach.plan import generate_plan
    a = make_agent(tmp_path)
    p = profile()
    p["experience"]["recent_layoff_weeks"] = 2
    plan = generate_plan(p)
    with pytest.raises(ValueError, match="复训"):
        apply_adjustment(plan, "increase_weight", "深蹲", "旧数据表现不错", last_weight=100)
    for days, weight in [(5, 50), (1, 60)]:
        row = a.db.add_checkin(a.user_id, "training", {"exercises": [
            {"name": "深蹲", "weight_kg": weight, "reps": 5}]})
        a.db.conn.execute("UPDATE checkins SET created_at=? WHERE id=?",
                          ((datetime.now() - timedelta(days=days)).isoformat(), row))
    a.db.conn.commit()
    assert all(s["action"] not in {"increase_weight", "add_volume"}
               for s in suggest_adjustments(a.db, a.user_id, plan))


def test_repeated_profile_proposal_is_one_confirmable_change(tmp_path):
    a = make_agent(tmp_path)
    for _ in range(2):
        chat_tools(a, "每次改成30分钟", ("update_profile", {"patch": {"resources": {"session_minutes": 30}}}))
    changes = a.profile["pending_profile_changes"]
    assert len(changes) == 1
    chat_tools(a, "确认每次30分钟", ("confirm_profile_change", {"change_id": changes[0]["id"], "accept": True}))
    assert a.profile["resources"]["session_minutes"] == 30


def test_fractional_training_years_cannot_be_confirmed_as_a_different_number(tmp_path):
    a = make_agent(tmp_path)
    chat_tools(a, "训练年限记错了，实际1.5年", ("update_profile", {"patch": {"experience": {"training_years": 1.5}}}))
    entry = a.profile["pending_profile_changes"][0]
    chat_tools(a, "确认，是1年", ("confirm_profile_change", {"change_id": entry["id"], "accept": True}))
    assert a.profile["experience"]["training_years"] == 4


def test_resolving_one_symptom_cannot_close_a_different_mentioned_symptom():
    from coach.confirmation import classify_safety_resolution
    knee = {"flag_id": "knee", "kw": "膝盖刺痛", "status": "open"}
    chest = {"flag_id": "chest", "kw": "胸闷", "status": "open"}
    text = "膝盖现在疼，胸闷已经消失"
    assert classify_safety_resolution(text, knee, [knee, chest]) != "accept"
    assert classify_safety_resolution(text, chest, [knee, chest]) == "accept"


def test_explicit_new_medical_restriction_applies_even_when_llm_only_reads_plan(tmp_path):
    a = make_agent(tmp_path)
    chat_tools(a, "今天医生让我暂停力量训练", ("get_plan", {}))
    plan = a.db.get_active_plan(a.user_id)
    assert plan["schedule"] == [] and plan["medical_status"] != "allowed"
    assert "杠铃平板卧推" not in a._turn_tool_results[-1]


def test_llm_cannot_erase_a_restriction_reported_in_the_same_turn(tmp_path):
    a = make_agent(tmp_path)
    text = "今天医生让我暂停力量训练"
    chat_tools(a, text, ("update_profile", {"patch": {"conditions": {
        "health_screen": {"clearance": "无"}, "health_screen_evidence": text}}}))
    assert a.db.get_active_plan(a.user_id)["schedule"] == []


@pytest.mark.parametrize("text", ["如果医生让我暂停力量训练该怎么办", "我的医生让我注意睡眠", "去年医生让我暂停训练"])
def test_educational_or_historical_doctor_statement_does_not_impose_a_new_restriction(text):
    from coach.medical import reported_current_restriction
    assert reported_current_restriction(text) is None


@pytest.mark.parametrize("reply", ["确认一个半小时", "确认十三次"])
def test_number_substrings_do_not_confirm_different_profile_values(reply):
    from coach.confirmation import change_is_referenced
    change = {"field": "resources.session_minutes", "new": 30} if "小时" in reply else {
        "field": "resources.days_per_week", "new": 3}
    entry = {"id": "c", "changes": [change]}
    assert not change_is_referenced(reply, entry, [entry], "accept")


def test_adjustment_confirmation_for_a_different_exercise_is_rejected():
    from coach.confirmation import adjustment_is_referenced
    suggestion = {"id": "a", "action": "increase_weight", "target": "杠铃卧推"}
    assert not adjustment_is_referenced("确认哑铃卧推加重", suggestion, [suggestion])


def test_malformed_legacy_exercises_do_not_hide_other_review_data(tmp_path):
    a = make_agent(tmp_path)
    a.db.add_checkin(a.user_id, "training", {"exercises": 42})
    a.db.add_checkin(a.user_id, "body", {"weight_kg": -75})
    a.db.add_checkin(a.user_id, "body", {"weight_kg": 75})
    summary = build_summary(a.db, a.user_id, a.db.get_active_plan(a.user_id))
    assert summary["weight_trend"][0][1] == 75


def test_discomfort_and_missing_stress_data_cannot_be_selected_as_a_safe_fallback():
    from coach.exercises import library
    from coach.plan import _hard_exclude
    ex = copy.deepcopy(library.get("barbell_bench_press"))
    assert _hard_exclude(ex, profile(), {ex["id"]: {"discomfort": "肩前侧不适"}}, set(), False)
    ex["joint_stress"] = {}
    assert _hard_exclude(ex, profile(), {}, {"shoulder"}, True)


def test_goal_change_during_medical_pause_retains_the_resumable_plan(tmp_path):
    a = make_agent(tmp_path)
    original = a.db.get_active_plan_record(a.user_id)
    chat_tools(a, "医生让我暂停力量训练")
    chat_tools(a, "我决定把目标改为减脂", ("update_profile", {"patch": {"goal": {"primary": "fat_loss"}}}))
    entry = a.profile["pending_profile_changes"][0]
    chat_tools(a, "确认把目标改为减脂", ("confirm_profile_change", {"change_id": entry["id"], "accept": True}))
    suspended = a.db.get_active_plan(a.user_id)
    assert not suspended["schedule"]
    assert suspended["resume_plan_id"] == original["id"]
    assert suspended["goal_version"] == a.profile["goal"]["version"]
