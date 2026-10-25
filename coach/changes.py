"""2.0 B2：统一修改协议 ChangeProposal → Validation → Commit（DESIGN_2.0 §四）

两条路径、同一套校验：
- 手动修改（source=user_manual）：校验通过即提交生效（2.0 §4.1 常规编辑
  不需要 AI 批准，但数据合法性与安全约束不可绕过）。
- AI 建议（source=ai）：先落 pending，经用户明确确认（语义门，复用
  confirmation.classify_decision）后走同一提交路径。

提交为单事务（数据写入 + 版本落档 + 提案状态一起成功/回滚）；
base_version 乐观锁防止覆盖其他界面的后续修改（2.0 §4.3）。
"""
from __future__ import annotations

import copy
import json
import uuid

from .approach import apply_operations as apply_approach_ops
from .confirmation import classify_decision
from .exercises import library
from .medical import training_permission
from .plan import INJURY_STRESS_THRESHOLD, _injured_joints, _joints_without_data
from .plan_edit import _resolve_exercise, apply_plan_operations

TARGETS = ("approach", "plan")
SOURCES = ("user_manual", "ai", "rule")


class ProposalRejected(ValueError):
    """确定性校验未通过；errors 为人可读的原因列表。"""

    def __init__(self, errors):
        self.errors = [str(e) for e in errors]
        super().__init__("；".join(self.errors))


def _require_dict(value, name, errors) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{name} 必须是对象")
        return {}
    return value


def validate_change(db, user_id: str, target: str, operations,
                    base_version, resolver=None) -> dict:
    """全部确定性校验（结构 / 安全 / 版本），不写库。
    返回 prepared 中间产物；不通过抛 ProposalRejected。"""
    errors: list[str] = []
    if target not in TARGETS:
        raise ProposalRejected([f"target 必须是 {TARGETS} 之一"])
    base = _require_dict(base_version, "base_version", errors)
    if not isinstance(operations, list) or not operations:
        raise ProposalRejected(["operations 必须是非空操作列表"])
    if any(not isinstance(op, dict) for op in operations):
        raise ProposalRejected(["每个操作都必须是对象"])
    if errors:
        raise ProposalRejected(errors)

    profile = db.get_existing_profile(user_id)
    if not profile:
        raise ProposalRejected(["用户不存在或尚未建档"])

    if target == "approach":
        return _validate_approach(db, user_id, profile, operations, base)
    return _validate_plan(db, user_id, profile, operations, base, resolver)


# ---- approach 目标 ----

def _validate_approach(db, user_id, profile, operations, base) -> dict:
    current = db.get_approach(user_id)
    if not current:
        raise ProposalRejected(["尚未初始化训练方式，先调用 initialize"])
    if base.get("approach_revision") != current.get("revision"):
        raise ProposalRejected([
            f"base_version.approach_revision={base.get('approach_revision')!r} "
            f"与当前版本 v{current.get('revision')} 不一致，请重新获取后再提交"])
    doc = copy.deepcopy(current)
    try:
        diffs = apply_approach_ops(doc, operations)
    except ValueError as e:
        raise ProposalRejected([str(e)]) from None
    return {"target": "approach", "base": {"approach_revision": current["revision"]},
            "new_doc": doc, "diffs": diffs, "warnings": []}


# ---- plan 目标 ----

def _added_exercise_ids(operations, resolver=None) -> list[str]:
    ids = []
    for op in operations:
        if op.get("op") in ("add_exercise", "replace_exercise") and op.get("exercise"):
            try:
                ex_id, _name = _resolve_exercise(op["exercise"], resolver)
            except ValueError:
                continue  # 结构校验阶段会给出完整错误
            ids.append(ex_id)
    return ids


