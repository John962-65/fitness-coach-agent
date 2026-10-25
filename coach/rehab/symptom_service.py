"""症状记录服务：事件 + 观察记录（含修订/历史），保存时同步分流。"""
from __future__ import annotations

import re
from datetime import datetime

from . import triage_rules

REGIONS = ("knee", "shoulder", "elbow", "wrist", "lower_back", "hip",
           "ankle", "neck", "other")
REGION_LABELS = {
    "knee": "膝", "shoulder": "肩", "elbow": "肘", "wrist": "腕",
    "lower_back": "腰背", "hip": "髋", "ankle": "踝", "neck": "颈", "other": "其他",
}
SIDES = ("left", "right", "bilateral")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def symptoms_version(db, user_id: str) -> str:
    return db.symptoms_version(user_id)


def validate_episode(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("数据必须是对象")
    body_region = str(data.get("body_region") or "").strip()
    if body_region not in REGIONS:
        raise ValueError(f"body_region 必须是 {REGIONS} 之一")
    side = data.get("side") or None
    if side and side not in SIDES:
        raise ValueError("side 必须是 left/right/bilateral")
    onset_at = str(data.get("onset_at") or "").strip()
    if not _DATE.match(onset_at):
        raise ValueError("onset_at 需为 YYYY-MM-DD（大致发生日期）")
    try:
        from datetime import date as _d
        _d.fromisoformat(onset_at)
    except ValueError:
        raise ValueError("onset_at 不是有效日期") from None
    description = str(data.get("description") or "").strip()
    if not description:
        raise ValueError("请描述不适情况（用户自述必填）")
    return {
        "body_region": body_region,
        "side": side,
        "onset_at": onset_at,
        "onset_context": str(data.get("onset_context") or "").strip()[:200] or None,
        "description": description[:1000],
        "related_checkin_id": data.get("related_checkin_id"),
        "professional_evaluated": bool(data.get("professional_evaluated")),
    }


def validate_observation(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("数据必须是对象")
    severity = data.get("severity")
    if severity is not None:
        if isinstance(severity, str) and severity.strip():
            try:
                severity = int(severity)
            except ValueError:
                raise ValueError("severity 需为 1-10 整数") from None
        if not isinstance(severity, int) or isinstance(severity, bool) \
                or not 1 <= severity <= 10:
            raise ValueError("severity 需为 1-10 整数（自报程度，不用于推断损伤）")
    limitations = data.get("functional_limitations") or []
    if not isinstance(limitations, list):
        raise ValueError("functional_limitations 必须是列表")
    clean = [str(x).strip()[:40] for x in limitations[:8] if str(x).strip()]
    return {
        "severity": severity,
        "symptom_description": str(data.get("symptom_description") or "").strip()[:1000]
                               or None,
        "functional_limitations": clean,
        "user_notes": str(data.get("user_notes") or "").strip()[:500] or None,
    }


def report_episode(db, user_id: str, data: dict,
                   submission_id: str | None = None) -> dict:
    """记录不适事件：保存 → 同步分流（即时返回，不依赖后台任务）→
    按分流结果创建/更新 triage_recommended 限制 → 触发事件。"""
    if submission_id:
        existing = db.get_record_submission(user_id, submission_id)
        if existing and existing["kind"] == "symptom":
            ep = db.get_symptom_episode(user_id, existing["record_id"])
            if ep:
                return {"episode_id": ep["id"], "existing": True,
                        "triage": triage_rules.triage(
                            ep["description"], onset_at=ep["onset_at"],
                            professional_evaluated=bool(ep["professional_evaluated"]))}
    clean = validate_episode(data)
    ep_id = db.create_symptom_episode(user_id, clean)
    if submission_id:
        db.record_submission(user_id, submission_id, "symptom", ep_id)
    first_obs = validate_observation(data)
    result = triage_rules.triage(
        clean["description"], severity=first_obs.get("severity"),
        functional_limitations=first_obs.get("functional_limitations"),
        onset_at=clean["onset_at"],
        professional_evaluated=clean["professional_evaluated"])
    first_obs["triage_result"] = result
    db.add_symptom_observation(user_id, ep_id, first_obs)
    restriction_id = _sync_triage_restriction(db, user_id, ep_id, clean, result)
    _fire(db, user_id, "SymptomReported", {"episode_id": ep_id})
    return {"episode_id": ep_id, "triage": result,
            "restriction_id": restriction_id,
            "region_label": REGION_LABELS[clean["body_region"]]}


def add_observation(db, user_id: str, ep_id: int, data: dict) -> dict:
    """对既有事件追加观察（不覆盖历史）；分流并同步限制。

    分流以**本次观察的新报告内容**为准（而不是合并历史文本）——否则
    "曾经 urgent" 会永久压住后续缓解信号；历史 urgent 的信息由限制的
    复核机制承载（缓解时限制不自动解除，仅设复核时点）。
    """
    ep = db.get_symptom_episode(user_id, ep_id)
    if not ep:
        raise ValueError("不适事件不存在")
    clean = validate_observation(data)
    result = triage_rules.triage(
        clean.get("symptom_description") or clean.get("user_notes") or "",
        severity=clean.get("severity"),
        functional_limitations=clean.get("functional_limitations"),
        onset_at=ep["onset_at"],
        professional_evaluated=bool(ep["professional_evaluated"]))
    clean["triage_result"] = result
    obs_id = db.add_symptom_observation(user_id, ep_id, clean)
    restriction_id = _sync_triage_restriction(db, user_id, ep_id, ep, result)
    _fire(db, user_id, "SymptomUpdated", {"episode_id": ep_id})
    return {"observation_id": obs_id, "triage": result,
            "restriction_id": restriction_id}


def _sync_triage_restriction(db, user_id: str, ep_id: int, ep: dict,
                             result: dict) -> int | None:
    """按分流结果维护 triage_recommended 限制：
    - 需要限制且无同事件 active 限制 → 创建（收紧方向）；
    - 转为 general_information（缓解）→ **不自动解除**，改 review_at 提示复核；
    - AI 只能收紧不能解除（2.0 §十）。"""
    from . import restriction_service
    region = ep["body_region"] if isinstance(ep.get("body_region"), str) \
        else ep["body_region"]
    suggested = triage_rules.recommended_region_restriction(
        region, ep.get("side"), result["action"])
    existing = next((r for r in db.list_restrictions(user_id)
                     if r["related_episode_id"] == ep_id
                     and r["source_type"] == "triage_recommended"), None)
    if suggested:
        hint = result.get("restriction_hint") or "相关部位保守安排"
        if existing and existing["status"] == "active":
            # 只收紧不放松：范围描述更新为更严的提示
            if hint != existing["restriction_description"]:
                db.revise_restriction(
                    user_id, existing["id"], existing["revision"],
                    {"restriction_description": hint},
                    "症状观察更新，分流提示调整",
                    f"分流规则 {result['rules_version']} · "
                    + "、".join(m["rule_id"] for m in result["matched_rules"]))
            return existing["id"]
        created = restriction_service.create_restriction(
            db, user_id, {
                "source_type": "triage_recommended",
                "source_evidence": (f"安全分流规则命中（{result['rules_version']}）："
                                    + "、".join(m["rule_id"] for m in result["matched_rules"])
                                    if result["matched_rules"] else
                                    f"安全分流（{result['rules_version']}）：信息不足保守处理"),
                "affected_activities": suggested,
                "restriction_description": hint,
                "related_episode_id": ep_id,
            })
        return created["id"] if isinstance(created, dict) else created
    if existing and existing["status"] == "active":
        # 症状缓解：不自动解除，设置复核时点
        db.revise_restriction(
            user_id, existing["id"], existing["revision"],
            {"review_at": _now()[:10]},
            "症状观察转为一般信息，限制待用户复核（不自动解除）",
            f"分流结果 action={result['action']}")
    return None


def update_episode_status(db, user_id: str, ep_id: int, status: str,
                          reason: str, evidence: str) -> dict:
    """事件状态变更（resolved/monitoring/active）——用户操作，留痕。"""
    if status not in ("active", "resolved", "monitoring"):
        raise ValueError("status 必须是 active/resolved/monitoring")
    if not reason.strip() or not evidence.strip():
        raise ValueError("状态变更必须说明原因并附用户原话")
    if not db.update_symptom_episode(user_id, ep_id, {"status": status}):
        raise ValueError("不适事件不存在")
    _fire(db, user_id, "SymptomUpdated", {"episode_id": ep_id})
    return db.get_symptom_episode(user_id, ep_id)


def _fire(db, user_id: str, trigger: str, refs: dict) -> None:
    """康复事件 → 专家任务（整体容错：分流已在保存路径同步完成）。"""
    from ..experts import task_dispatcher
    try:
        refs = {**refs, "symptoms_version": symptoms_version(db, user_id)}
        task_dispatcher.on_event(db, user_id, trigger, refs)
    except Exception:  # noqa: BLE001
        pass
