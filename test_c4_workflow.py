"""C4 完整教练工作流（26.5 训练前）＋ 有边界的个人尝试（26.3C）"""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from coach.agent import CoachAgent


def _agent(uid="s"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


def _plan(a):
    a.db.create_plan(a.user_id, {"days_per_week": 3, "template": "三分化推拉蹲",
                                 "schedule": [{"day": "周一", "focus": "推"},
                                              {"day": "周三", "focus": "拉"},
                                              {"day": "周五", "focus": "蹲"}],
                                 "notes": []})


def test_pre_training_brief_blocks_open_safety_flags():
    ag = _agent()
    ag.profile["conditions"]["pain_flags"] = [
        {"flag_id": "flag-x", "kw": "肩膀疼", "status": "open", "at": "2026-10-10"}]
    ag.db.save_profile("s", ag.profile)
    _plan(ag)
    out = ag._handle_tool({"name": "get_pre_training_brief", "arguments": "{}"}, "auto")
    assert "训练前简报" in out
    assert "flag-x" in out and "肩膀疼" in out and "先确认对应安全事件近况" in out
    assert "训练安排" in out
    assert "本周计划" not in out and "周一 推" not in out


def test_pre_training_brief_medical_pause_first():
    ag = _agent()
    ag.profile["onboarding_done"] = True
    ag.profile["conditions"]["health_screen"] = {
        "heart": "冠心病", "clearance": "医生禁止高强度运动"}
    ag.db.save_profile("s", ag.profile)
    out = ag._handle_tool({"name": "get_pre_training_brief", "arguments": "{}"}, "auto")
    assert "训练处方已暂停" in out and "不安排训练" in out
    assert "本周计划" not in out


def test_pre_training_brief_hides_fenced_plan_schedule():
    ag = _agent()
    ag.profile["onboarding_done"] = True
    ag.db.save_profile(ag.user_id, ag.profile)
    _plan(ag)

    ag.chat("我训练时胸闷")

    brief = ag._handle_tool({"name": "get_pre_training_brief", "arguments": "{}"}, "auto")
    assert "当前计划已隔离" in brief
    assert "确认处理前不提供训练安排" in brief
    assert "本周计划" not in brief
    assert "周一 推" not in brief


def test_trial_lifecycle_single_factor_rule():
    ag = _agent()
    ag.db.add_message("s", "user", "我想试试把卧推组间休息从2分钟改成90秒，两周后复盘")
    out1 = ag._handle_tool(
        {"name": "start_personal_trial",
         "arguments": '{"change_desc": "把卧推组间休息从 2 分钟改 90 秒",'
                      ' "reason": "用户想缩短总时长", "observe": "力量表现与完成率",'
                      ' "review_days": 14, "stop_rule": "连续两次表现下滑就停止"}'}, "auto")
    assert "已登记" in out1 and "个人观察" in out1
    out2 = ag._handle_tool(
        {"name": "start_personal_trial",
         "arguments": '{"change_desc": "同时把蛋白质加到 2g/kg", "reason": "r",'
                      ' "observe": "o", "stop_rule": "s", "review_days": 14}'}, "auto")
    assert "每次只改一个因素" in out2 and "先结束" in out2
    assert "进行中" in ag._personal_trials_text()
    out3 = ag._handle_tool(
        {"name": "end_personal_trial",
         "arguments": '{"trial_id": 1, "outcome": "完成率提升，力量持平",'
                      ' "decision": "keep"}'}, "auto")
    assert "已结束" in out3 and "仅适用于本人" in out3
    assert "已完成率提升" in ag._personal_trials_text().replace(" ", "") or \
        "完成率提升" in ag._personal_trials_text()


def test_trial_five_elements_required():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "start_personal_trial",
         "arguments": '{"change_desc": "换个动作", "reason": "r", "observe": "o"}'}, "auto")
    assert "缺一不可" in out and "未保存" in out
    assert ag.db.personal_trials("s") == []


def test_trial_forbidden_content_rejected():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "start_personal_trial",
         "arguments": '{"change_desc": "加一类固醇循环", "reason": "涨得快",'
                      ' "observe": "o", "stop_rule": "s"}'}, "auto")
    assert "不属于可自主尝试的范围" in out
    assert ag.db.personal_trials("s") == []


def test_trial_due_review_flagged():
    ag = _agent()
    ag.db.add_message("s", "user", "我想尝试改成晨练，两周后复盘")
    ag._handle_tool(
        {"name": "start_personal_trial",
         "arguments": '{"change_desc": "晨练改空腹", "reason": "用户时间只有早上",'
                      ' "observe": "训练感受与力量", "review_days": 14,'
                      ' "stop_rule": "力量掉就停"}'}, "auto")
    ag.db.conn.execute("UPDATE personal_trials SET review_at=? WHERE user_id=?",
                       ((datetime.now() - timedelta(days=1)).isoformat(), "s"))
    ag.db.conn.commit()
    text = ag._personal_trials_text()
    assert "复盘时点已到" in text
    brief = ag._handle_tool({"name": "get_pre_training_brief", "arguments": "{}"}, "auto")
    assert "进行中的尝试" in brief and "复盘时点已到" in brief
