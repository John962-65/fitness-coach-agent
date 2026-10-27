"""P6：跨领域事实包（CrossDomainEvidenceBundle）。

只读取用户授权范围内、与协作问题相关的领域事实；每个领域复用既有
确定性数据服务（fact_service / meal_service / body_metrics /
recovery_metrics / restriction_service / motion 档案），不另写公式。
未请求的领域不进入事实包——不把全部健康数据默认提供给每个专家。
"""
from __future__ import annotations

from datetime import date, timedelta

from ..analytics.fact_service import get_training_facts, training_scope_signature
from ..body import body_metrics
from ..equipment import equipment_version
from ..recovery import recovery_metrics
from ..rehab import restriction_service, safety_integration
from .models import DOMAINS, evidence_item

SUPPORTED_DOMAINS = DOMAINS


def _rev(checkins: dict, plan_record, meals: dict, recovery_count: int,
         recovery_records: dict, restrictions: str, equipment: str,
         motion: str, body: dict, symptoms: str = "",
         targets_updated_at: str = "", training_scope: dict | None = None) -> dict:
    rev: dict = {"checkins": checkins, "recovery_records_count": recovery_count,
                 "restrictions": restrictions, "equipment": equipment}
    if training_scope:
        rev["training_scope"] = training_scope
    if recovery_records:
        rev["recovery_records"] = recovery_records
    if symptoms:
        rev["symptoms"] = symptoms
    if targets_updated_at:
        rev["targets_updated_at"] = targets_updated_at
    if plan_record:
        rev["plan_version"] = plan_record["version"]
    if meals:
        rev["meals"] = meals
    if motion:
        rev["motion"] = motion
    if body:
        rev["body"] = body
    return rev


