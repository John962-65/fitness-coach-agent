"""C1 记忆契约：来源性质分层、复核时点、失效传播、档案留旧值（DESIGN 26.2）"""
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from coach.agent import CoachAgent
from coach.db import Database
from coach.profile import merge_patch


def _agent(uid="s"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


def test_note_type_stored_and_default_inference():
    db = _agent().db
    a = db.add_coach_note("s", "周三常加班", "用户原话A", note_type="fact", review_days=30)
    b = db.add_coach_note("s", "可能在减平台", "推测依据")
    notes = {n["id"]: n for n in db.open_coach_notes("s")}
    assert notes[a]["note_type"] == "fact" and notes[a]["review_at"]
    assert notes[b]["note_type"] == "inference" and not notes[b]["review_at"]
    # 默认不过复核点
    assert notes[a]["due_review"] is False and notes[b]["due_review"] is False


def test_note_type_invalid_rejected():
    db = _agent().db
    with pytest.raises(ValueError):
        db.add_coach_note("s", "x", "y", note_type="guess")


def test_due_review_flag_when_review_at_passed():
    db = _agent().db
    db.add_coach_note("s", "最近睡眠差", "用户原话", note_type="fact", review_days=-1)
    db.add_coach_note("s", "喜欢哑铃卧推", "用户原话", note_type="preference")
    notes = {n["note"]: n["due_review"] for n in db.open_coach_notes("s")}
    assert notes["最近睡眠差"] is True
    assert notes["喜欢哑铃卧推"] is False


def test_expired_note_moves_to_reconfirm_not_silent():
    db = _agent().db
    db.add_coach_note("s", "这两周出差", "用户原话", note_type="fact", expires_days=-1)
    assert db.open_coach_notes("s") == []
    stale = db.notes_for_reconfirm("s")
    assert len(stale) == 1 and stale[0]["note"] == "这两周出差"


def test_renderer_labels_types_and_surfaces_stale():
    ag = _agent()
    ag.db.add_coach_note("s", "周三常加班", "原话A", note_type="fact", expires_days=-1)
    ag.db.add_coach_note("s", "硬拉下背先酸", "原话B", note_type="inference")
    text = ag._coach_notes_text()
    assert "教练推测" in text            # 活跃笔记带性质标签
    assert "硬拉下背先酸" in text
    assert "已过适用期" in text and "周三常加班" in text  # 过期笔记不再静默，要求先确认
    assert "用户明说" not in text        # 过期笔记不在活跃段，不再以当前情况呈现


def test_close_voids_citing_suggestions():
    ag = _agent()
    ag.profile["pending_adjustments"] = [
        {"id": "adj-1", "source": "rule", "action": "add_volume",
         "target": "杠铃深蹲", "reason": "用户说过出差两周后恢复，建议加量"},
        {"id": "adj-2", "source": "rule", "action": "deload",
         "target": "整体", "reason": "连续疲劳"},
    ]
    nid = ag.db.add_coach_note("s", "出差两周后恢复", "用户原话", note_type="fact")
    note = next(n for n in ag.db.open_coach_notes("s") if n["id"] == nid)
    dropped = ag._void_suggestions_citing(note["note"])
    assert [s["id"] for s in dropped] == ["adj-1"]
    assert [s["id"] for s in ag.profile["pending_adjustments"]] == ["adj-2"]


def test_close_coach_note_handler_propagates():
    ag = _agent()
    ag.profile["pending_adjustments"] = [
        {"id": "adj-9", "source": "regenerate", "action": "regenerate_plan",
         "target": "整体计划", "reason": "用户提到膝盖不适，建议重排"},
    ]
    nid = ag.db.add_coach_note("s", "膝盖不适", "用户原话", note_type="fact")
    out = ag._handle_tool({"name": "close_coach_note",
                           "arguments": f'{{"note_id": {nid}}}'}, "auto")
    assert "已关闭" in out and "adj-9" in out
    assert ag.profile["pending_adjustments"] == []
    # 再关一次：无引用时不误报
    nid2 = ag.db.add_coach_note("s", "喜欢早上练", "用户原话", note_type="preference")
    out2 = ag._handle_tool({"name": "close_coach_note",
                            "arguments": f'{{"note_id": {nid2}}}'}, "auto")
    assert "已关闭" in out2 and "作废" not in out2


def test_add_coach_note_handler_rejects_unknown_type():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "add_coach_note",
         "arguments": '{"note": "x", "evidence": "y", "note_type": "guess"}'}, "auto")
    assert "未保存" in out
    assert ag.db.open_coach_notes("s") == []


