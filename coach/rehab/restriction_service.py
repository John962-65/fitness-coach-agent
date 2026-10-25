"""训练限制服务：创建 / 修订 / 解除纪律 / 版本锚。

解除纪律（2.0 §5.3）：
- user_reported：用户本人可解除（必须说明依据，留修订痕）；
- professional：必须附"专业人员说明"才能解除——这是**用户录入的专业人员
  原话**，不是 AI 判断；AI/任何顾问不能解除任何限制；
- triage_recommended：症状缓解后不自动解除，仅设置复核时点提醒用户；
  用户确认情况变化后可解除（按 user 确认记录）。
"""
from __future__ import annotations

from datetime import datetime

SOURCE_TYPES = ("user_reported", "professional", "triage_recommended")
# 区域 → 计划校验关节映射（与动作库 joint_stress 的键对齐）
REGION_JOINTS = {
    "knee": "knee", "lower_back": "lumbar", "shoulder": "shoulder",
    "elbow": "elbow", "wrist": "wrist", "hip": "hip", "ankle": "ankle",
    "neck": "cervical",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def restrictions_version(db, user_id: str) -> str:
    return db.restrictions_version(user_id)


def create_restriction(db, user_id: str, data: dict) -> dict:
    source_type = str(data.get("source_type") or "").strip()
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type 必须是 {SOURCE_TYPES} 之一")
    evidence = str(data.get("source_evidence") or "").strip()
    if not evidence:
        raise ValueError("限制必须附来源依据（用户原话或专业人员说明）")
    description = str(data.get("restriction_description") or "").strip()
    if not description:
        raise ValueError("限制描述必填")
    affected = data.get("affected_activities") or {}
    if not isinstance(affected, dict):
        raise ValueError("affected_activities 必须是对象")
    regions = [str(x)[:20] for x in (affected.get("regions") or [])][:8]
    movements = [str(x)[:40] for x in (affected.get("movements") or [])][:8]
    if not regions and not movements:
        raise ValueError("限制必须覆盖至少一个区域或动作")
    effective_at = str(data.get("effective_at") or _now()[:10])
    rid = db.create_restriction(user_id, {
        "source_type": source_type,
        "source_evidence": evidence[:500],
        "affected_activities": {"regions": regions, "movements": movements,
                                "notes": str(affected.get("notes") or "")[:200]},
        "restriction_description": description[:300],
        "related_episode_id": data.get("related_episode_id"),
        "effective_at": effective_at,
        "review_at": data.get("review_at"),
    })
    _fire(db, user_id, "RestrictionChanged", {"restriction_id": rid})
    return db.get_restriction(user_id, rid)


def lift_restriction(db, user_id: str, rid: int, expected_revision: int,
                     lift_evidence: str, reason: str) -> dict:
    """解除限制：按来源类型校验解除依据。"""
    current = db.get_restriction(user_id, rid)
    if not current:
        raise ValueError("限制不存在")
    if current["status"] != "active":
        raise ValueError(f"限制已处于 {current['status']} 状态")
    evidence = str(lift_evidence or "").strip()
    if not evidence:
        raise ValueError("解除限制必须附依据（原话/专业人员说明）")
    if current["source_type"] == "professional" and len(evidence) < 10:
        raise ValueError("专业人员给出的限制必须附完整的专业人员解除说明"
                         "（≥10 字），AI 与系统提示不能解除")
    fresh = db.revise_restriction(
        user_id, rid, expected_revision,
        {"status": "lifted", "lift_evidence": evidence[:500]},
        reason or "解除限制", evidence)
    _fire(db, user_id, "RestrictionChanged", {"restriction_id": rid})
    return fresh


def effective_restrictions(db, user_id: str) -> list[dict]:
    """当前生效限制（active；供计划校验与各顾问读取）。"""
    return db.list_restrictions(user_id, "active")


def restriction_blocks(db, user_id: str, exercise_doc: dict) -> dict | None:
    """给定动作是否被当前限制阻挡（确定性匹配）。

    匹配维度：
    - 区域 → joint_stress 关节（限制区域映射到动作高压关节）；
    - 区域 → 动作 primary 肌群（中文区域名匹配，如膝→腿部动作不做硬匹配，
      只用关节与显式 movements 列表，避免误伤过宽）；
    - 显式 movements：动作 id/名称/别名精确命中。
    返回阻挡它的限制与原因；None = 无匹配限制。
    """
    active = effective_restrictions(db, user_id)
    if not active:
        return None
    ex_name = str(exercise_doc.get("name") or "")
    ex_id = str(exercise_doc.get("id") or "")
    aliases = set(exercise_doc.get("aliases") or [])
    stress = exercise_doc.get("joint_stress") or {}
    primary = set(exercise_doc.get("primary") or [])
    # 区域与肌群的保守映射（仅在限制显式列出这些肌群词时生效）
    REGION_MUSCLES = {
        "knee": {"quads", "leg"}, "shoulder": {"front_delt", "side_delt",
                                               "rear_delt", "shoulder"},
        "elbow": {"biceps", "triceps"}, "wrist": {"forearm"},
        "lower_back": {"erectors", "lumbar"}, "hip": {"glutes", "hip"},
        "ankle": {"calves"}, "neck": {"traps"},
    }
    for r in active:
        aff = r["affected_activities"] or {}
        # 显式动作命中
        for mv in aff.get("movements") or []:
            if mv and mv in (ex_id, ex_name) or mv in aliases:
                return {"restriction": r, "reason": f"限制显式覆盖动作「{ex_name}」"
                        f"（{r['source_type_label'] if 'source_type_label' in r else r['source_type']}）"}
        # 关节压力命中
        for region in aff.get("regions") or []:
            joint = REGION_JOINTS.get(region)
            if joint and stress.get(joint, 0) >= 2:
                return {"restriction": r,
                        "reason": f"限制覆盖「{region}」区域，而「{ex_name}」对 {joint} "
                                  f"压力为 {stress[joint]}（≥2）"}
            muscles = REGION_MUSCLES.get(region, set())
            if muscles & primary:
                return {"restriction": r,
                        "reason": f"限制覆盖「{region}」区域，而「{ex_name}」主练"
                                  f" {'、'.join(sorted(muscles & primary))}"}
    return None


def _fire(db, user_id: str, trigger: str, refs: dict) -> None:
    from ..experts import task_dispatcher
    try:
        refs = {**refs, "restrictions_version": restrictions_version(db, user_id),
                "symptoms_version": db.symptoms_version(user_id)}
        task_dispatcher.on_event(db, user_id, trigger, refs)
    except Exception:  # noqa: BLE001
        pass
