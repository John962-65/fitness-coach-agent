"""第24章交付回归：审核、预算、个性化、纠错；不联网、不读取真实用户数据。"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import yaml

from coach.budget import BudgetExceeded, RequestBudget
from coach.claim_review import content_fingerprint, is_publishable, record_review
from coach.claims import ClaimStore
from coach.adjust import apply_adjustment, suggest_adjustments
from coach.plan import generate_plan, regenerate_plan_preserve
from coach.programming import estimate_minutes
from coach.review import strength_trend
from test_repair_regressions import chat_tools, make_agent, pending, profile


def claim():
    return {"id": "tcy-test", "blogger": "谭成义", "speaker": "谭成义", "video": "BV128bX6eExV",
            "ts": [1, 3], "claim": "合成的测试素材，非真实训练建议", "type": "cue",
            "exercises": ["barbell_back_squat"], "provenance": "transcript", "status": "draft"}


def approve(c):
    record_review(c, "source", "测试审核员", "合成来源验证")
    record_review(c, "applicability", "测试审核员", "合成适用性验证")


def test_two_review_stages_and_content_invalidation():
    c = claim()
    c["status"] = "approved"
    assert not is_publishable(c)
    record_review(c, "source", "测试审核员", "来源对照")
    assert not is_publishable(c)
    record_review(c, "applicability", "测试审核员", "适用性对照")
    assert is_publishable(c)
    before = content_fingerprint(c)
    c["claim"] = "修改后的表述"
    assert content_fingerprint(c) != before and not is_publishable(c)


@pytest.mark.parametrize("speaker", ["", "待确认", "凯圣王（语境归因）"])
def test_unconfirmed_speaker_cannot_be_approved(speaker):
    c = claim()
    c["speaker"] = speaker
    with pytest.raises(ValueError, match="发言者"):
        record_review(c, "source", "测试审核员", "来源对照")


def test_runtime_hides_changed_or_unreviewed_claims(tmp_path):
    c = claim()
    approve(c)
    c["claim"] = "未经重新审核的变更"
    (tmp_path / "tcy.yaml").write_text(yaml.safe_dump([c], allow_unicode=True))
    store = ClaimStore(tmp_path)
    assert "未经重新审核" not in store.format_coaching({"cues": [c["id"]]})


def test_review_apply_removes_revoked_reference(tmp_path, monkeypatch):
    import tools.review_ui as ui
    (tmp_path / "claims").mkdir()
    (tmp_path / "exercises").mkdir()
    c = claim()
    approve(c)
    (tmp_path / "claims" / "tcy.yaml").write_text(yaml.safe_dump([c]))
    path = tmp_path / "exercises" / "barbell_back_squat.yaml"
    path.write_text(yaml.safe_dump({"id": "barbell_back_squat", "cues": ["ksw-other"]}))
    monkeypatch.setattr(ui, "ROOT", tmp_path)
    monkeypatch.setattr(ui, "CLAIMS", tmp_path / "claims")
    ui.apply_to_exercises("tcy")
    assert yaml.safe_load(path.read_text())["cues"] == ["ksw-other", c["id"]]
    c["status"] = "rejected"
    (tmp_path / "claims" / "tcy.yaml").write_text(yaml.safe_dump([c]))
    ui.apply_to_exercises("tcy")
    assert yaml.safe_load(path.read_text())["cues"] == ["ksw-other"]


def test_budget_is_shared_and_failure_consumes_attempt(tmp_path):
    path = tmp_path / "ledger.json"
    a, b = RequestBudget(path, 2), RequestBudget(path, 2)
    first = a.reserve()
    a.finish(first, failed=True)
    b.finish(b.reserve(), usage={"total_tokens": 123, "secret": "not-to-store"})
    with pytest.raises(BudgetExceeded):
        a.reserve()
    assert a.snapshot() == {"limit": 2, "used": 2, "remaining": 0, "failed": 1, "total_tokens": 123}
    assert "not-to-store" not in path.read_text()
    with pytest.raises(ValueError):
        RequestBudget(path, 3)


def test_budget_concurrent_reservations_never_exceed_limit(tmp_path):
    path = tmp_path / "ledger.json"
    RequestBudget(path, 3)
    def attempt(_):
        try:
            return RequestBudget(path, 3).reserve()
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        tickets = [r for r in pool.map(attempt, range(12)) if r is not None]
    assert sorted(tickets) == [1, 2, 3]


def test_llm_counter_wraps_actual_request_and_disables_retries(tmp_path, monkeypatch):
    from coach.llm import LLMClient
    import openai
    captured, calls = {}, []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 5}),
                               choices=[SimpleNamespace(message=SimpleNamespace(content="测试", tool_calls=[]))])
    def constructor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(openai, "OpenAI", constructor)
    monkeypatch.setenv("FAKE_LLM", "0")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-value")
    monkeypatch.setenv("LLM_BUDGET_PATH", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("LLM_MAX_REQUESTS", "1")
    client = LLMClient()
    client.chat([{"role": "user", "content": "合成测试"}])
    with pytest.raises(BudgetExceeded):
        client.chat([{"role": "user", "content": "不会发送"}])
    assert len(calls) == 1 and captured["max_retries"] == 0


def test_time_budget_changes_actual_prescription():
    p = profile()
    long = generate_plan(p)
    p["resources"]["session_minutes"] = 30
    short = generate_plan(p)
    assert short != long
    assert all(d["estimated_minutes"] <= 30 for d in short["schedule"])
    assert sum(e["sets"] for d in short["schedule"] for e in d["exercises"]) < sum(
        e["sets"] for d in long["schedule"] for e in d["exercises"])


def test_preference_without_pain_changes_default():
    p = profile()
    states = [{"exercise_id": "barbell_bench_press", "preference": -2},
              {"exercise_id": "dumbbell_bench_press", "preference": 2}]
    plan = generate_plan(p, states)
    assert plan["schedule"][0]["exercises"][0]["exercise_id"] == "dumbbell_bench_press"
    assert generate_plan(p, states) == plan


def test_regeneration_keeps_prior_frequency_and_sets():
    p = profile()
    old = generate_plan(p)
    old = apply_adjustment(old, "add_volume", "深蹲", "之前确认加量")
    old = apply_adjustment(old, "reduce_frequency", "计划频率", "时间有限")
    new = regenerate_plan_preserve(p, [{"exercise_id": "barbell_bench_press", "status": "avoid"}], old)
    assert len(new["schedule"]) == len(old["schedule"])
    old_sets = next(e["sets"] for d in old["schedule"] for e in d["exercises"] if e["exercise_id"] == "barbell_back_squat")
    new_sets = next(e["sets"] for d in new["schedule"] for e in d["exercises"] if e["exercise_id"] == "barbell_back_squat")
    assert new_sets == old_sets


def test_session_minutes_update_offers_real_regeneration(tmp_path):
    # C1 收尾（2026-10-11 规格变更）：已有确认值的时长被改写 → 暂存待确认，
    # 澄清并 confirm 后才落库并触发重排（26.2"冲突先澄清"，26.4 一致落库）。
    a = make_agent(tmp_path)
    chat_tools(a, "每次只有30分钟", ("update_profile", {"patch": {"resources": {"session_minutes": 30}}}))
    assert a.profile["resources"]["session_minutes"] == 60          # 未静默生效
    change = next(c for c in a.profile["pending_profile_changes"]
                  if any(h["field"] == "resources.session_minutes" for h in c["changes"]))
    chat_tools(a, "确认，以后每次按30分钟来",
               ("confirm_profile_change", {"change_id": change["id"], "accept": True}))
    assert a.profile["resources"]["session_minutes"] == 30
    assert a.profile["_history"]["resources.session_minutes"]["old"] == 60
    sid = pending(a, "regenerate_plan")["id"]
    chat_tools(a, "确认按30分钟重排", ("apply_adjustment", {"suggestion_id": sid}))
    assert all(d["estimated_minutes"] <= 30 for d in a.db.get_active_plan(a.user_id)["schedule"])


def test_fatigue_signal_never_also_increases_stimulus(tmp_path):
    a = make_agent(tmp_path)
    for days, rpe in [(6, 7), (3, 8), (0, 9)]:
        ck = a.db.add_checkin(a.user_id, "training", {"exercises": [{"name": "硬拉", "weight_kg": 100, "reps": 5, "rpe": rpe}]})
        a.db.conn.execute("UPDATE checkins SET created_at=? WHERE id=?", ((datetime.now()-timedelta(days=days)).isoformat(), ck))
    a.db.conn.commit()
    suggestions = suggest_adjustments(a.db, a.user_id, a.db.get_active_plan(a.user_id))
    assert any(s["action"] == "deload" for s in suggestions)
    assert not any(s["action"] in ("increase_weight", "add_volume") for s in suggestions)


def test_discomfort_can_be_cleared_without_erasing_preference(tmp_path):
    a = make_agent(tmp_path)
    a.db.record_exercise_feedback(a.user_id, "barbell_bench_press", preference=1, discomfort="旧不适", evidence="原话")
    a.db.record_exercise_feedback(a.user_id, "barbell_bench_press", discomfort="", evidence="现在没有这个不适")
    state = a.db.get_user_exercise(a.user_id, "barbell_bench_press")
    assert state["discomfort"] == "" and state["preference"] == 1


def test_correction_recomputes_best_and_keeps_history(tmp_path):
    a = make_agent(tmp_path)
    a.db.record_exercise_feedback(a.user_id, "barbell_back_squat", preference=2, evidence="喜欢")
    chat_tools(a, "深蹲160kg做5次", ("save_checkin", {"type": "training", "data": {
        "exercises": [{"name": "深蹲", "weight_kg": 160, "reps": 5}]}}))
    row = a.db.list_checkins(a.user_id)[0]
    a.profile["pending_adjustments"] = [{"id": "stale"}]
    a.db.save_profile(a.user_id, a.profile)
    chat_tools(a, "记错了，深蹲实际60kg", ("correct_checkin", {"checkin_id": row["id"],
        "expected_revision": 0, "exercise_index": 0, "patch": {"weight_kg": 60},
        "reason": "重量记错", "evidence": "记错了，深蹲实际60kg"}))
    revised = a.db.get_checkin(a.user_id, row["id"])
    assert revised["revision"] == 1 and revised["at"] == row["at"]
    state = a.db.get_user_exercise(a.user_id, "barbell_back_squat")
    assert state["best_e1rm"] == 70 and state["last_weight"] == 60 and state["preference"] == 2
    assert a.profile["pending_adjustments"] == []
    history = a.db.conn.execute("SELECT old_data FROM checkin_revisions").fetchone()[0]
    assert json.loads(history)["exercises"][0]["weight_kg"] == 160
    assert len(a.db.list_checkins(a.user_id)) == 1
    assert strength_trend(a.db.list_checkins(a.user_id), "深蹲")[0][1] == 70


def test_correction_rejects_foreign_user_and_stale_revision(tmp_path):
    a = make_agent(tmp_path)
    ck = a.db.add_checkin(a.user_id, "body", {"weight_kg": 80})
    with pytest.raises(ValueError, match="不存在"):
        a.db.revise_checkin("other", ck, 0, {"weight_kg": 60}, "原因", "原话")
    a.db.revise_checkin(a.user_id, ck, 0, {"weight_kg": 60}, "原因", "原话")
    with pytest.raises(ValueError, match="已被修订"):
        a.db.revise_checkin(a.user_id, ck, 0, {"weight_kg": 70}, "原因", "原话")


def test_correcting_action_rebuilds_both_old_and_new_state(tmp_path):
    a = make_agent(tmp_path)
    ck = a.db.add_checkin(a.user_id, "training", {"exercises": [{"name": "深蹲", "exercise_id": "barbell_back_squat", "weight_kg": 80, "reps": 5}]})
    a.db.update_exercise_state(a.user_id, "barbell_back_squat", 80, 7, 93.3)
    a.db.revise_checkin(a.user_id, ck, 0, {"exercises": [{"name": "硬拉", "exercise_id": "deadlift", "weight_kg": 80, "reps": 5}]}, "动作名错了", "用户原话")
    assert a.db.get_user_exercise(a.user_id, "barbell_back_squat")["best_e1rm"] is None
    assert a.db.get_user_exercise(a.user_id, "deadlift")["best_e1rm"] == 93.3


def test_volume_adjustment_cannot_break_time_budget():
    plan = {"time_budget_minutes": 15, "medical_status": "allowed", "schedule": [{
        "exercises": [{"name": "杠铃深蹲", "exercise_id": "barbell_back_squat",
                       "role": "main", "sets": 2, "reps": "5"}]}]}
    assert estimate_minutes(plan["schedule"][0]["exercises"]) <= 15
    with pytest.raises(ValueError, match="时间预算"):
        apply_adjustment(plan, "add_volume", "深蹲", "测试")
    assert plan["schedule"][0]["exercises"][0]["sets"] == 2


def test_correction_rolls_back_revision_and_data_on_failure(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    ck = a.db.add_checkin(a.user_id, "body", {"weight_kg": 80})
    original = a.db.get_checkin(a.user_id, ck)
    def fail(*args):
        raise RuntimeError("模拟重算失败")
    monkeypatch.setattr(a.db, "_recompute_exercise_states", fail)
    with pytest.raises(RuntimeError):
        a.db.revise_checkin(a.user_id, ck, 0, {"weight_kg": 60}, "原因", "依据")
    assert a.db.get_checkin(a.user_id, ck) == original
    assert a.db.conn.execute("SELECT COUNT(*) FROM checkin_revisions").fetchone()[0] == 0


def test_correction_requires_actual_user_quote(tmp_path):
    a = make_agent(tmp_path)
    ck = a.db.add_checkin(a.user_id, "body", {"weight_kg": 80})
    chat_tools(a, "查看记录", ("correct_checkin", {"checkin_id": ck, "expected_revision": 0,
        "patch": {"weight_kg": 60}, "reason": "错误", "evidence": "不是本轮用户的话"}))
    assert a.db.get_checkin(a.user_id, ck)["data"]["weight_kg"] == 80
    assert "打卡未修改" in a._turn_tool_results[-1]


def test_runner_does_not_mutate_loaded_expectations(tmp_path, monkeypatch):
    import eval.runner as runner
    a = make_agent(tmp_path)
    a.chat = lambda text: "离线回复"
    monkeypatch.setattr(runner, "CoachAgent", lambda **kwargs: a)
    definition = {"id": "test", "turns": [{"say": "你好", "expect": {"no_tools_crash": True}}]}
    before = copy.deepcopy(definition)
    assert runner.run_persona(definition, tmp_path)["ok"]
    assert definition == before


def test_runner_records_setup_failure_as_incomplete(tmp_path, monkeypatch):
    import eval.runner as runner
    def fail(**kwargs):
        raise ValueError("不可用配置")
    monkeypatch.setattr(runner, "CoachAgent", fail)
    result = runner.run_persona({"id": "test", "turns": []}, tmp_path)
    assert not result["ok"] and result["incomplete"] and result["stop_reason"] == "setup_failed"


def test_review_packet_reuses_existing_p1_selection(tmp_path):
    from tools.prepare_review import make_packet
    from tools.p1_backlog import _template_defaults
    report = make_packet(tmp_path)
    assert [a["id"] for a in report["actions"]] == [eid for eid, _ in _template_defaults()[:12]]
    assert report["status"] == "awaiting_human_review"
    assert report["missing"]["chenshi_source"]


def test_empty_trial_does_not_become_completed(tmp_path):
    from tools.trial_status import build_status
    report = build_status(tmp_path, acceptance={"mode": "fake", "status": "passed"}, trial={"entries": []})
    assert report["trial"]["recorded_days"] == 0
    assert report["overall"] == "not_fully_accepted"
    assert report["acceptance"]["mode"] == "fake"