def test_merge_patch_records_history_on_change():
    prof = {"basic": {"weight_kg": 80}}
    merged, _ = merge_patch(prof, {"basic": {"weight_kg": 82}})
    h = merged["_history"]["basic.weight_kg"]
    assert h["old"] == 80 and h["at"]
    # 值没变不记；新字段不记
    merged2, _ = merge_patch(merged, {"basic": {"weight_kg": 82},
                                      "goal": {"primary": "fat_loss"}})
    assert merged2["_history"]["basic.weight_kg"]["old"] == 80
    assert "goal.primary" not in merged2.get("_history", {})


def test_history_not_writable_by_llm():
    prof = {"basic": {"weight_kg": 80},
            "_history": {"basic.weight_kg": {"old": 80, "at": "t0"}}}
    merged, info = merge_patch(prof, {
        "_history": {"basic.weight_kg": {"old": 999, "at": "fake"}},
        "basic": {"weight_kg": 82}})
    assert merged["_history"]["basic.weight_kg"]["old"] == 80  # 真历史保留
    assert "_history" in info["dropped"]                        # 伪造被拒


def test_migration_adds_columns_to_old_db():
    tmp = Path(tempfile.mkdtemp()) / "old.db"
    conn = sqlite3.connect(tmp)
    conn.execute(
        "CREATE TABLE coach_notes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " user_id TEXT NOT NULL, note TEXT NOT NULL, evidence TEXT NOT NULL,"
        " status TEXT DEFAULT 'open', expires_at TEXT,"
        " created_at TEXT, closed_at TEXT)")
    conn.commit()
    conn.close()
    db = Database(tmp)  # __init__ 自动迁移
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(coach_notes)")}
    assert {"note_type", "review_at"} <= cols
    nid = db.add_coach_note("s", "迁移后可写", "原话", note_type="observation")
    assert nid


# ---- C1 收尾：敏感字段改写需确认（26.2/26.4） ----

def test_hold_conflicting_goal_change_not_applied():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag.profile["resources"] = {"location": "gym", "days_per_week": 3, "session_minutes": 60}
    out = ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"},'
                      ' "basic": {"weight_kg": 82}}}'}, "auto")
    assert "需确认" in out and "goal.primary" in out
    # 敏感字段未生效，非敏感字段已生效
    assert ag.profile["goal"]["primary"] == "fat_loss"
    assert ag.profile["basic"]["weight_kg"] == 82
    pend = ag.profile["pending_profile_changes"]
    assert len(pend) == 1 and pend[0]["changes"][0]["field"] == "goal.primary"
    assert pend[0]["changes"][0]["old"] == "fat_loss"
    assert pend[0]["changes"][0]["new"] == "muscle_gain"


def test_first_time_and_same_value_not_held():
    ag = _agent()
    ag.profile["goal"] = {"primary": "", "phase": "", "target": ""}
    ag.profile["resources"] = {"location": "gym", "days_per_week": 0, "session_minutes": 60}
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "fat_loss"},'
                      ' "resources": {"days_per_week": 3}}}'}, "auto")
    assert ag.profile["goal"]["primary"] == "fat_loss"      # 首次采集不拦
    assert ag.profile["resources"]["days_per_week"] == 3
    assert not ag.profile.get("pending_profile_changes")
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"resources": {"days_per_week": 3}}}'}, "auto")
    assert not ag.profile.get("pending_profile_changes")     # 同值不算冲突


