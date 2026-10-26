"""ExpertInsight 服务：创建 / 查询 / 已读 / 忽略 / 失效 / 重新分析。

失效策略（2.0 §2.2 状态机）：
- 懒失效：每次读取（列表/详情）时对比 source_revision 与当前数据——
  引用的 checkin 修订数变化、或生效计划版本升高 → invalidated。
  这保证任何写入路径（API、agent、恢复历史版本）造成的数据漂移都会
  在用户看到洞察之前被识别，不依赖钩子全覆盖；
- 到期：expires_at 已过且仍 ready/viewed → expired（同样懒判定）；
- 用户操作：view（已读）/ dismiss（忽略，可重新分析）/ regenerate。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from . import evidence_validator

INSIGHT_STATUSES = ("ready", "viewed", "dismissed", "expired", "invalidated",
                    "failed")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_insight(db, user_id: str, payload: dict, task_id: str | None = None) -> dict:
    """分析载荷 → 校验证据 → 落库。"""
    payload = evidence_validator.validate_evidence(payload, db, user_id)
    payload.pop("evidence_report", None)  # 校验报告进任务日志，不进洞察正文
    payload["id"] = "ins-" + uuid.uuid4().hex
    payload["user_id"] = user_id
    payload["task_id"] = task_id
    db.insert_expert_insight(payload)
    return db.get_expert_insight(user_id, payload["id"])


def _revision_drift(db, user_id: str, insight: dict) -> str | None:
    """数据漂移检查：返回失效原因（None=仍有效）。

    覆盖三类依赖：训练打卡修订、生效计划版本、当日饮食记录版本
    （P1）——任何一类漂移都意味着分析基于旧数据。
    """
    rev = insight.get("source_revision") or {}
    for cid, stored in (rev.get("checkins") or {}).items():
        row = db.conn.execute(
            "SELECT (SELECT COUNT(*) FROM checkin_revisions r"
            " WHERE r.checkin_id=c.id) AS rev FROM checkins c"
            " WHERE c.user_id=? AND c.id=?", (user_id, int(cid))).fetchone()
        if not row:
            return f"引用的训练记录 #{cid} 已不存在"
        if row["rev"] != int(stored):
            return (f"引用的训练记录 #{cid} 已被纠错（修订 {stored} → {row['rev']}），"
                    "分析基于旧数据，请重新分析")
    plan_version = rev.get("plan_version")
    if plan_version is not None:
        record = db.get_active_plan_record(user_id)
        if record and record["version"] > int(plan_version):
            return (f"训练计划已更新（v{plan_version} → v{record['version']}），"
                    "该分析基于旧计划，请重新分析")
    for local_date, stored_version in (rev.get("meals") or {}).items():
        from ..nutrition.meal_service import day_version
        current = day_version(db, user_id, local_date)
        if str(current) != str(stored_version):
            return (f"{local_date} 的饮食记录已变化，该分析基于旧数据，"
                    "请重新分析")
    for local_date, stored in (rev.get("recovery") or {}).items():
        from ..recovery.checkin_service import version as recovery_version
        current = recovery_version(db, user_id, local_date)
        if str(current) != str(stored):
            return (f"{local_date} 的恢复记录已变化，该分析基于旧数据，"
                    "请重新分析")
    for rid, stored in (rev.get("recovery_records") or {}).items():
        # P5-C2：下一次训练解读按恢复记录修订号失效（用户更正恢复打卡 → 失效）
        row = db.conn.execute(
            "SELECT (SELECT COUNT(*) FROM recovery_revisions rr"
            " WHERE rr.recovery_id=recovery_checkins.id) AS rev"
            " FROM recovery_checkins WHERE user_id=? AND id=?",
            (user_id, int(rid))).fetchone()
        if not row:
            return f"引用的恢复记录 #{rid} 已不存在"
        if str(row["rev"]) != str(stored):
            return (f"引用的恢复记录 #{rid} 已更新（修订 {stored} → {row['rev']}），"
                    "该分析基于旧数据，请重新分析")
    if "motion" in rev:
        current = db.motion_profile_version(user_id)
        if str(current) != str(rev["motion"]):
            return ("动作视频档案已变化（重算或删除），该分析基于旧数据，"
                    "请重新分析")
    if "symptoms" in rev or "restrictions" in rev:
        from ..rehab import symptom_service, restriction_service
        if "symptoms" in rev                 and str(symptom_service.symptoms_version(db, user_id)) != str(rev["symptoms"]):
            return "症状记录已变化，该分析基于旧数据，请重新分析"
        if "restrictions" in rev and str(
                restriction_service.restrictions_version(db, user_id)) != str(rev["restrictions"]):
            return "训练限制已变化，该分析基于旧数据，请重新分析"
    for mid, stored in (rev.get("body") or {}).items():
        row = db.conn.execute(
            "SELECT (SELECT COUNT(*) FROM body_measurement_revisions r"
            " WHERE r.measurement_id=m.id) AS rev"
            " FROM body_measurements m WHERE m.user_id=? AND m.id=?",
            (user_id, int(mid))).fetchone()
        if not row:
            return f"引用的身体测量 #{mid} 已不存在"
        if str(row["rev"]) != str(stored):
            return (f"引用的身体测量 #{mid} 已被修订，分析基于旧数据，"
                    "请重新分析")
    targets_at = rev.get("targets_updated_at")
    if targets_at:
        targets = db.get_nutrition_targets(user_id)
        if (targets.get("updated_at") or "") != str(targets_at) \
                and targets.get("updated_at") is not None:
            # 目标变更不影响「已记录摄入量」事实，只影响目标比较——保守失效
            return "营养目标已更新，目标比较基于旧目标，请重新分析"
    if "equipment" in rev:
        # P5-C2：器械/地点配置变化 → 候选可执行性必须重新检查
        from ..equipment import equipment_version
        if str(equipment_version(db, user_id)) != str(rev["equipment"]):
            return ("训练地点或器械配置已变化，候选可执行性需重新检查，"
                    "请重新分析")
    if "rules_version" in rev:
        from ..training_progression import progression_service
        if str(rev["rules_version"]) != \
                progression_service.PROGRESSION_RULES_VERSION:
            return "进阶规则版本已更新，旧候选依据不再有效，请重新分析"
    if insight.get("expires_at") and insight["expires_at"] <= _now():
        return "分析已过有效期（数据窗口久远）"
    return None


def refresh_status(db, user_id: str, insight: dict) -> dict:
    """懒失效/到期判定（就地更新后返回最新视图，附 status_reason）。"""
    if insight.get("status") not in ("ready", "viewed"):
        return insight
    reason = _revision_drift(db, user_id, insight)
    if not reason:
        return insight
    new_status = "expired" if reason.startswith("分析已过有效期") else "invalidated"
    db.update_expert_insight_status(user_id, insight["id"], new_status)
    fresh = db.get_expert_insight(user_id, insight["id"])
    fresh["status_reason"] = reason
    return fresh


def list_insights(db, user_id: str, specialist: str | None = None,
                  status: str | None = None, limit: int = 20) -> list[dict]:
    out = []
    for ins in db.list_expert_insights(user_id, specialist, status, limit):
        out.append(refresh_status(db, user_id, ins))
    return out


def get_insight(db, user_id: str, insight_id: str) -> dict | None:
    ins = db.get_expert_insight(user_id, insight_id)
    return refresh_status(db, user_id, ins) if ins else None


def mark_viewed(db, user_id: str, insight_id: str) -> dict | None:
    refresh_status(db, user_id, db.get_expert_insight(user_id, insight_id) or {})
    if db.update_expert_insight_status(user_id, insight_id, "viewed"):
        return db.get_expert_insight(user_id, insight_id)
    return None


def dismiss(db, user_id: str, insight_id: str) -> dict | None:
    """忽略建议（用户决策之一；不删除历史，可重新分析）。"""
    ins = db.get_expert_insight(user_id, insight_id)
    if not ins:
        return None
    if ins["status"] not in ("ready", "viewed"):
        raise ValueError(f"状态为 {ins['status']} 的分析不能被忽略")
    db.update_expert_insight_status(user_id, insight_id, "dismissed")
    return db.get_expert_insight(user_id, insight_id)


def regenerate(db, user_id: str, insight_id: str) -> dict:
    """重新分析：以原洞察输入新建 UserRequested 任务并立即执行。"""
    from . import task_dispatcher
    ins = db.get_expert_insight(user_id, insight_id)
    if not ins:
        raise ValueError("分析不存在")
    task = task_dispatcher.enqueue(
        db, user_id, ins["specialist"], ins["insight_type"], "UserRequested",
        dict(ins.get("input_refs") or {}))
    result = task_dispatcher.run_task(db, task)
    return result
