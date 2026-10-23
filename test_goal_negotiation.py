"""C2 目标协商：提案预览、支持范围护栏、目标/计划/评价指标一致落库与版本绑定（26.4）"""
import tempfile
from pathlib import Path

from coach.agent import CoachAgent
from coach.goals import goal_transition_preview
from coach.plan import generate_plan


def _agent(uid="s"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


def test_preview_structure():
    p = goal_transition_preview("fat_loss", "muscle_gain")
    assert "减脂 → 增肌" in p
    assert "训练侧重" in p and "营养侧重" in p and "评价指标" in p
    assert "保留与过渡" in p and "不清空历史" in p
    assert "体重不再下降不再默认当失败" in p
    p2 = goal_transition_preview("muscle_gain", "fat_loss")
    assert "体重开始下降是预期结果" in p2


def test_unsupported_goal_rejected_not_disguised():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    out = ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "running"}}}'}, "auto")
    assert "暂不在支持范围" in out and "能力边界" in out
    assert ag.profile["goal"]["primary"] == "fat_loss"          # 未被换名接收
    assert not ag.profile.get("pending_profile_changes")


def test_hold_includes_transition_preview():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    out = ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    assert "目标变更预览" in out and "评价指标" in out and "不清空历史" in out
    assert "需确认" in out                                       # 仍走确认流


def test_confirm_binds_version_and_evaluation():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag.profile["onboarding_done"] = True
    ag.db.create_plan("s", {"days_per_week": 3, "template": "t", "schedule": [], "notes": []})
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    entry = ag.profile["pending_profile_changes"][0]
    ag.db.add_message("s", "user", "确认转增肌")  # 模拟下一轮（跨轮强制）
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": f'{{"change_id": "{entry["id"]}", "accept": true}}'}, "auto")
    g = ag.profile["goal"]
    assert g["primary"] == "muscle_gain"
    assert g["version"] == 1                                     # 版本绑定
    assert "力量渐进" in g["evaluation"]                          # 评价指标一致切换
    assert g["confirmed_at"]
    # DESIGN 26.4⑤：确认后计划与目标一起生效，不留下旧目标的现役计划。
    assert "v1" in out and "重排" in out
    assert not ag.profile["pending_adjustments"]
    assert ag.db.get_active_plan("s")["goal_version"] == 1


def test_plan_stamped_with_goal_version():
    base = {"experience": {"training_years": 2, "level": "intermediate"},
            "resources": {"location": "gym", "days_per_week": 3, "session_minutes": 60},
            "goal": {"primary": "muscle_gain", "version": 2},
            "conditions": {}}
    assert generate_plan(base)["goal_version"] == 2
    base["goal"] = {"primary": "fat_loss"}                       # 无版本 → 初始 0
    assert generate_plan(base)["goal_version"] == 0


def test_selected_draft_actions_disclosed_in_notes():
    """决策项 2 选 B：无伤病处方域不锁 approved，但选中的 draft 动作必须明示。"""
    from coach.exercises import library
    draft_ids = [e["id"] for e in library.all() if e.get("status") != "approved"]
    assert draft_ids, "库内应有 draft 动作"
    # 用一个必然落在 draft 动作上的槽位直测：组装含 draft 动作的计划并断言备注
    profile = {"experience": {"training_years": 3, "level": "intermediate"},
               "resources": {"location": "home", "days_per_week": 3, "session_minutes": 60},
               "goal": {"primary": "muscle_gain", "version": 1},
               "conditions": {}}
    plan = generate_plan(profile)
    selected = {ex["name"] for day in plan["schedule"] for ex in day["exercises"]}
    lib_names = {e["name"]: e.get("status") for e in library.all()}
    draft_names = {n for n in selected if lib_names.get(n) != "approved"}
    note = next((n for n in plan["notes"] if "尚未经审核" in n), None)
    assert note is not None, f"draft 动作 {draft_names} 未被披露"
    for n in draft_names:
        assert n in note
