"""P5-C1：下一次训练的统一数据上下文。

只读服务：组合计划处方、真实历史、恢复、安全、器械和事实来源；
不生成建议、不写计划、不修改训练记录。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from .. import equipment as equipment_service
from .. import exercise_service
from ..analytics.activity_class import (
    ACTIVITY_CLASS_VERSION, CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH,
)
from ..analytics.exercise_metrics import exercise_sessions
from ..analytics.fact_service import get_training_facts
from ..recovery import recovery_metrics
from ..rehab import restriction_service, safety_integration
from .comparability import (
    plan_prescription, select_comparable,
)

RECENT_WINDOW_DAYS = 60
RECENT_SESSION_LIMIT = 8


@dataclass
class NextTrainingContext:
    user_id: str
    exercise_id: str
    measurement_type: str
    activity_class: str
    classification_source: dict = field(default_factory=dict)
    plan_id: int | None = None
    plan_version: int | None = None
    planned_day: str | None = None
    planned_exercise: dict | None = None
    plan_prescription_applies: bool = False
    recent_sessions: list = field(default_factory=list)
    comparable_sessions: list = field(default_factory=list)
    last_actual_performance: dict | None = None
    current_prescription: dict = field(default_factory=dict)
    recovery_context: dict = field(default_factory=dict)
    safety_context: dict = field(default_factory=dict)
    equipment_context: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)
    source_revisions: dict = field(default_factory=dict)
    fact_refs: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _find_plan_entry(plan_record: dict | None, exercise_id: str,
                     plan_context: dict | None) -> tuple[dict | None, dict]:
    """返回 (计划日/动作定位摘要, quality)。不修改计划。"""
    quality: dict = {}
    if not plan_record:
        quality["plan"] = "当前没有生效计划"
        return None, quality
    ctx = plan_context if isinstance(plan_context, dict) else {}
    stale = False
    if ctx.get("plan_id") and str(ctx["plan_id"]) != str(plan_record["id"]):
        stale = True
    if ctx.get("plan_version") is not None \
            and int(ctx["plan_version"]) != int(plan_record["version"]):
        stale = True
    quality["plan_context_stale"] = stale
    plan = plan_record.get("content") or {}
    days = [d for d in plan.get("schedule") or [] if isinstance(d, dict)]
    day_name = ctx.get("planned_day") or ctx.get("day")
    index = ctx.get("index")
    planned_id = ctx.get("planned_exercise_id")
    candidates = []
    if day_name:
        day = next((d for d in days if d.get("day") == day_name), None)
        if not day:
            quality["plan"] = "指定训练日不在当前计划"
            return None, quality
        if isinstance(index, int) and 0 <= index < len(day.get("exercises") or []):
            entry = day["exercises"][index]
            candidates = [(day, entry, index)]
        elif planned_id:
            for i, entry in enumerate(day.get("exercises") or []):
                if entry.get("exercise_id") == planned_id:
                    candidates = [(day, entry, i)]
                    break
        else:
            for i, entry in enumerate(day.get("exercises") or []):
                if entry.get("exercise_id") == exercise_id:
                    candidates = [(day, entry, i)]
                    break
    else:
        for day in days:
            for i, entry in enumerate(day.get("exercises") or []):
                if entry.get("exercise_id") == exercise_id:
                    candidates.append((day, entry, i))
    if len(candidates) > 1:
        quality["plan"] = "当前计划多天包含该动作，需要明确训练日与下标"
        quality["plan_candidates"] = [
            {"day": d.get("day"), "index": i} for d, _e, i in candidates]
        return None, quality
    if not candidates:
        quality["plan"] = "当前计划没有该动作"
        return None, quality
    day, entry, idx = candidates[0]
    if stale:
        quality["plan"] = "传入计划版本与当前生效计划不一致"
    return {
        "day": day.get("day"),
        "index": idx,
        "entry": dict(entry),
    }, quality


def _increment_metadata(doc: dict, recent: list[dict]) -> dict:
    progression = doc.get("progression") if isinstance(
        doc.get("progression"), dict) else {}
    inc = progression.get("increment_kg")
    if isinstance(inc, (int, float)) and not isinstance(inc, bool) and inc > 0:
        return {"increment_kg": float(inc),
                "increment_source": "exercise_progression_metadata"}
    increments = []
    for session in recent:
        loads = sorted({float(s["weight_kg"]) for s in session.get("sets") or []
                        if s.get("activity_class") == CLASS_STRENGTH
                        and (s.get("method") or "straight_set") == "straight_set"
                        and isinstance(s.get("weight_kg"), (int, float))})
        increments.extend(round(b - a, 3) for a, b in zip(loads, loads[1:])
                          if b > a)
    if increments:
        return {"increment_kg": min(increments),
                "increment_source": "observed_history"}
    return {"increment_kg": None,
            "increment_source": "unknown_no_exact_increment"}


def _recovery_context(db, user_id: str) -> dict:
    snapshot = recovery_metrics.recovery_snapshot(db, user_id, 14)
    latest = (snapshot.get("records") or [None])[0]
    signals = []
    if latest:
        if isinstance(latest.get("fatigue"), (int, float)) and latest["fatigue"] >= 4:
            signals.append({"metric": "fatigue", "value": latest["fatigue"],
                            "note": "近期自报疲劳较高（1-5 分），不是医学判断"})
        if isinstance(latest.get("muscle_soreness"), (int, float)) \
                and latest["muscle_soreness"] >= 4:
            signals.append({"metric": "muscle_soreness",
                            "value": latest["muscle_soreness"],
                            "note": "近期自报酸痛较高（1-5 分），不是损伤诊断"})
        if isinstance(latest.get("sleep_hours"), (int, float)) \
                and latest["sleep_hours"] < 6:
            signals.append({"metric": "sleep_hours", "value": latest["sleep_hours"],
                            "note": "近期自报睡眠少于 6 小时，仅为事实记录"})
    return {
        "window": snapshot.get("window"),
        "records_count": snapshot.get("records_count", 0),
        "latest": latest,
        "signals": signals,
        "facts": [
            {"fact_id": f["fact_id"], "metric": f["metric"],
             "value": f["value"], "unit": f["unit"],
             "source_ids": f.get("source_ids") or []}
            for f in snapshot.get("facts") or []
            if f.get("measurement_type") == "recovery"
        ],
        "data_quality": snapshot.get("data_quality"),
        "limitations": snapshot.get("limitations") or [],
        "source_ids": [
            f"recovery:{r['id']}:revision:{r.get('revision') or 0}"
            for r in snapshot.get("records") or []
        ],
    }


def build_next_training_context(db, user_id: str, exercise_id: str,
                                plan_context: dict | None = None,
                                recent_days: int = RECENT_WINDOW_DAYS
                                ) -> NextTrainingContext:
    profile = db.get_existing_profile(user_id)
    if not profile:
        raise ValueError("用户不存在或尚未建档")
    doc = exercise_service.get_exercise(db, user_id, exercise_id)
    if not doc:
        raise ValueError("动作不在当前用户可见动作库内")

    plan_record = db.get_active_plan_record(user_id)
    located, plan_quality = _find_plan_entry(plan_record, exercise_id,
                                             plan_context)
    entry = located["entry"] if located else None
    planned_id = (entry or {}).get("exercise_id")
    replacement = bool(entry and planned_id != exercise_id)
    plan_applies = bool(entry and not replacement
                        and not plan_quality.get("plan_context_stale"))

    all_sessions = exercise_sessions(db, user_id, exercise_id)
    since = (date.today() - timedelta(days=recent_days - 1)).isoformat()
    recent = [s for s in all_sessions if s["date"] >= since][:RECENT_SESSION_LIMIT]
    latest = recent[0] if recent else None
    if latest:
        classes = latest.get("activity_classes") or []
        activity_class = classes[0] if len(classes) == 1 else "mixed"
        measurement_type = (latest.get("actual_measurement")
                            or doc.get("measurement") or "weight_reps")
    else:
        activity_class = (CLASS_STEADY_CARDIO
                          if doc.get("activity") == "cardio" else CLASS_STRENGTH)
        measurement_type = doc.get("measurement") or "weight_reps"
    if doc.get("measurement"):
        measurement_type = doc["measurement"]

    prescription = plan_prescription(entry, measurement_type) if plan_applies else {}
    target = prescription.get("reps_target")
    if activity_class not in (CLASS_STRENGTH, CLASS_STEADY_CARDIO, CLASS_INTERVAL):
        comparable, excluded = [], {
            str(s.get("checkin_id")): ["最近记录混有多个活动类别"]
            for s in recent}
    else:
        target_for_compare = target \
            if activity_class == CLASS_STRENGTH and target \
            and target.get("kind") == "reps" else None
        comparable, excluded = select_comparable(
            recent, activity_class, target_for_compare)

    latest_sources = {}
    if latest:
        for source, count in (latest.get("classification") or {}).get(
                "sources", {}).items():
            latest_sources[source] = count

    safety = safety_integration.safety_view(db, user_id)
    restriction_hit = restriction_service.restriction_blocks(db, user_id, doc)
    safety_context = {
        "permission_status": safety.permission_status,
        "allows_prescription": safety.allows_prescription,
        "plan_fenced": safety.plan_fenced,
        "fence_reason": safety.fence_reason,
        "active_restrictions": safety.active_restrictions,
        "action_restriction": restriction_hit,
        "summary_lines": safety.summary_lines(),
        "records_view_allowed": True,
        "recommendations_allowed": (
            not safety.prescription_blocked and restriction_hit is None),
    }

    catalog = equipment_service.equipment_map(db, user_id)
    location = next((x for x in db.list_training_locations(user_id)
                     if x["is_current"]), None)
    availability = equipment_service.exercise_availability(
        db, user_id, doc, location, catalog) if location else {
            "available": None, "missing_equipment_ids": [],
            "missing_equipment": [], "missing_optional_equipment": [],
            "location_ok": None}
    equipment_context = {
        "location": ({"id": location["id"], "name": location["name"],
                      "kind": location["kind"]} if location else None),
        "available": availability["available"],
        "executable": availability["available"] is True,
        "missing_equipment": availability["missing_equipment"],
        "missing_optional_equipment": availability["missing_optional_equipment"],
        "equipment": doc.get("equipment") or [],
        "equipment_names": [catalog.get(x, {"name": x})["name"]
                            for x in (doc.get("equipment") or [])],
        **_increment_metadata(doc, recent),
    }

    facts_bundle = get_training_facts(
        db, user_id, recent_days, exercise_ids=[exercise_id])
    fact_refs = [
        {"fact_id": f["fact_id"], "metric": f["metric"],
         "status": f["status"], "value": f["value"],
         "unit": f["unit"]}
        for f in facts_bundle["facts"]
        if f.get("exercise_id") == exercise_id
        or f.get("measurement_type") == "session"
    ]
    source_revisions = {
        "checkins": {str(s["checkin_id"]): s.get("revision") or 0
                     for s in recent},
        "plan": ({"plan_id": plan_record["id"],
                  "plan_version": plan_record["version"]}
                 if plan_record else None),
        "restrictions_version": db.restrictions_version(user_id),
        "activity_class_version": ACTIVITY_CLASS_VERSION,
    }
    recovery_context = _recovery_context(db, user_id)
    source_revisions["recovery"] = {
        src.split(":")[1]: src.split(":")[-1]
        for src in recovery_context["source_ids"]}
    latest_comparable = bool(
        latest and any(s.get("checkin_id") == latest.get("checkin_id")
                       for s in comparable))
    data_quality = {
        **plan_quality,
        "recent_session_count": len(recent),
        "comparable_session_count": len(comparable),
        "latest_session_comparable": latest_comparable,
        "comparable_exclusions": excluded,
        "last_actual_source": "actual_checkins_only",
        "classification_sources": latest_sources,
        "classification_version": ACTIVITY_CLASS_VERSION,
        "rpe_missing_sessions": sum(
            1 for s in comparable
            if any(st.get("rpe") is None for st in s.get("sets") or [])),
        "methods": sorted({
            st.get("method") or "straight_set"
            for s in recent for st in s.get("sets") or []
            if st.get("activity_class") == CLASS_STRENGTH}),
        "superset": any(s.get("superset_group") for s in recent),
        "temporary_replacement": replacement,
        "recovery_records": recovery_context["records_count"],
        "recovery_missing": recovery_context["records_count"] == 0,
    }
    return NextTrainingContext(
        user_id=user_id, exercise_id=exercise_id,
        measurement_type=measurement_type,
        activity_class=activity_class,
        classification_source=latest_sources,
        plan_id=plan_record["id"] if plan_record else None,
        plan_version=plan_record["version"] if plan_record else None,
        planned_day=located["day"] if located else None,
        planned_exercise=entry,
        plan_prescription_applies=plan_applies,
        recent_sessions=recent,
        comparable_sessions=comparable,
        last_actual_performance=(
            _performance(latest) if latest else None),
        current_prescription=prescription,
        recovery_context=recovery_context,
        safety_context=safety_context,
        equipment_context=equipment_context,
        data_quality=data_quality,
        source_revisions=source_revisions,
        fact_refs=fact_refs,
    )


def _performance(session: dict) -> dict:
    from .comparability import performance_summary
    return performance_summary(session)