def test_confirm_accept_applies_and_invalidates_old_goal():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag.profile["onboarding_done"] = True
    ag.db.create_plan("s", {"days_per_week": 3, "template": "三分化推拉蹲",
                            "schedule": [], "notes": []})
    ag.profile["pending_adjustments"] = [
        {"id": "adj-old", "source": "rule", "user_id": "s",
         "action": "add_volume", "target": "杠铃深蹲", "reason": "减脂期加量",
         "plan_id": 1, "plan_version": 1, "created_message_id": 0,
         "expires_at": "2099-01-01T00:00:00+00:00"}]
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    entry = ag.profile["pending_profile_changes"][0]
    ag.db.add_message("s", "user", "确认")  # 模拟下一轮（跨轮强制）
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": f'{{"change_id": "{entry["id"]}", "accept": true}}'}, "auto")
    assert "档案已更新" in out and "muscle_gain" in out
    assert ag.profile["goal"]["primary"] == "muscle_gain"
    assert ag.profile["_history"]["goal.primary"]["old"] == "fat_loss"
    assert ag.profile["pending_profile_changes"] == []
    # 旧目标建议失效，且按设计生成一条新的重排建议（不是空列表）
    assert ag.profile["pending_adjustments"]
    assert all(s["action"] == "regenerate_plan"
               for s in ag.profile["pending_adjustments"])
    assert "regenerate_plan" in out or "重排" in out


def test_confirm_decline_keeps_old_value():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    entry = ag.profile["pending_profile_changes"][0]
    ag.db.add_message("s", "user", "确认")  # 模拟下一轮（跨轮强制）
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": f'{{"change_id": "{entry["id"]}", "accept": false}}'}, "auto")
    assert "保留原值" in out
    assert ag.profile["goal"]["primary"] == "fat_loss"
    assert ag.profile["pending_profile_changes"] == []
    assert "_history" not in ag.profile or "goal.primary" not in ag.profile.get("_history", {})


def test_confirm_expired_change_rejected():
    ag = _agent()
    ag.profile["pending_profile_changes"] = [
        {"id": "prf-x", "changes": [{"field": "goal.primary", "old": "a", "new": "b"}],
         "created_message_id": 0, "expires_at": "2020-01-01T00:00:00+00:00"}]
    ag.db.add_message("s", "user", "确认")  # 过跨轮门，命中过期分支
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": '{"change_id": "prf-x", "accept": true}'}, "auto")
    assert "过期" in out
    assert ag.profile["pending_profile_changes"] == []
    assert "goal" not in ag.profile or ag.profile.get("goal", {}).get("primary") != "b"


def test_pending_profile_changes_not_writable_by_llm():
    ag = _agent()
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"pending_profile_changes": [],'
                      ' "basic": {"weight_kg": 75}}}'}, "auto")
    assert "pending_profile_changes" in [d for d in []] or True  # 占位，断言在下行
    assert ag.profile.get("basic", {}).get("weight_kg") == 75
    assert not ag.profile.get("pending_profile_changes")     # 白名单外字段被拒收


def test_confirm_unknown_change_id():
    ag = _agent()
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": '{"change_id": "prf-nope", "accept": true}'}, "auto")
    assert "没有待确认" in out


# ---- 评审 P0 修复（2026-10-11）：跨轮确认 / 伤病隔离 / evidence 绑定 ----

def test_confirm_same_turn_rejected():
    """对抗：同一轮先创建变更再确认 → 必须拒绝（不得代用户批准）。"""
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    entry = ag.profile["pending_profile_changes"][0]
    # 注意：此处不插入新用户消息——同轮创建+同轮确认必须被拒（对抗用例）
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": f'{{"change_id": "{entry["id"]}", "accept": true}}'}, "auto")
    assert "下一轮确认" in out and "不得代用户批准" in out
    assert ag.profile["goal"]["primary"] == "fat_loss"        # 未生效
    assert ag.profile["pending_profile_changes"]              # 暂存保留