def _validate_plan(db, user_id, profile, operations, base,
                   resolver=None) -> dict:
    record = db.get_active_plan_record(user_id)
    if not record:
        raise ProposalRejected(["当前没有生效的计划"])
    if base.get("plan_id") != record["id"] or base.get("plan_version") != record["version"]:
        raise ProposalRejected([
            f"base_version(plan_id={base.get('plan_id')!r},plan_version="
            f"{base.get('plan_version')!r}) 与当前生效计划"
            f"(#{record['id']} v{record['version']}) 不一致，请重新获取后再提交"])

    errors: list[str] = []
    fence = profile.get("plan_fence")
    if fence:
        errors.append(f"计划已隔离（{fence.get('reason', '未知原因')}）："
                      "编辑被拒绝，唯一出路是跟进安全记录并确认重排")
    if not training_permission(profile).allows_prescription:
        errors.append("医疗许可不允许训练处方，计划编辑被拒绝；请先确认医疗许可")

    # 伤病关节高压动作注入检查（用户手动编辑也不可绕过安全约束）
    joints, _unknown = _injured_joints((profile.get("conditions") or {}).get("injuries"))
    joints -= _joints_without_data(joints)
    for ex_id in _added_exercise_ids(operations, resolver):
        if not joints:
            break
        stress = (library.get(ex_id) or {}).get("joint_stress") or {}
        for joint in sorted(joints):
            if stress.get(joint, 0) >= INJURY_STRESS_THRESHOLD:
                errors.append(
                    f"动作「{library.get(ex_id)['name']}」对 {joint} 压力高"
                    f"（≥{INJURY_STRESS_THRESHOLD}），而档案记录该部位有伤，拒绝加入计划")
    # P3：训练限制（TrainingRestriction）服务端强制校验——任何来源的
    # 限制（用户报告/专业人员/安全分流）都不因专家未提示而失效
    from .rehab.safety_integration import validate_plan_change
    from . import exercise_service as _ex_svc
    added_docs = []
    for ex_id in _added_exercise_ids(operations, resolver):
        doc = _ex_svc.get_exercise(db, user_id, ex_id)
        if doc:
            added_docs.append(doc)
    errors.extend(validate_plan_change(db, user_id, added_docs))
    if errors:
        raise ProposalRejected(errors)

    try:
        new_plan, applied = apply_plan_operations(record["content"], operations,
                                                  resolver=resolver)
    except ValueError as e:
        raise ProposalRejected([str(e)]) from None

    warnings = []
    for ex_id in _added_exercise_ids(operations, resolver):
        row = db.get_user_exercise(user_id, ex_id)
        if row and row.get("status") == "avoid":
            ex = library.get(ex_id) or {}
            warnings.append(
                f"你之前说过先不练{ex.get('name', ex_id)}；这次手动加回请确认情况已变化")
    return {"target": "plan", "base": {"plan_id": record["id"], "plan_version": record["version"]},
            "plan": new_plan, "applied": applied, "warnings": warnings}


# ---- 提交（单事务：数据 + 版本 + 提案状态一起成功/回滚）----

def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _record_proposal(db, user_id, target, operations, source, reason,
                     base_version, status="pending") -> str:
    proposal_id = "chg-" + uuid.uuid4().hex
    db.insert_proposal({
        "id": proposal_id, "user_id": user_id, "target": target,
        "operations": operations, "source": source, "reason": str(reason or ""),
        "base_version": base_version, "status": status,
        "created_message_id": db.latest_user_message_id(user_id),
    })
    return proposal_id


def _apply_approach(db, user_id, prepared, proposal_id, initiator, reason) -> dict:
    with db.conn:
        if not db.conn.in_transaction:
            db.conn.execute("BEGIN IMMEDIATE")
        row = db.conn.execute(
            "SELECT content FROM training_approach WHERE user_id=?", (user_id,)).fetchone()
        if not row or json.loads(row["content"]).get("revision") \
                != prepared["base"]["approach_revision"]:
            raise ProposalRejected(["训练方式版本已被其他修改更新，请重新获取后再提交"])
        new_rev = prepared["base"]["approach_revision"] + 1
        doc = prepared["new_doc"]
        doc["revision"] = new_rev
        plan_record = db.get_active_plan_record(user_id)
        db.conn.execute(
            "UPDATE training_approach SET content=?, updated_at=? WHERE user_id=?",
            (json.dumps(doc, ensure_ascii=False), _now(), user_id))
        db.conn.execute(
            "INSERT INTO approach_revisions(user_id, revision, content, diff, initiator,"
            " reason, confirmed, proposal_id, affected_plan_version, created_at)"
            " VALUES(?,?,?,?,?,?,1,?,?,?)",
            (user_id, new_rev, json.dumps(doc, ensure_ascii=False),
             json.dumps(prepared["diffs"], ensure_ascii=False), initiator,
             str(reason or ""), proposal_id,
             plan_record["version"] if plan_record else None, _now()))
        db.conn.execute(
            "UPDATE change_proposals SET status='applied', result=?, decided_at=?"
            " WHERE user_id=? AND id=? AND status='pending'",
            (json.dumps({"revision": new_rev, "diffs": prepared["diffs"]},
                        ensure_ascii=False), _now(), user_id, proposal_id))
    return {"target": "approach", "approach_revision": new_rev,
            "diffs": prepared["diffs"], "warnings": prepared.get("warnings", [])}


