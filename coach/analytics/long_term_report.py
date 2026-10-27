"""P7-D：长期个人报告（周 / 月 / 自定义区间）。

统一汇总既有同源口径的事实，不另写公式：
- 实际训练频率、计划执行情况、力量表现变化（progress_analysis 趋势）、
  有氧与 HIIT、已记录营养情况（含完整度——记录只覆盖几天就如实说明，
  不得描述为全月真实摄入）、体重趋势（body_metrics）、自报恢复状态、
  个人尝试、当前训练方式、专家建议采纳情况；
- 每个维度保留数据充分性说明与限制；
- 报告只读，不产生建议、不修改任何数据。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from ..analytics.exercise_metrics import exercise_sessions
from ..analytics.fact_service import get_training_facts
from ..analytics.progress_analysis import analyze_progress
from ..body import body_metrics
from ..recovery import recovery_metrics


def _range(period: str, start: str | None, end: str | None) -> tuple[str, str]:
    today = date.today()
    if period == "week":
        end_d = today
        start_d = today - timedelta(days=6)
    elif period == "month":
        end_d = today
        start_d = today - timedelta(days=29)
    elif period == "custom":
        try:
            start_d, end_d = date.fromisoformat(str(start)), \
                date.fromisoformat(str(end))
        except (ValueError, TypeError):
            raise ValueError("custom 区间需要 start/end（YYYY-MM-DD）") from None
        if end_d < start_d:
            raise ValueError("end 不能早于 start")
        if (end_d - start_d).days > 400:
            raise ValueError("区间最长 400 天")
    else:
        raise ValueError("period 必须是 week/month/custom")
    return start_d.isoformat(), end_d.isoformat()


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def build_report(db, user_id: str, period: str = "month",
                 start: str | None = None, end: str | None = None) -> dict:
    start_d, end_d = _range(period, start, end)
    days = _days_between(start_d, end_d)
    limitations: list[str] = []

    # ---- 训练：频率 / 容量 / 趋势（窗口 = 区间） ----
    sessions = [s for s in _sessions_in(db, user_id, start_d, end_d)]
    training = {
        "days_trained": len({s["date"] for s in sessions}),
        "sessions": len(sessions),
        "strength_volume_kg": round(sum(s.get("volume") or 0
                                        for s in sessions)),
        "working_sets": sum(s.get("working_sets") or 0 for s in sessions),
        "steady_cardio_seconds": sum(s.get("steady_cardio_seconds") or 0
                                     for s in sessions),
        "steady_cardio_distance_m": sum(s.get("steady_cardio_distance_m") or 0
                                        for s in sessions),
        "interval_sessions": sum(
            1 for s in sessions if "interval" in (s.get("activity_classes")
                                                  or [])),
    }
    plan_record = db.get_active_plan_record(user_id)
    plan_days_expected = (plan_record["content"].get("days_per_week") or 0) \
        * max(1, round(days / 7)) if plan_record else 0
    training["plan"] = {
        "plan_version": plan_record["version"] if plan_record else None,
        "expected_sessions_hint": plan_days_expected or None,
        "note": "计划执行情况按训练日频次参考；不强制对齐（休息也是训练的一部分）",
    } if plan_record else {"note": "当前无生效计划"}

    # 力量趋势（窗口内会话 ≥2 才判定）
    trend_exercises = sorted(
        {ex.get("exercise_id") for ex in _exercises_in(db, user_id, start_d,
                                                       end_d)
         if ex.get("exercise_id")})
    trend_by_exercise = []
    for eid in trend_exercises[:5]:
        ex_sessions = [s for s in exercise_sessions(db, user_id, eid)
                       if start_d <= s["date"] <= end_d]
        if len(ex_sessions) < 2:
            continue
        t = analyze_progress(
            [{"date": s["date"], "best_e1rm": s.get("best_e1rm"),
              "best_set": s.get("best_set"),
              "longest_set_s": s.get("longest_set_s"),
              "farthest_set_m": s.get("farthest_set_m")}
             for s in reversed(ex_sessions)],
            measurement_type=ex_sessions[0].get("actual_measurement")
            or "weight_reps",
            activity_class=ex_sessions[0].get("activity_class") or "strength")
        trend_by_exercise.append({
            "exercise_id": eid, "verdict": t.get("verdict"),
            "metric": t.get("metric"),
            "limitations": t.get("limitations") or []})
    if not trend_by_exercise:
        limitations.append("窗口内没有可做趋势判定的动作记录")

    # ---- 营养：记录完整度（如实区分"已记录"与"真实摄入"） ----
    from ..nutrition import meal_service
    meals_days = 0
    kcal_sum = protein_sum = 0.0
    for i in range(days):
        day = (date.fromisoformat(start_d) + timedelta(days=i)).isoformat()
        summary = meal_service.day_summary(db, user_id, day)
        if summary.get("meal_types_recorded"):
            meals_days += 1
        kcal_sum += float(summary.get("calories") or 0)
        protein_sum += float(summary.get("protein") or 0)
    completeness = round(meals_days / days, 2) if days else 0
    nutrition = {
        "days_recorded": meals_days,
        "days_total": days,
        "completeness": completeness,
        "avg_calories_recorded": round(kcal_sum / days, 1) if days else None,
        "avg_protein_g_recorded": round(protein_sum / days, 1) if days else None,
        "note": ("以下为已记录摄入；未记录餐次不代表未摄入"
                 if completeness < 0.9 else
                 "记录完整度较高，已记录均值接近真实摄入（仍为自报）"),
    }
    if completeness < 0.6:
        limitations.append(
            f"饮食记录只覆盖 {meals_days}/{days} 天："
            "不能将已记录均值描述为全月真实摄入")

    # ---- 身体 / 恢复 ----
    body_rows = db.list_body_measurements(user_id, start=start_d, end=end_d)
    body_summary = body_metrics.summarize(body_rows, window_days=days)
    recovery = recovery_metrics.recovery_snapshot(db, user_id, days)

    # ---- 个人尝试 / 专家建议采纳 / 当前训练方式 ----
    trials = db.personal_trials(user_id, limit=10)
    trials_in_window = [t for t in trials
                        if (t.get("created_at") or "")[:10] >= start_d]
    insights = db.list_expert_insights(user_id, limit=200)
    adoption = {
        "insights_generated": len(insights),
        "viewed": sum(1 for i in insights if i["status"] == "viewed"),
        "dismissed": sum(1 for i in insights if i["status"] == "dismissed"),
        "invalidated": sum(1 for i in insights
                           if i["status"] in ("invalidated", "expired")),
        "note": "采纳情况只统计查看/忽略/失效计数；是否采纳方案以用户决定为准",
    }
    approach = db.get_approach(user_id)
    proposals = db.list_proposals(user_id, limit=100)
    applied = [p for p in proposals if p.get("status") == "applied"
               and (p.get("decided_at") or "")[:10] >= start_d]

    return {
        "kind": "long_term_report_v1",
        "user_id": user_id,
        "period": period if period != "custom" else "custom",
        "range": {"start": start_d, "end": end_d, "days": days},
        "training": training,
        "strength_trends": trend_by_exercise,
        "nutrition": nutrition,
        "body": {"facts": body_summary.get("facts", []),
                 "limitations": body_summary.get("limitations", [])},
        "recovery": {
            "records_count": recovery.get("records_count", 0),
            "facts": [f for f in recovery.get("facts", [])
                      if f.get("measurement_type") == "recovery"],
            "limitations": recovery.get("limitations") or [],
        },
        "trials": [{"id": t["id"], "change_desc": t["change_desc"],
                    "status": t["status"], "decision": t["decision"]}
                   for t in trials_in_window],
        "expert_adoption": adoption,
        "plan_changes_applied": len(applied),
        "approach_dimensions": list((approach or {}).keys())[:8],
        "limitations": limitations,
        "note": "本报告是只读汇总，全部数值来自各域既有同源口径；"
                "不产生建议、不修改数据",
    }


def _exercises_in(db, user_id: str, start_d: str, end_d: str) -> list[dict]:
    """窗口内的动作记录（供趋势判定取 exercise_id）。"""
    rows = db.conn.execute(
        "SELECT data, created_at FROM checkins WHERE user_id=?"
        " AND type='training' ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    from .exercise_metrics import session_local_date, entry_identity
    out = []
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        if not (start_d <= session_local_date(row["created_at"], data)
                <= end_d):
            continue
        for ex in data.get("exercises") or []:
            eid = entry_identity(db, user_id, ex)
            if eid:
                out.append({"exercise_id": eid})
    return out


def _sessions_in(db, user_id: str, start_d: str, end_d: str) -> list[dict]:
    """窗口内的训练会话（按用户本地日期过滤；每打卡计一次，频率口径）。"""
    rows = db.conn.execute(
        "SELECT id, data, created_at FROM checkins WHERE user_id=?"
        " AND type='training' ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    from .exercise_metrics import entry_identity, session_local_date, _working_sets
    from .. import exercise_service
    out = []
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        local_date = session_local_date(row["created_at"], data)
        if not (start_d <= local_date <= end_d):
            continue
        classes: set[str] = set()
        working_sets = 0
        volume = 0
        steady_seconds = 0
        steady_distance = 0
        has_work = False
        for ex in data.get("exercises") or []:
            logs = [l for l in (ex.get("set_logs") or []) if isinstance(l, dict)]
            ex_id = entry_identity(db, user_id, ex)
            doc = exercise_service.get_exercise(db, user_id, ex_id) if ex_id else None
            working = _working_sets(logs, doc)
            if not working:
                continue
            has_work = True
            classes.update(s["activity_class"] for s in working)
            strength = [s for s in working if s["activity_class"] == "strength"]
            working_sets += len(strength)
            volume += sum(s.get("volume") or 0 for s in strength)
            steady_seconds += sum(
                s.get("duration_seconds") or 0 for s in working
                if s.get("activity_class") not in ("strength", "interval"))
            steady_distance += sum(
                s.get("distance_m") or 0 for s in working
                if s.get("activity_class") == "steady_cardio")
        if has_work:
            # 每个打卡计一次会话（频率口径），但指标聚合该会话的全部动作
            out.append({
                "checkin_id": row["id"], "date": local_date,
                "activity_classes": sorted(classes),
                "working_sets": working_sets,
                "volume": volume,
                "steady_cardio_seconds": steady_seconds,
                "steady_cardio_distance_m": steady_distance,
            })
    return out
