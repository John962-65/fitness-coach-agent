"""R2 数据契约测试（设计书 17.2 L1/L3/D1/D2/G1/G2/G3）"""
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from coach.agent import CoachAgent
from coach.db import Database
from coach.exercises import library as exercise_lib
from coach.onboarding import can_finish
from coach.profile import merge_patch
from coach.review import build_summary, review_context_text, strength_trend
from coach.adjust import apply_adjustment, suggest_adjustments
from coach.validate import coerce_checkin, coerce_profile_patch


def ago(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")


def _agent(uid="c"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


# ---------- 动作归一（L1） ----------

def test_alias_exact_and_sub():
    assert exercise_lib.normalize("深蹲")[0] == "barbell_back_squat"
    assert exercise_lib.normalize("杠铃深蹲")[0] == "barbell_back_squat"
    assert exercise_lib.normalize("今天深蹲")[0] == "barbell_back_squat"  # 子串
    assert exercise_lib.normalize("squat")[0] == "barbell_back_squat"


def test_alias_no_collision():
    assert exercise_lib.normalize("罗马尼亚硬拉")[0] == "romanian_deadlift"
    assert exercise_lib.normalize("硬拉")[0] == "deadlift"
    assert exercise_lib.normalize("坐姿划船")[0] == "seated_row"
    assert exercise_lib.normalize("划船")[0] == "barbell_row"


def test_unknown_exercise_returns_none():
    ex_id, official, via = exercise_lib.normalize("坐姿夹胸飞鸟机")
    assert ex_id is None and via == ""


# ---------- 变式保护（2026-09-29：变式动作不静默合并进基础动作） ----------

def test_variant_squat_jump_not_merged():
    """"深蹲跳"不是深蹲：子串命中被变式词否决 → 进待确认队列"""
    ex_id, _, _ = exercise_lib.normalize("深蹲跳")
    assert ex_id is None


def test_variant_sumo_deadlift_not_merged():
    ex_id, _, _ = exercise_lib.normalize("相扑硬拉")
    assert ex_id is None


def test_variant_box_squat_not_merged():
    ex_id, _, _ = exercise_lib.normalize("箱式深蹲")
    assert ex_id is None


def test_variant_single_leg_not_merged():
    ex_id, _, _ = exercise_lib.normalize("单腿硬拉")
    assert ex_id is None


def test_close_grip_bench_still_normalizes():
    """"窄距卧推"子串命中"卧推"被变式词否决后，模糊匹配对上"窄握卧推" ——
    同一动作的不同叫法仍然归一，不进待确认队列"""
    ex_id, official, via = exercise_lib.normalize("窄距卧推")
    assert ex_id == "close_grip_bench_press"


def test_plain_sentence_substring_still_works():
    """日常口语打卡不带变式词，子串归一不受影响"""
    assert exercise_lib.normalize("今天深蹲")[0] == "barbell_back_squat"
    assert exercise_lib.normalize("深蹲80kg")[0] == "barbell_back_squat"


def test_save_checkin_normalizes_name():
    agent = _agent()
    result = agent._handle_tool({"name": "save_checkin", "arguments": json.dumps({
        "type": "training",
        "data": {"exercises": [{"name": "深蹲", "weight_kg": 80, "sets": 5, "reps": 5}]},
    })}, "normal")
    ck = agent.db.list_checkins("c")[0]
    ex = ck["data"]["exercises"][0]
    assert ex["name"] == "杠铃深蹲" and ex["exercise_id"] == "barbell_back_squat"
    assert ex["name_raw"] == "深蹲"


def test_save_checkin_unmatched_goes_to_queue():
    agent = _agent()
    result = agent._handle_tool({"name": "save_checkin", "arguments": json.dumps({
        "type": "training", "data": {"exercises": [{"name": "坐姿夹胸飞鸟机"}]},
    })}, "normal")
    assert "未识别动作" in result and "待补队列" in result
    queue = agent.db.path.parent / "unmatched_exercises.jsonl"
    assert queue.exists()
    entry = json.loads(queue.read_text("utf-8").strip().splitlines()[-1])
    assert entry["raw"] == "坐姿夹胸飞鸟机"
    # 不静默丢弃：按原名落库
    ck = agent.db.list_checkins("c")[0]
    assert ck["data"]["exercises"][0]["name"] == "坐姿夹胸飞鸟机"


# ---------- 打卡校验（D1） ----------

def test_coerce_dirty_training_data():
    data, warnings = coerce_checkin("training", {"exercises": [
        {"name": "杠铃深蹲", "weight_kg": "80kg", "sets": "5", "reps": "5x5"},
        {"name": "卧推", "reps": [8, 8, 6]},
        {"name": "硬拉", "weight_kg": "很重"},
        {"note": "没有名字"},
    ]})
    exs = data["exercises"]
    assert len(exs) == 3  # 没名字的剔除
    assert exs[0]["weight_kg"] == 80.0 and exs[0]["sets"] == 5 and exs[0]["reps"] == 5
    assert exs[1]["reps"] == 8
    assert "weight_kg" not in exs[2]
    assert warnings


def test_coerce_body_weight_string():
    data, _ = coerce_checkin("body", {"weight_kg": "84.5kg"})
    assert data["weight_kg"] == 84.5


# ---------- "斤"按 0.5kg 换算（2026-09-29：中国用户报体重常用斤） ----------

def test_jin_converted_to_kg_body_checkin():
    """"150斤"是 75kg，不是 150kg"""
    data, _ = coerce_checkin("body", {"weight_kg": "150斤"})
    assert data["weight_kg"] == 75.0


def test_jin_converted_to_kg_profile():
    """档案体重/三大项里的"斤"同样换算（否则定级被翻倍）"""
    from coach.validate import coerce_profile_patch
    patch, _ = coerce_profile_patch({"basic": {"weight_kg": "130斤"}})
    assert patch["basic"]["weight_kg"] == 65.0
    patch, _ = coerce_profile_patch({"experience": {"big3": {"squat": "300斤"}}})
    assert patch["experience"]["big3"]["squat"] == 150.0


def test_kg_not_double_converted():
    """"公斤/kg"不触发斤换算"""
    data, _ = coerce_checkin("body", {"weight_kg": "84.5公斤"})
    assert data["weight_kg"] == 84.5


def test_review_survives_dirty_legacy_rows():
    """D1：旧脏数据在库里时复盘不崩（读侧容错）"""
    agent = _agent()
    uid = "c"
    agent.profile["onboarding_done"] = True
    agent.db.create_plan(uid, {"days_per_week": 3, "schedule": [
        {"day": "周一", "focus": "全身", "exercises": [{"name": "杠铃深蹲"}]}]})
    bad_rows = [
        {"exercises": [{"name": "杠铃深蹲", "weight_kg": "80kg", "reps": "5x5"}]},
        {"exercises": [{"name": "杠铃深蹲", "weight_kg": [80], "reps": [5, 5]}]},
        {"exercises": "不是一个列表"},
        {"weight_kg": "84.5kg"},
    ]
    for i, row in enumerate(bad_rows):
        agent.db.conn.execute(
            "INSERT INTO checkins(user_id,type,data,created_at) VALUES(?,?,?,?)",
            (uid, "training" if i < 3 else "body", json.dumps(row), ago(3)))
    agent.db.conn.commit()
    # 不抛异常即为通过；且能算出趋势
    text = review_context_text(agent.db, uid, agent.db.get_active_plan(uid))
    assert "e1RM" in text


# ---------- L1 闭环：口语打卡也能出趋势 ----------

def test_colloquial_checkin_feeds_trend():
    agent = _agent()
    uid = "c"
    agent.db.create_plan(uid, {"days_per_week": 3, "schedule": [
        {"day": "周一", "focus": "全身",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5"}]}]})
    for i, w in enumerate((60, 62.5, 65)):
        agent._handle_tool({"name": "save_checkin", "arguments": json.dumps({
            "type": "training",
            "data": {"exercises": [{"name": "深蹲", "weight_kg": w, "sets": 5, "reps": 5}]},
        })}, "normal")
        agent.db.conn.execute(
            "UPDATE checkins SET created_at=? WHERE user_id=? AND id=?",
            (ago(10 - i * 3), uid, i + 1))
    agent.db.conn.commit()
    trend = strength_trend(agent.db.list_checkins(uid), "杠铃深蹲")
    assert len(trend) == 3 and trend[-1][1] > trend[0][1]
    sugs = suggest_adjustments(agent.db, uid, agent.db.get_active_plan(uid))
    assert any(s["action"] == "increase_weight" for s in sugs)


# ---------- L3：追踪全部主力动作 ----------

def test_summary_tracks_all_main_exercises():
    agent = _agent()
    uid = "c"
    agent.db.create_plan(uid, {"days_per_week": 3, "schedule": [
        {"day": "周一", "focus": "全身A", "exercises": [
            {"name": "杠铃深蹲"}, {"name": "杠铃卧推"}]},
        {"day": "周三", "focus": "全身B", "exercises": [
            {"name": "杠铃深蹲"}, {"name": "站姿推举"}]},
    ]})
    for i, (name, w) in enumerate([("杠铃深蹲", 60), ("杠铃卧推", 40),
                                    ("站姿推举", 25)]):
        agent.db.add_checkin(uid, "training", {"exercises": [
            {"name": name, "weight_kg": w, "sets": 5, "reps": 5}]})
        agent.db.conn.execute(
            "UPDATE checkins SET created_at=? WHERE user_id=?", (ago(5 - i), uid))
    agent.db.conn.commit()
    s = build_summary(agent.db, uid, agent.db.get_active_plan(uid))
    # 官方名归一：计划里的"杠铃卧推"统一为库官方名"杠铃平板卧推"
    assert set(s["strength_trends"]) >= {"杠铃深蹲", "杠铃平板卧推", "站姿推举"}


# ---------- D2/G1：档案把关 ----------

def test_merge_patch_whitelist_blocks_system_fields():
    profile = {"conditions": {"pain_flags": [{"kw": "胸闷", "status": "open"}]}}
    merged, report = merge_patch(profile, {
        "onboarding_done": True,
        "experience": {"level": "advanced", "training_years": 3},
        "conditions": {"pain_flags": []},
    })
    assert "onboarding_done" not in merged
    assert merged["experience"] == {"training_years": 3}  # level 被拒、年限保留
    assert merged["conditions"]["pain_flags"][0]["kw"] == "胸闷"  # 未被清空
    assert "onboarding_done" in report["dropped"]
    assert "experience.level" in report["dropped"]
    assert "conditions.pain_flags" in report["dropped"]


def test_merge_patch_coerces_numbers():
    merged, report = merge_patch({}, {
        "basic": {"age": "28岁"},
        "experience": {"big3": {"squat": "130kg", "bench": "不知道"}},
    })
    assert merged["basic"]["age"] == 28
    assert merged["experience"]["big3"]["squat"] == 130.0
    assert "bench" not in merged["experience"]["big3"]
    assert report["warnings"]


def test_merge_patch_unknown_section_dropped():
    merged, report = merge_patch({}, {"hacked": {"x": 1}})
    assert "hacked" not in merged and "hacked" in report["dropped"]


# ---------- G2：伤病史/健康筛查须用户原话 ----------

def _finishable_profile():
    return {
        "basic": {"age": 28, "gender": "男", "height_cm": 178, "weight_kg": 85},
        "goal": {"primary": "fat_loss"},
        "resources": {"days_per_week": 3},
        "conditions": {
            "injuries": [], "injuries_collected": True,
            "injuries_evidence": "我没有任何伤病",
            "health_screen": {"heart": "无"}, "health_screen_collected": True,
            "health_screen_evidence": "身体都正常",
        },
    }


def test_can_finish_requires_evidence():
    p = _finishable_profile()
    ok, _ = can_finish(p)
    assert ok
    p2 = _finishable_profile()
    p2["conditions"]["injuries_evidence"] = ""
    ok, why = can_finish(p2)
    assert not ok and "原话" in why
    p3 = _finishable_profile()
    p3["conditions"]["health_screen_evidence"] = "  "
    ok, why = can_finish(p3)
    assert not ok and "原话" in why


# ---------- G3：定级回写 ----------

def test_level_written_back_on_finish():
    agent = _agent()
    for msg in ("你好", "男，28岁，178cm，85kg", "我想减脂，每周能练3天",
                "我没有任何伤病"):
        agent.chat(msg)
    assert agent.profile["onboarding_done"] is True
    assert agent.profile["experience"]["level"] == "beginner"
    from coach.profile import profile_summary
    assert "水平：beginner" in profile_summary(agent.profile)


# ---------- apply_adjustment 未命中报错 ----------

def test_apply_adjustment_alias_target():
    plan = {"days_per_week": 2, "schedule": [
        {"day": "周一", "focus": "全身",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5", "note": ""}]}]}
    new = apply_adjustment(plan, "add_volume", "深蹲", "别名也认")
    assert new["schedule"][0]["exercises"][0]["sets"] == 7


def test_apply_adjustment_unknown_target_raises():
    plan = {"days_per_week": 2, "schedule": [
        {"day": "周一", "focus": "全身",
         "exercises": [{"name": "杠铃深蹲", "sets": 5, "reps": "5"}]}]}
    with pytest.raises(ValueError, match="找不到目标动作"):
        apply_adjustment(plan, "increase_weight", "坐姿夹胸", "x")