def _apply_plan(db, user_id, prepared, proposal_id, source, reason) -> dict:
    profile = db.get_existing_profile(user_id)
    with db.conn:
        if not db.conn.in_transaction:
            db.conn.execute("BEGIN IMMEDIATE")
        current = db.conn.execute(
            "SELECT id, version FROM plans WHERE user_id=? AND active=1",
            (user_id,)).fetchone()
        if not current or current["id"] != prepared["base"]["plan_id"]:
            raise ProposalRejected(["计划已被其他修改更新，请重新获取后再提交"])
        db.conn.execute("UPDATE plans SET active=0 WHERE user_id=?", (user_id,))
        version = db.conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE user_id=?",
            (user_id,)).fetchone()[0]
        content = prepared["plan"]
        content["adjust_action"] = "manual_edit" if source == "user_manual" else "ai_edit"
        content["adjust_reason"] = str(reason or "统一修改协议提交")
        approach = db.get_approach(user_id)
        if approach:
            # 计划版本与训练方式版本关联（2.0 §十一 约束 2）
            content["approach_revision"] = approach.get("revision")
        cur = db.conn.execute(
            "INSERT INTO plans(user_id, version, content, active, created_at)"
            " VALUES(?,?,?,1,?)",
            (user_id, version, json.dumps(content, ensure_ascii=False), _now()))
        plan_id = cur.lastrowid
        profile["pending_adjustments"] = []
        db.conn.execute(
            "UPDATE users SET profile=?, updated_at=? WHERE user_id=?",
            (json.dumps(profile, ensure_ascii=False), _now(), user_id))
        db.conn.execute(
            "UPDATE change_proposals SET status='applied', result=?, decided_at=?"
            " WHERE user_id=? AND id=? AND status='pending'",
            (json.dumps({"plan_id": plan_id, "plan_version": version,
                         "changes": prepared["applied"],
                         "warnings": prepared.get("warnings", [])},
                        ensure_ascii=False), _now(), user_id, proposal_id))
    return {"target": "plan", "plan_id": plan_id, "plan_version": version,
            "changes": prepared["applied"], "warnings": prepared.get("warnings", [])}


def _apply(db, user_id, prepared, proposal_id, source, reason) -> dict:
    if prepared["target"] == "approach":
        initiator = "user" if source == "user_manual" else "ai"
        return _apply_approach(db, user_id, prepared, proposal_id, initiator, reason)
    return _apply_plan(db, user_id, prepared, proposal_id, source, reason)


def restore_plan_version(db, user_id: str, version: int, reason: str = "") -> dict:
    """恢复历史计划版本（M2 撤销闭环）：复制旧版本内容为新版本提交。

    与手动编辑同一套安全门：隔离/医疗暂停期拒绝；base 乐观锁用当前
    生效计划 id；旧 pending 建议一并作废。
    """
    profile = db.get_existing_profile(user_id)
    if not profile:
        raise ProposalRejected(["用户不存在或尚未建档"])
    errors: list[str] = []
    fence = profile.get("plan_fence")
    if fence:
        errors.append(f"计划已隔离（{fence.get('reason', '未知原因')}）：恢复被拒绝")
    if not training_permission(profile).allows_prescription:
        errors.append("医疗许可不允许训练处方，恢复被拒绝")
    record = db.get_active_plan_record(user_id)
    old = db.get_plan_by_version(user_id, version)
    if not record or not old:
        raise ProposalRejected(["当前没有生效计划或目标版本不存在"])
    if errors:  # 安全门优先于同版本等常规检查
        raise ProposalRejected(errors)
    if old["id"] == record["id"]:
        raise ProposalRejected([f"v{version} 已是当前生效版本"])

    content = copy.deepcopy(old["content"])
    content["adjust_action"] = "restore"
    content["adjust_reason"] = reason or f"恢复计划 v{version}"
    approach = db.get_approach(user_id)
    if approach:
        content["approach_revision"] = approach.get("revision")
    with db.conn:
        if not db.conn.in_transaction:
            db.conn.execute("BEGIN IMMEDIATE")
        current = db.conn.execute(
            "SELECT id FROM plans WHERE user_id=? AND active=1", (user_id,)).fetchone()
        if not current or current["id"] != record["id"]:
            raise ProposalRejected(["计划已被其他修改更新，请重试"])
        db.conn.execute("UPDATE plans SET active=0 WHERE user_id=?", (user_id,))
        new_version = db.conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE user_id=?",
            (user_id,)).fetchone()[0]
        cur = db.conn.execute(
            "INSERT INTO plans(user_id, version, content, active, created_at)"
            " VALUES(?,?,?,1,?)",
            (user_id, new_version, json.dumps(content, ensure_ascii=False), _now()))
        profile["pending_adjustments"] = []
        db.conn.execute("UPDATE users SET profile=? WHERE user_id=?",
                        (json.dumps(profile, ensure_ascii=False), user_id))
    return {"target": "plan", "plan_id": cur.lastrowid, "plan_version": new_version,
            "restored_from": version,
            "changes": [f"计划恢复自 v{version}（{content['adjust_reason']}）"]}