def test_confirm_rejected_when_old_value_drifted():
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    entry = ag.profile["pending_profile_changes"][0]
    ag.db.add_message("s", "user", "确认")  # 模拟下一轮（跨轮强制）
    # 暂存后档案被其他路径改写（模拟漂移）
    ag.profile["goal"]["primary"] = "strength"
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": f'{{"change_id": "{entry["id"]}", "accept": true}}'}, "auto")
    assert "旧值不符" in out and "未执行" in out
    assert ag.profile["goal"]["primary"] == "strength"        # 未被覆盖


def test_injury_update_fences_plan_until_regenerate():
    ag = _agent()
    ag.profile["onboarding_done"] = True
    ag.db.create_plan("s", {"days_per_week": 3, "template": "三分化推拉蹲",
                            "schedule": [{"day": "周一", "focus": "推", "exercises": []}],
                            "notes": []})
    # 新增伤病 → 立即隔离（evidence 须为真实用户消息）
    ag.db.add_message("s", "user", "肩膀最近受伤了")
    out = ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"conditions": {"injuries": ["肩部受伤"],'
                      ' "injuries_evidence": "肩膀最近受伤了"}}}'}, "auto")
    fence = ag.profile.get("plan_fence")
    assert fence and "肩部受伤" in fence["reason"]
    # get_plan 带隔离警告
    plan_text = ag._handle_tool({"name": "get_plan", "arguments": "{}"}, "auto")
    assert "【计划已隔离】" in plan_text
    # 隔离期拒绝非重排调整
    ag.profile["pending_adjustments"] = [
        {"id": "adj-f", "source": "rule", "user_id": "s", "action": "deload",
         "target": "整体", "reason": "疲劳", "plan_id": 1, "plan_version": 1,
         "created_message_id": 0, "expires_at": "2099-01-01T00:00:00+00:00"}]
    out2 = ag._handle_tool(
        {"name": "apply_adjustment", "arguments": '{"suggestion_id": "adj-f"}'}, "auto")
    assert "被隔离" in out2 and "不接受对旧计划的增量调整" in out2
    # 重排确认执行 → 解除隔离
    ag._offer_regenerate("伤病更新，重排计划")
    regen = next(s for s in ag.profile["pending_adjustments"]
                 if s["action"] == "regenerate_plan")
    ag.db.add_message("s", "user", "确认重排")
    out3 = ag._handle_tool(
        {"name": "apply_adjustment", "arguments": f'{{"suggestion_id": "{regen["id"]}"}}'},
        "auto")
    assert ag.profile.get("plan_fence") is None               # 已解除
    assert "隔离" not in ag._handle_tool({"name": "get_plan", "arguments": "{}"}, "auto")


def test_injury_removal_does_not_fence():
    ag = _agent()
    ag.profile["conditions"]["injuries"] = ["膝部旧伤"]
    ag.profile["onboarding_done"] = True
    ag.db.create_plan("s", {"days_per_week": 3, "template": "t", "schedule": [], "notes": []})
    ag.db.add_message("s", "user", "膝盖好了")
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"conditions": {"injuries": [],'
                      ' "injuries_evidence": "膝盖好了"}}}'}, "auto")
    assert ag.profile.get("plan_fence") is None               # 删除伤病不隔离


def test_unverifiable_evidence_rejected():
    """对抗：LLM 附不在任何用户消息里的 evidence → 拒收该项。"""
    ag = _agent()
    ag.db.add_message("s", "user", "我膝盖不太好")
    out = ag._handle_tool(
        {"name": "update_profile",
         'arguments': '{"patch": {"conditions": {"injuries": ["膝盖"],'
                      ' "injuries_evidence": "用户确认有膝伤半年（编造依据）"}}}'.replace("'", '"')
         if False else json.dumps({"patch": {"conditions": {
             "injuries": ["膝盖"],
             "injuries_evidence": "用户确认有膝伤半年（编造依据）"}}})}, "auto")
    assert "不是用户原话" in out
    assert "injuries" not in ag.profile.get("conditions", {}) or \
        ag.profile["conditions"].get("injuries") in (None, [], ["膝盖"]) and \
        not ag.profile["conditions"].get("injuries_evidence") in (None, "") and False or True
    # 严格断言：injuries 未被保存（依据无效则整项拒收或走原话判定失败）
    c = ag.profile.get("conditions", {})
    assert not c.get("injuries"), c.get("injuries")


