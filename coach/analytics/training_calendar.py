"""训练日历与周期汇总：按日期聚合训练记录。

P5-B3 统一口径（所有类别先经 activity_class 分类）：
- strength：工作组、容量、肌群；
- steady_cardio：持续有氧时长/距离；有效 HIIT 绝不重复计入；
- interval：计划/完成/跳过轮次与工作/休息/总经过秒数。

兼容字段：
- sessions = training_sessions；
- working_sets = strength_working_sets；
- volume = strength_volume_kg；
- cardio_seconds = steady_cardio_seconds（P5-B 旧实现误把 HIIT 也计入持续性
  有氧，B3 明确修正；间歇另见 interval_*）；
- interval_seconds = interval_elapsed_seconds。
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta

from .activity_class import (
    ACTIVITY_CLASS_VERSION, CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH,
    classify_training_record, classification_quality,
)
from .exercise_metrics import entry_identity, parse_stamp, session_local_date, set_volume

_MAX_SCAN_DAYS = 400  # 周期汇总最多回看范围，防全表滥用


def _load_training_rows(db, user_id: str, since: str | None = None):
    sql = ("SELECT id, data, created_at FROM checkins WHERE user_id=? AND type='training'")
    params: list = [user_id]
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    sql += " ORDER BY created_at DESC, id DESC"
    for row in db.conn.execute(sql, params).fetchall():
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            yield row, data


def _exercise_doc(db, user_id: str, ex_id: str):
    """用户可见动作文档（内置 + 本人自定义），与 exercise_service 同口径。"""
    from .. import exercise_service
    return exercise_service.get_exercise(db, user_id, ex_id)


def _iter_classified_sets(db, user_id: str, data: dict):
    """产出 (动作文档 | None, working_set, classification)。"""
    for ex in data.get("exercises", []) or []:
        if not isinstance(ex, dict):
            continue
        doc = None
        ex_id = entry_identity(db, user_id, ex)
        if ex_id:
            doc = _exercise_doc(db, user_id, ex_id)
        logs = ex.get("set_logs") if isinstance(ex.get("set_logs"), list) else []
        for log in logs:
            if isinstance(log, dict) and not log.get("warmup"):
                yield doc, log, classify_training_record(doc, log)


def _empty_metrics() -> dict:
    return {
        "training_sessions": 0,
        "strength_working_sets": 0,
        "strength_volume_kg": 0.0,
        "steady_cardio_seconds": 0.0,
        "steady_cardio_distance_m": 0.0,
        "interval_work_seconds": 0,
        "interval_rest_seconds": 0,
        "interval_elapsed_seconds": 0,
        "interval_planned_rounds": 0,
        "interval_completed_rounds": 0,
        "interval_skipped_rounds": 0,
        "interval_ended_early": 0,
        "strength_sessions": 0,
        "steady_cardio_sessions": 0,
        "interval_sessions": 0,
        "by_muscle": {},
        "cardio_by_activity": {},
    }


def _add_classified_log(metrics: dict, doc, log: dict, cls: dict,
                        session_id: int, session_classes: set[str]) -> None:
    category = cls["class"]
    session_classes.add(category)
    if category == CLASS_STRENGTH:
        metrics["strength_working_sets"] += 1
        metrics["strength_volume_kg"] += set_volume(log)
        muscle = (doc.get("primary") or ["other"])[0] if doc else "other"
        metrics["by_muscle"][muscle] = metrics["by_muscle"].get(muscle, 0) + 1
        return
    if category == CLASS_STEADY_CARDIO:
        metrics["steady_cardio_seconds"] += float(log.get("duration_seconds") or 0)
        distance = float(log.get("distance_m") or 0)
        metrics["steady_cardio_distance_m"] += distance
        key = (doc or {}).get("id") or str(log.get("exercise_name") or "cardio")
        group = metrics["cardio_by_activity"].setdefault(key, {
            "name": (doc or {}).get("name") or key,
            "session_ids": set(), "duration_seconds": 0.0, "distance_m": 0.0,
        })
        group["session_ids"].add(session_id)
        group["duration_seconds"] += float(log.get("duration_seconds") or 0)
        group["distance_m"] += distance
        return
    hiit = log.get("hiit") if isinstance(log.get("hiit"), dict) else {}
    work = int(hiit.get("work_seconds_done") or 0)
    rest = int(hiit.get("rest_seconds_done") or 0)
    elapsed = int(log.get("duration_seconds") or 0)
    if elapsed <= 0:
        elapsed = work + rest
    metrics["interval_work_seconds"] += work
    metrics["interval_rest_seconds"] += rest
    metrics["interval_elapsed_seconds"] += elapsed
    metrics["interval_planned_rounds"] += int(hiit.get("planned_rounds") or 0)
    metrics["interval_completed_rounds"] += int(hiit.get("completed_rounds") or 0)
    metrics["interval_skipped_rounds"] += len(hiit.get("skipped") or [])
    if hiit.get("ended_early"):
        metrics["interval_ended_early"] += 1


def _finalize_metrics(metrics: dict, session_classes: set[str]) -> dict:
    if CLASS_STRENGTH in session_classes:
        metrics["strength_sessions"] += 1
    if CLASS_STEADY_CARDIO in session_classes:
        metrics["steady_cardio_sessions"] += 1
    if CLASS_INTERVAL in session_classes:
        metrics["interval_sessions"] += 1
    return metrics


def _cardio_activity_rows(metrics: dict) -> list[dict]:
    rows = []
    for key in sorted(metrics["cardio_by_activity"]):
        group = metrics["cardio_by_activity"][key]
        seconds = group["duration_seconds"]
        distance = group["distance_m"]
        rows.append({
            "exercise_id": key,
            "name": group["name"],
            "sessions": len(group["session_ids"]),
            "duration_seconds": round(seconds),
            "distance_m": round(distance),
            "speed_mps": round(distance / seconds, 3) if seconds > 0 and distance > 0 else None,
            "pace_sec_per_km": round(seconds / (distance / 1000), 1)
                                if distance > 0 and seconds > 0 else None,
        })
    return rows


def month_calendar(db, user_id: str, year: int, month: int) -> dict:
    """某月训练日历。

    工作组/容量只含 strength；有氧与间歇分别单列。sessions 仍保留为全部
    训练会话数（兼容），训练日不再因类别而拆分。
    """
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    since = (first - timedelta(days=1)).isoformat()
    days: dict[str, dict] = {}
    classification_rows = []
    for row, data in _load_training_rows(db, user_id, since=since):
        day = session_local_date(row["created_at"], data)
        if day < first.isoformat() or day > last.isoformat():
            continue
        slot = days.setdefault(day, {
            "date": day, **_empty_metrics(),
            "classification_sources": {},
        })
        slot["training_sessions"] += 1
        session_classes: set[str] = set()
        for doc, log, cls in _iter_classified_sets(db, user_id, data):
            classification_rows.append(cls)
            slot["classification_sources"][cls["source"]] = \
                slot["classification_sources"].get(cls["source"], 0) + 1
            _add_classified_log(slot, doc, log, cls, row["id"], session_classes)
        _finalize_metrics(slot, session_classes)
    out_days = []
    for key in sorted(days):
        slot = days[key]
        cardio_rows = _cardio_activity_rows(slot)
        out_days.append({
            **{k: v for k, v in slot.items()
               if k not in ("cardio_by_activity",)},
            "sessions": slot["training_sessions"],
            "working_sets": slot["strength_working_sets"],
            "volume": round(slot["strength_volume_kg"]),
            "cardio_by_activity": cardio_rows,
        })
    return {
        "year": year, "month": month,
        "days": out_days,
        "activity_class_version": ACTIVITY_CLASS_VERSION,
        "classification": classification_quality(classification_rows),
    }


def _session_duration_min(data: dict, stamps: list[str]) -> float | None:
    meta = data.get("session_meta") if isinstance(data.get("session_meta"), dict) else {}
    if meta.get("started_at") and meta.get("completed_at"):
        try:
            return max(0.0, (parse_stamp(meta["completed_at"])
                             - parse_stamp(meta["started_at"])).total_seconds() / 60)
        except ValueError:
            pass
    if len(stamps) >= 2:
        return (parse_stamp(max(stamps)) - parse_stamp(min(stamps))).total_seconds() / 60
    return None


def period_summary(db, user_id: str, days: int = 30) -> dict:
    """周期统计：统一类别口径 + 兼容字段别名。"""
    days = max(1, min(int(days), _MAX_SCAN_DAYS))
    since = (datetime.now() - timedelta(days=days)).isoformat()
    metrics = _empty_metrics()
    durations: list[float] = []
    session_dates: set[str] = set()
    classification_rows = []
    for row, data in _load_training_rows(db, user_id, since=since):
        metrics["training_sessions"] += 1
        session_dates.add(session_local_date(row["created_at"], data))
        stamps: list[str] = []
        session_classes: set[str] = set()
        for doc, log, cls in _iter_classified_sets(db, user_id, data):
            classification_rows.append(cls)
            session_classes.add(cls["class"])
            _add_classified_log(metrics, doc, log, cls, row["id"], session_classes)
            if log.get("at"):
                stamps.append(log["at"])
        _finalize_metrics(metrics, session_classes)
        duration = _session_duration_min(data, stamps)
        if duration is not None:
            durations.append(duration)
    return {
        "days": days,
        "training_sessions": metrics["training_sessions"],
        "training_days": len(session_dates),
        "per_week": round(metrics["training_sessions"] * 7 / days, 1),
        "strength_working_sets": metrics["strength_working_sets"],
        "strength_volume_kg": round(metrics["strength_volume_kg"]),
        "steady_cardio_seconds": round(metrics["steady_cardio_seconds"]),
        "steady_cardio_distance_m": round(metrics["steady_cardio_distance_m"]),
        "interval_work_seconds": metrics["interval_work_seconds"],
        "interval_rest_seconds": metrics["interval_rest_seconds"],
        "interval_elapsed_seconds": metrics["interval_elapsed_seconds"],
        "interval_planned_rounds": metrics["interval_planned_rounds"],
        "interval_completed_rounds": metrics["interval_completed_rounds"],
        "interval_skipped_rounds": metrics["interval_skipped_rounds"],
        "interval_ended_early": metrics["interval_ended_early"],
        "strength_sessions": metrics["strength_sessions"],
        "steady_cardio_sessions": metrics["steady_cardio_sessions"],
        "interval_sessions": metrics["interval_sessions"],
        "by_muscle": dict(sorted(metrics["by_muscle"].items(), key=lambda kv: -kv[1])),
        "cardio_by_activity": _cardio_activity_rows(metrics),
        "avg_duration_min": (round(sum(durations) / len(durations)) if durations else None),
        "activity_class_version": ACTIVITY_CLASS_VERSION,
        "classification": classification_quality(classification_rows),
        # 兼容别名（语义已在模块 docstring 固定）
        "sessions": metrics["training_sessions"],
        "working_sets": metrics["strength_working_sets"],
        "volume": round(metrics["strength_volume_kg"]),
        "cardio_seconds": round(metrics["steady_cardio_seconds"]),
        "cardio_distance_m": round(metrics["steady_cardio_distance_m"]),
        "interval_seconds": metrics["interval_elapsed_seconds"],
    }
