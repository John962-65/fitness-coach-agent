"""C3 知识讨论闭环（26.3B）＋ C2 收尾（目标补充字段、复盘联动）"""
import tempfile
from pathlib import Path

from coach.agent import CoachAgent
from coach.review import review_context_text


def _agent(uid="s"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


def test_record_discussion_and_inject():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "record_knowledge_discussion",
         "arguments": '{"source": "我看到一个视频说空腹有氧燃脂更多",'
                      ' "topic": "空腹有氧", "verdict": "diverging",'
                      ' "claimed_conditions": "晨起空腹",'
                      ' "followup": "观察两周执行情况"}'}, "auto")
    assert "已记录" in out and "不代表知识被批准" in out
    text = ag._knowledge_discussions_text()
    assert "空腹有氧" in text and "与现有知识有分歧" in text
    assert "私人讨论记录" in text and "建议-确认流程" in text
    assert "观察两周执行情况" in text


def test_invalid_verdict_rejected():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "record_knowledge_discussion",
         "arguments": '{"source": "s", "topic": "t", "verdict": "approved"}'}, "auto")
    assert "未保存" in out
    assert ag.db.open_knowledge_discussions("s") == []


def test_discussions_are_private_per_user():
    a = _agent("a")
    a._handle_tool(
        {"name": "record_knowledge_discussion",
         "arguments": '{"source": "A 的观点", "topic": "T", "verdict": "consistent"}'}, "auto")
    b = _agent("b")
    assert b._knowledge_discussions_text() == "（暂无）"
    assert a._knowledge_discussions_text() != "（暂无）"


def test_close_discussion():
    ag = _agent()
    ag._handle_tool(
        {"name": "record_knowledge_discussion",
         "arguments": '{"source": "s", "topic": "t", "verdict": "consistent"}'}, "auto")
    out = ag._handle_tool(
        {"name": "close_knowledge_discussion", "arguments": '{"item_id": 1}'}, "auto")
    assert "已关闭" in out
    assert ag._knowledge_discussions_text() == "（暂无）"
    out2 = ag._handle_tool(
        {"name": "close_knowledge_discussion", "arguments": '{"item_id": 1}'}, "auto")
    assert "没有找到" in out2


def test_goal_secondary_and_timeline_writable():
    ag = _agent()
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "fat_loss",'
                      ' "secondary": "保留力量", "timeline": "12 周减 4kg"}}}'}, "auto")
    g = ag.profile["goal"]
    assert g["secondary"] == "保留力量" and g["timeline"] == "12 周减 4kg"
    assert not ag.profile.get("pending_profile_changes")   # 首次采集不拦


def test_review_links_goal_version_and_metrics():
    ag = _agent()
    ag.profile["goal"] = {"primary": "muscle_gain", "version": 2,
                          "confirmed_at": "2026-10-11T10:00:00",
                          "evaluation": "力量渐进 + 围度增长 + 体重缓升"}
    ag.db.save_profile("s", ag.profile)
    ag.db.create_plan("s", {"goal_version": 1, "days_per_week": 3,
                            "template": "t", "schedule": [], "notes": []})
    ag.db.add_checkin("s", "training",
                      {"exercises": [{"name": "杠铃深蹲", "weight_kg": 100, "reps": 5}]})
    plan = ag.db.get_active_plan("s")
    text = review_context_text(ag.db, "s", plan)
    assert "当前目标：增肌（目标版本 v2" in text
    assert "力量渐进" in text and "不套用旧目标标准" in text
    assert "生效计划是目标 v1 时生成的" in text and "建议确认重排" in text


def test_discussion_related_card_hint():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "record_knowledge_discussion",
         "arguments": '{"source": "空腹有氧燃脂更多的说法", "topic": "空腹有氧",'
                      ' "verdict": "insufficient_evidence"}'}, "auto")
    assert "已审核教练卡" in out and "不因讨论修改" in out      # 自动比对提示
    row = ag.db.open_knowledge_discussions("s")[0]
    assert row["related_card"] == "card-training-cardio-basics"
    assert "关联已审核卡：card-training-cardio-basics" in ag._knowledge_discussions_text()
    out2 = ag._handle_tool(
        {"name": "record_knowledge_discussion",
         "arguments": '{"source": "自创的一套呼吸法", "topic": "完全冷门的话题",'
                      ' "verdict": "insufficient_evidence"}'}, "auto")
    assert "已审核教练卡" not in out2                          # 无相关卡不硬凑