def build_evidence_bundle(db, user_id: str, domains: list[str],
                          window_days: int = 14,
                          exercise_id: str | None = None) -> dict:
    """构建跨领域事实包（只含请求的领域）。"""
    for d in domains:
        if d not in SUPPORTED_DOMAINS:
            raise ValueError(f"未知领域 {d!r}（可选：{SUPPORTED_DOMAINS}）")
    window_days = max(1, min(int(window_days), 60))
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=window_days - 1)).isoformat()
    window = {"start": start, "end": end, "days": window_days}
    items: list[dict] = []

    checkins_rev: dict = {}
    plan_record = db.get_active_plan_record(user_id)
    meals_rev: dict = {}
    body_rev: dict = {}
    recovery_count = 0
    recovery_records: dict = {}

    if "training" in domains:
        facts = get_training_facts(db, user_id, window_days,
                                   exercise_ids=[exercise_id] if exercise_id else None)
        for f in facts.get("facts", []):
            if f.get("status") == "insufficient":
                continue
            items.append(evidence_item(
                fact_id=f["fact_id"], domain="training", metric=f["metric"],
                value=f.get("value"), unit=f.get("unit") or "",
                time_window=f.get("window") or window,
                source_ids=f.get("source_ids") or [],
                source_revisions={"checkins": {
                    src.split(":")[1]: src.split(":")[-1]
                    for src in f.get("source_ids") or []}},
                calculation=f.get("calculation") or "既有训练事实口径",
                data_quality=f.get("data_quality") or {},
                limitations=[f"状态：{f.get('status')}"] if f.get("status") else []))
            for src in f.get("source_ids") or []:
                parts = src.split(":")
                if parts[0] == "checkin":
                    checkins_rev[parts[1]] = parts[-1]
        if plan_record:
            items.append(evidence_item(
                fact_id=f"plan-version-{plan_record['id']}",
                domain="training", metric="plan-version",
                value=plan_record["version"], unit="",
                time_window=window, source_ids=[f"plan:{plan_record['id']}"],
                source_revisions={"plan_version": plan_record["version"]},
                calculation="当前生效计划版本",
                data_quality={}, limitations=[]))

    if "nutrition" in domains:
        from ..nutrition import meal_service
        days_recorded, kcal_sum, protein_sum = 0, 0.0, 0.0
        for i in range(window_days):
            day = (date.today() - timedelta(days=i)).isoformat()
            summary = meal_service.day_summary(db, user_id, day)
            meals_rev[day] = str(meal_service.day_version(db, user_id, day))
            if summary.get("meal_types_recorded"):
                days_recorded += 1
            kcal_sum += float(summary.get("calories") or 0)
            protein_sum += float(summary.get("protein") or 0)
        completeness = round(days_recorded / window_days, 2)
        targets = db.get_nutrition_targets(user_id)
        targets_updated = targets.get("updated_at")
        if targets.get("protein_g") or targets.get("energy_kcal"):
            items.append(evidence_item(
                fact_id="nutrition-targets", domain="nutrition",
                metric="nutrition-targets",
                value={"protein_g": targets.get("protein_g"),
                       "energy_kcal": targets.get("energy_kcal")},
                unit="", time_window=window, source_ids=[],
                source_revisions={},
                calculation="用户自行设置的营养目标（观察对照基准，非处方）",
                data_quality={},
                limitations=["目标是用户自设参考，不是医疗营养处方"]))
        items.append(evidence_item(
            fact_id=f"nutrition-window-{start}-{end}", domain="nutrition",
            metric="nutrition-window-summary",
            value={"days_recorded": days_recorded,
                   "avg_calories": round(kcal_sum / window_days, 1),
                   "avg_protein_g": round(protein_sum / window_days, 1)},
            unit="", time_window=window, source_ids=[],
            source_revisions={"meals": meals_rev},
            calculation="已记录餐次快照求和 / 窗口天数（未记录餐次不代表未摄入）",
            data_quality={"days_recorded": days_recorded,
                          "completeness": completeness},
            limitations=["饮食记录完整度不足时不能代表真实摄入",
                         "本汇总不构成营养处方"]))

    if "body" in domains:
        rows = db.list_body_measurements(
            user_id, start=(date.today() - timedelta(days=window_days)).isoformat())
        summary = body_metrics.summarize(rows, window_days=window_days)
        for m in rows:
            mid = str(m.get("id"))
            body_rev[mid] = str(m.get("revision") or 0)
        for f in summary.get("facts", []):
            items.append(evidence_item(
                fact_id=f["fact_id"], domain="body", metric=f["metric"],
                value=f.get("value"), unit=f.get("unit") or "",
                time_window=f.get("window") or window,
                source_ids=f.get("source_ids") or [],
                source_revisions={"body": body_rev},
                calculation=f.get("calculation") or "身体测量既有口径",
                data_quality=f.get("data_quality") or {},
                limitations=[]))

    if "recovery" in domains:
        snapshot = recovery_metrics.recovery_snapshot(db, user_id, window_days)
        recovery_count = snapshot.get("records_count", 0)
        # 按记录修订计数：用户更正恢复打卡（含同日更新）会改变修订号
        for r in snapshot.get("records") or []:
            row = db.conn.execute(
                "SELECT (SELECT COUNT(*) FROM recovery_revisions rr"
                " WHERE rr.recovery_id=recovery_checkins.id) AS rev"
                " FROM recovery_checkins WHERE user_id=? AND id=?",
                (user_id, r["id"])).fetchone()
            if row:
                recovery_records[str(r["id"])] = str(row["rev"])
        for f in snapshot.get("facts", []):
            if f.get("measurement_type") != "recovery":
                continue
            items.append(evidence_item(
                fact_id=f["fact_id"], domain="recovery", metric=f["metric"],
                value=f.get("value"), unit=f.get("unit") or "",
                time_window=f.get("window") or window,
                source_ids=f.get("source_ids") or [],
                source_revisions={"recovery_records_count": recovery_count},
                calculation=f.get("calculation") or "自报恢复快照口径",
                data_quality=f.get("data_quality") or {},
                limitations=["用户主观自报；与训练表现不是确定因果关系"]))

    if "rehabilitation" in domains:
        from ..rehab import symptom_service, triage_rules
        safety = safety_integration.safety_view(db, user_id)
        restrictions = restriction_service.effective_restrictions(db, user_id)
        episodes = db.list_symptom_episodes(user_id)[:5]
        for ep in episodes:
            triage = triage_rules.triage(
                ep.get("description"), onset_at=ep.get("onset_at"),
                professional_evaluated=bool(ep.get("professional_evaluated")))
            items.append(evidence_item(
                fact_id=f"symptom-episode-{ep['id']}", domain="rehabilitation",
                metric="symptom-episode",
                value={"status": ep.get("status"),
                       "description": (ep.get("description") or "")[:80],
                       "triage_action": triage.get("action")},
                unit="", time_window=window,
                source_ids=[f"symptom:{ep['id']}"],
                source_revisions={"symptoms": symptom_service.symptoms_version(
                    db, user_id)},
                calculation="既有症状事件与风险分流结果",
                data_quality={},
                limitations=["风险分流是保守规则，不构成医疗诊断"]))
        items.append(evidence_item(
            fact_id="rehab-permission-status", domain="rehabilitation",
            metric="training-permission-status",
            value=safety.permission_status, unit="", time_window=window,
            source_ids=[], source_revisions={
                "restrictions": db.restrictions_version(user_id)},
            calculation="P3 训练许可状态（合并档案与限制）",
            data_quality={}, limitations=[]))
        for r in restrictions:
            items.append(evidence_item(
                fact_id=f"restriction-{r['id']}", domain="rehabilitation",
                metric="active-restriction", value=r.get("restriction_description"),
                unit="", time_window=window,
                source_ids=[f"restriction:{r['id']}"],
                source_revisions={"restrictions": db.restrictions_version(user_id)},
                calculation="当前生效训练限制",
                data_quality={}, limitations=["限制由 P3 安全门强制执行"]))

    if "movement" in domains:
        motion_version = db.motion_profile_version(user_id)
        analyses = db.list_motion_analyses(user_id, limit=5)
        items.append(evidence_item(
            fact_id=f"motion-profile-{motion_version}", domain="movement",
            metric="motion-profile-version", value=motion_version, unit="",
            time_window=window, source_ids=[],
            source_revisions={"motion": motion_version},
            calculation="动作视频档案版本（重算或删除会变化）",
            data_quality={}, limitations=["二维视频分析存在视角与遮挡限制"]))
        for a in analyses:
            items.append(evidence_item(
                fact_id=f"motion-analysis-{a['id']}", domain="movement",
                metric="motion-analysis",
                value={"exercise_id": a.get("exercise_id"),
                       "status": a.get("status")}, unit="", time_window=window,
                source_ids=[f"motion:{a['id']}"],
                source_revisions={"motion": motion_version},
                calculation="既有动作技术分析记录",
                data_quality={}, limitations=["保守观察，不构成动作正确性评分"]))

    training_scope = None
    if "training" in domains:
        training_scope = {
            "exercise_id": exercise_id,
            "window_start": window["start"],
            "window_end": window["end"],
            "signature": training_scope_signature(
                db, user_id, exercise_id, window["start"], window["end"]),
        }
    source_revisions = _rev(
        checkins_rev, plan_record, meals_rev,
        recovery_count if "recovery" in domains else 0,
        recovery_records if "recovery" in domains else {},
        db.restrictions_version(user_id),
        equipment_version(db, user_id),
        db.motion_profile_version(user_id) if "movement" in domains else "",
        body_rev,
        symptom_service.symptoms_version(db, user_id)
        if "rehabilitation" in domains else "",
        (db.get_nutrition_targets(user_id) or {}).get("updated_at") or ""
        if "nutrition" in domains else "",
        training_scope)
    return {"kind": "cross_domain_evidence_bundle_v1",
            "domains": list(domains), "window": window,
            "exercise_id": exercise_id,
            "facts": items, "source_revisions": source_revisions}