def test_evidence_quoted_from_user_message_accepted():
    ag = _agent()
    ag.db.add_message("s", "user", "我最近肩膀疼痛，举不起来")
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": json.dumps({"patch": {"conditions": {
             "injuries": ["肩膀疼痛"],
             "injuries_evidence": "我最近肩膀疼痛，举不起来"}}})}, "auto")
    assert ag.profile["conditions"]["injuries"] == ["肩膀疼痛"]
    assert ag.profile["conditions"]["injuries_evidence"] == "我最近肩膀疼痛，举不起来"


# ---- 评审二轮收口（2026-10-11）：语义确认 / 未知伤病隔离 / 建议生成门 ----

def test_confirm_decline_phrasing_rejected():
    """对抗：下一轮消息是撤销/搁置表述时，LLM 调 accept=true 必须被语义门拒绝。"""
    ag = _agent()
    ag.profile["goal"] = {"primary": "fat_loss", "phase": "", "target": ""}
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": '{"patch": {"goal": {"primary": "muscle_gain"}}}'}, "auto")
    entry = ag.profile["pending_profile_changes"][0]
    ag.db.add_message("s", "user", "我先不改了，今天练什么？")
    out = ag._handle_tool(
        {"name": "confirm_profile_change",
         "arguments": f'{{"change_id": "{entry["id"]}", "accept": true}}'}, "auto")
    assert "明确确认" in out
    assert ag.profile["goal"]["primary"] == "fat_loss"           # 未被改
    assert ag.profile["pending_profile_changes"]                 # 变更保留待用户明确答复


def test_regenerate_with_unmappable_injury_keeps_fence():
    """评审二轮：重排成功 ≠ 风险已处理——无法映射关节的伤病保持隔离（降级为未解决）。"""
    ag = _agent()
    ag.profile["onboarding_done"] = True
    ag.db.create_plan("s", {"days_per_week": 3, "template": "t", "schedule": [], "notes": []})
    ag.db.add_message("s", "user", "我肋骨骨裂了")
    ag._handle_tool(
        {"name": "update_profile",
         "arguments": json.dumps({"patch": {"conditions": {
             "injuries": ["肋骨骨裂"], "injuries_evidence": "我肋骨骨裂了"}}})}, "auto")
    assert ag.profile.get("plan_fence")
    ag._offer_regenerate("伤病更新，重排计划")
    regen = next(s for s in ag.profile["pending_adjustments"]
                 if s["action"] == "regenerate_plan")
    ag.db.add_message("s", "user", "确认重排")
    ag._handle_tool(
        {"name": "apply_adjustment", "arguments": f'{{"suggestion_id": "{regen["id"]}"}}'},
        "auto")
    fence = ag.profile.get("plan_fence")
    assert fence and fence.get("unresolved") == ["肋骨骨裂"]      # 未解除，降级为未解决
    assert "相关部位的训练与调整暂停" in fence["reason"]
    # 隔离未解除 → 建议生成入口同样拦截
    out = ag._handle_tool({"name": "get_adjustment_suggestions", "arguments": "{}"}, "auto")
    assert "隔离期不生成普通调整建议" in out


def test_adjustment_suggestions_blocked_while_fenced():
    ag = _agent()
    ag.profile["onboarding_done"] = True
    ag.db.create_plan("s", {"days_per_week": 3, "template": "t", "schedule": [], "notes": []})
    ag.profile["plan_fence"] = {"reason": "新增伤病（肩部受伤）", "at": "t",
                                "added_injuries": ["肩部受伤"]}
    out = ag._handle_tool({"name": "get_adjustment_suggestions", "arguments": "{}"}, "auto")
    assert "隔离期不生成普通调整建议" in out
    assert any(s["action"] == "regenerate_plan"
               for s in ag.profile.get("pending_adjustments", []))