def submit_manual(db, user_id: str, target: str, operations,
                  reason: str, base_version, resolver=None) -> dict:
    """手动修改：校验 → 暂存提案（审计）→ 单事务应用。失败时提案记 rejected。"""
    prepared = validate_change(db, user_id, target, operations, base_version,
                               resolver)
    proposal_id = _record_proposal(db, user_id, target, operations,
                                   "user_manual", reason, prepared["base"])
    try:
        result = _apply(db, user_id, prepared, proposal_id, "user_manual", reason)
    except Exception as e:  # 应用期失败（并发漂移等）：数据未写入，提案留痕
        db.decide_proposal(user_id, proposal_id, "rejected", {"error": str(e)})
        raise
    return {"proposal_id": proposal_id, "status": "applied", **result}


def stage_ai(db, user_id: str, target: str, operations, reason: str,
             base_version, created_message_id: int | None = None) -> dict:
    """AI 建议先落 pending；未经用户确认不生效（同套校验先行）。"""
    prepared = validate_change(db, user_id, target, operations, base_version)
    proposal_id = _record_proposal(db, user_id, target, operations, "ai",
                                   reason, prepared["base"])
    if created_message_id is not None:
        db.conn.execute(
            "UPDATE change_proposals SET created_message_id=? WHERE id=?",
            (int(created_message_id), proposal_id))
        db.conn.commit()
    return {"proposal_id": proposal_id, "status": "pending",
            "target": target, "base": prepared["base"],
            "warnings": prepared.get("warnings", [])}


def confirm_proposal(db, user_id: str, proposal_id: str, message: str,
                     already_recorded: bool = False) -> dict:
    """用户确认 AI 提案：语义门（同意/拒绝/含糊）→ 引用消歧 → 重校验 → 提交。

    边界：API 场景确认消息由客户端传入并在此留痕入库；agent 对话场景
    本轮用户原话已由 chat() 落库，传 already_recorded=True 避免重复记录。
    "不得同轮自批"由 created_message_id 跨轮检查保证：确认消息必须是
    提案暂存之后的新用户消息。
    """
    proposal = db.get_proposal(user_id, proposal_id)
    if not proposal:
        raise ProposalRejected(["提案不存在"])
    if proposal["status"] != "pending":
        raise ProposalRejected([f"提案状态为 {proposal['status']}，不能再确认"])
    if proposal["source"] != "ai":
        raise ProposalRejected(["只有 AI 来源的提案需要确认（手动提案已即时生效）"])

    text = str(message or "").strip()
    if not text:
        return {"proposal_id": proposal_id, "status": "pending",
                "decision": "unclear", "note": "确认为空，保持待确认"}
    decision = classify_decision(text)
    if decision == "unclear":
        return {"proposal_id": proposal_id, "status": "pending",
                "decision": "unclear",
                "note": "用户表述含糊或仍在考虑，保持待确认"}
    if decision == "reject":
        db.decide_proposal(user_id, proposal_id, "rejected",
                           {"decision": "reject", "message": text})
        return {"proposal_id": proposal_id, "status": "rejected",
                "decision": "reject", "message": text}

    pending = db.list_proposals(user_id, status="pending")
    if len(pending) > 1 and proposal_id not in text:
        raise ProposalRejected([
            "当前有多条待确认提案，请在消息中注明要确认的提案 ID："
            + "、".join(p["id"] for p in pending)])

    if already_recorded:
        # 对话场景：本轮原话已在库，直接作为最新用户消息依据
        mid = db.latest_user_message_id(user_id)
    else:
        mid = db.add_message(user_id, "user", text)  # 确认原话留痕
    created = proposal.get("created_message_id")
    if isinstance(created, int) and mid <= created:
        db.decide_proposal(user_id, proposal_id, "rejected",
                           {"error": "确认消息不晚于提案创建，不得代用户批准"})
        raise ProposalRejected(["确认消息与提案同轮，不得代用户批准"])

    try:
        prepared = validate_change(db, user_id, proposal["target"],
                                   proposal["operations"], proposal["base_version"])
    except ProposalRejected as e:
        db.decide_proposal(user_id, proposal_id, "expired", {"error": e.errors})
        raise
    result = _apply(db, user_id, prepared, proposal_id, "ai", proposal["reason"])
    return {"proposal_id": proposal_id, "status": "applied",
            "decision": "accept", **result}
