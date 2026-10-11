"""C5 离线纵向验收：§27.2 九步连续场景（同一合成用户，断言数据库状态而非措辞）。

对照基线：C0_CAPABILITY_MATRIX_2026-10-11.md 第 2 节（当时 ④⑤⑨ 步"机制缺失"）。
本测试通过即表示九步的机制路径全部可走通；真实 LLM 行为仍需独立验证（不做声称）。
"""
import json
from datetime import datetime, timedelta

from coach.agent import CoachAgent
from coach.plan import generate_plan
from test_repair_regressions import chat_tools, pending

ONBOARD_PATCH = {
    "basic": {"name": "小陈", "age": 28, "gender": "男",
              "height_cm": 175, "weight_kg": 80},
    "experience": {"training_years": 2},
    "goal": {"primary": "fat_loss"},
    "resources": {"location": "gym", "days_per_week": 3, "session_minutes": 60},
    "conditions": {"injuries": [], "injuries_evidence": "没有伤病",
                   "health_screen": {"heart": "无", "pregnancy": "不适用"},
                   "health_screen_evidence": "没有心血管疾病，医生没有限制运动"},
}


def test_nine_step_continuous_scenario(tmp_path):
    a = CoachAgent("chen", db_path=tmp_path / "nine.db")

    # ---- 步骤1：建档 + 减脂目标 + 初始安排 ----
    chat_tools(a, "请建档：28岁男，175cm 80kg，练了2年，目标减脂，健身房每周3练"
                  "每次60分钟。没有伤病，没有心血管疾病，医生没有限制运动。",
               ("update_profile", {"patch": ONBOARD_PATCH}),
               ("finish_onboarding", {}))
    assert a.profile["onboarding_done"] is True
    assert a.profile["goal"]["primary"] == "fat_loss"
    assert a.profile["experience"]["level"]          # G3 定级回写
    plan = a.db.get_active_plan("chen")
    assert plan and plan["schedule"]
    assert plan["goal_version"] == 0                 # 初始计划绑定目标 v0

    # ---- 步骤2：偏好表达 → 记录（不擅自认定伤病），顺便完成一次打卡 ----
    chat_tools(a, "今天卧推 60kg 做了 3 组。另外我不喜欢杠铃卧推，更喜欢哑铃的，但没有疼。",
               ("save_checkin", {"type": "training", "data": {"exercises": [
                   {"name": "杠铃卧推", "weight_kg": 60, "sets": 3, "reps": "8"}]}}),
               ("record_exercise_feedback", {
                   "exercise": "杠铃卧推", "preference": -1,
                   "evidence": "我不喜欢杠铃卧推，更喜欢哑铃的，但没有疼"}))
    st = a.db.get_user_exercise("chen", "barbell_bench_press")
    assert st and st["preference"] == -1 and "不喜欢" in (st["evidence"] or "")
    assert a.profile["conditions"]["pain_flags"] == []      # 没有疼 → 不得写安全记录
    ck = a.db.list_checkins("chen")[0]
    assert ck["revision"] == 0 and ck["data"]["exercises"][0]["weight_kg"] == 60

    # ---- 步骤3：时间变化 3×60 → 2×30（暂存→澄清→确认→重排） ----
    chat_tools(a, "以后每次只有30分钟了",
               ("update_profile", {"patch": {"resources": {"session_minutes": 30}}}))
    assert a.profile["resources"]["session_minutes"] == 60           # 未静默生效
    chg = a.profile["pending_profile_changes"][0]
    chat_tools(a, "确认，以后就按30分钟来",
               ("confirm_profile_change",
                {"change_id": chg["id"], "accept": True}))
    assert a.profile["resources"]["session_minutes"] == 30
    regen = pending(a, "regenerate_plan")
    chat_tools(a, "好，按30分钟重排吧",
               ("apply_adjustment", {"suggestion_id": regen["id"]}))
    plan = a.db.get_active_plan("chen")
    assert all(d.get("estimated_minutes", 0) <= 30 for d in plan["schedule"])
    assert plan["goal_version"] == 0                                 # 目标没变，绑定不变

    # ---- 步骤4：分享训练观点 → 讨论记录，不盲从也不直接改计划 ----
    before_plan = json.dumps(plan, sort_keys=True)
    chat_tools(a, "我看有个视频说空腹有氧燃脂更多，我要不要早上空腹练？",
               ("record_knowledge_discussion", {
                   "source": "我看有个视频说空腹有氧燃脂更多",
                   "topic": "空腹有氧", "verdict": "insufficient_evidence",
                   "relation": "与现有知识有分歧：全天结算下总量优先；且证据不足待核",
                   "followup": "先按当前安排执行两周再看"}))
    assert a._knowledge_discussions_text() != "（暂无）"
    assert json.dumps(a.db.get_active_plan("chen"), sort_keys=True) == before_plan
    assert not a.profile.get("pending_adjustments")                  # 未借讨论改处方

    # ---- 步骤5：转增肌 → 协商/预览/确认 → 目标/计划/评价指标一致落库 ----
    n_ck = len(a.db.list_checkins("chen"))
    chat_tools(a, "我想转增肌了",
               ("update_profile", {"patch": {"goal": {"primary": "muscle_gain"}}}))
    assert a.profile["goal"]["primary"] == "fat_loss"                # 未静默生效
    assert a.profile["pending_profile_changes"][0]["changes"][0]["old"] == "fat_loss"
    chg = a.profile["pending_profile_changes"][0]
    chat_tools(a, "对，确认转增肌，保留现在的安排基础",
               ("confirm_profile_change", {"change_id": chg["id"], "accept": True}))
    g = a.profile["goal"]
    assert g["primary"] == "muscle_gain" and g["version"] == 1
    assert "力量渐进" in g["evaluation"]                              # 评价指标同步切换
    assert a.profile["_history"]["goal.primary"]["old"] == "fat_loss"  # 保留来历
    regen = pending(a, "regenerate_plan")
    assert "v1" in regen["reason"]                                    # 版本化重排
    chat_tools(a, "确认按增肌重排",
               ("apply_adjustment", {"suggestion_id": regen["id"]}))
    plan = a.db.get_active_plan("chen")
    assert plan["goal_version"] == 1                                  # 计划绑定新目标版本
    assert len(a.db.list_checkins("chen")) == n_ck                    # 历史不清空

    # ---- 步骤6：停训后复训 → 过渡安排，不按历史最高直接恢复 ----
    chat_tools(a, "过年停了两周没练",
               ("update_profile", {"patch": {"experience": {"recent_layoff_weeks": 2}}}))
    assert a.profile["experience"]["recent_layoff_weeks"] == 2
    a._offer_regenerate("停训 2 周后复训，参考已有能力过渡")
    regen = pending(a, "regenerate_plan")
    chat_tools(a, "好，按复训安排来",
               ("apply_adjustment", {"suggestion_id": regen["id"]}))
    plan = a.db.get_active_plan("chen")
    assert any("70%" in n for n in plan["notes"])                     # 复训 ramp

    # ---- 步骤7：纠正旧打卡 → 修订留痕、派生重算、旧建议作废 ----
    chat_tools(a, "今天卧推 100kg 做了 3 组",
               ("save_checkin", {"type": "training", "data": {"exercises": [
                   {"name": "杠铃卧推", "weight_kg": 100, "sets": 3, "reps": "8"}]}}))
    chat_tools(a, "上次记录错了，卧推是 90kg 不是 100kg",
               ("get_checkins", {}),
               ("correct_checkin", lambda a: {
                   "checkin_id": a.db.list_checkins("chen")[0]["id"],
                   "expected_revision": 0, "exercise_index": 0,
                   "patch": {"weight_kg": 90},
                   "reason": "用户指出重量记错",
                   "evidence": "卧推是 90kg 不是 100kg"}))
    fixed = a.db.get_checkin("chen", a.db.list_checkins("chen")[0]["id"])
    assert fixed["revision"] == 1 and fixed["data"]["exercises"][0]["weight_kg"] == 90

    # ---- 步骤8：疲劳信号 → 降阶建议，不机械追加刺激 ----
    for days, rpe in [(6, 7), (3, 8), (0, 9)]:
        c = a.db.add_checkin("chen", "training", {"exercises": [
            {"name": "硬拉", "weight_kg": 100, "reps": 5, "rpe": rpe}]})
        a.db.conn.execute(
            "UPDATE checkins SET created_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=days)).isoformat(), c))
    a.db.conn.commit()
    chat_tools(a, "最近很累，需要调整吗",
               ("get_adjustment_suggestions", {}))
    actions = [s["action"] for s in a.profile["pending_adjustments"]]
    assert "deload" in actions
    assert "increase_weight" not in actions and "add_volume" not in actions

    # ---- 步骤9：新尝试 → 带依据与不确定性的个人观察，不外推 ----
    chat_tools(a, "我想试试把组间休息从 2 分钟改成 90 秒，两周看效果",
               ("start_personal_trial", {
                   "change_desc": "组间休息 2 分钟改 90 秒",
                   "reason": "用户想缩短单次时长",
                   "observe": "力量表现与每组完成次数",
                   "review_days": 14, "stop_rule": "力量下滑就停止"}))
    chat_tools(a, "两周到了，感觉不错，力量没掉",
               ("end_personal_trial", {"trial_id": 1,
                                       "outcome": "完成率上升，力量持平",
                                       "decision": "keep"}))
    trials = a.db.personal_trials("chen")
    assert trials[0]["status"] == "ended" and "完成率上升" in trials[0]["outcome"]
    assert trials[0]["decision"] == "keep"
    other = CoachAgent("someone_else", db_path=tmp_path / "nine.db")
    assert other._personal_trials_text() == "（暂无）"                 # 个人观察不外推
    assert other._knowledge_discussions_text() == "（暂无）"           # 讨论记录按用户隔离

    # ---- 收尾一致性 ----
    assert not a.profile.get("pending_profile_changes")
    assert a.profile["goal"]["version"] == 1
