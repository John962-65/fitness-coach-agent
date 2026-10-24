"""训练日历与周期汇总：按日期聚合训练记录。

肌群组数口径：按动作 primary 主肌群归口，一组只记入一个肌群（不重复统计）。
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta

from ..exercises import library as exercise_lib
from .exercise_metrics import parse_stamp

_MAX_SCAN_DAYS = 400  # 周期汇总最多回看范围，防全表滥用


def _load_training_rows(db, user_id: str, since: str | None = None):
    sql = ("SELECT id, data, created_at FROM checkins WHERE user_id=? AND type='training'")
    params: list = [user_id]
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    sql += " ORDER BY created_at DESC, id DESC"
    for row in db.conn.execute(sql, params).fetchall():
        data = json.loads(row["data"])
        if isinstance(data, dict):
            yield row, data


def _iter_working_sets(data: dict):
    """产出 (exercise_doc | None, working_set)。肌群归口需要动作文档。"""
    for ex in data.get("exercises", []) or []:
        if not isinstance(ex, dict):
            continue
        logs = ex.get("set_logs") if isinstance(ex.get("set_logs"), list) else []
        doc = None
        ex_id = ex.get("exercise_id")
        if isinstance(ex_id, str):
            doc = exercise_lib.get(ex_id)
        if doc is None:
            ex_id_norm, _, _ = exercise_lib.normalize(str(ex.get("name") or ""))
            doc = exercise_lib.get(ex_id_norm) if ex_id_norm else None
        for log in logs:
            if isinstance(log, dict) and not log.get("warmup"):
                yield doc, log


def month_calendar(db, user_id: str, year: int, month: int) -> dict:
    """某月训练日历：每天的训练次数/工作组数/容量（同日多次训练合并计数）。"""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    days: dict[str, dict] = {}
    for row, data in _load_training_rows(db, user_id, since=first.isoformat()):
        day = row["created_at"][:10]
        if day > last.isoformat():
            continue
        slot = days.setdefault(day, {"date": day, "sessions": 0, "working_sets": 0, "volume": 0})
        slot["sessions"] += 1
        for _doc, log in _iter_working_sets(data):
            slot["working_sets"] += 1
            w, r = log.get("weight_kg"), log.get("reps")
            if w is not None and r:
                slot["volume"] += w * r
    return {
        "year": year, "month": month,
        "days": [days[k] for k in sorted(days)],
    }


def period_summary(db, user_id: str, days: int = 30) -> dict:
    """周期统计：训练次数 / 工作组数 / 容量 / 肌群分布 / 会话时长。"""
    days = max(1, min(int(days), _MAX_SCAN_DAYS))
    since = (datetime.now() - timedelta(days=days)).isoformat()
    sessions = 0
    working_sets = 0
    volume = 0
    by_muscle: dict[str, int] = {}
    durations: list[float] = []
    session_dates: set[str] = set()
    for row, data in _load_training_rows(db, user_id, since=since):
        sessions += 1
        session_dates.add(row["created_at"][:10])
        stamps: list[str] = []
        for doc, log in _iter_working_sets(data):
            working_sets += 1
            w, r = log.get("weight_kg"), log.get("reps")
            if w is not None and r:
                volume += w * r
            muscle = (doc.get("primary") or ["other"])[0] if doc else "other"
            by_muscle[muscle] = by_muscle.get(muscle, 0) + 1
            if log.get("at"):
                stamps.append(log["at"])
        if len(stamps) >= 2:
            span = (parse_stamp(max(stamps)) - parse_stamp(min(stamps))).total_seconds() / 60
            durations.append(span)
    return {
        "days": days,
        "sessions": sessions,
        "training_days": len(session_dates),
        "per_week": round(sessions * 7 / days, 1),
        "working_sets": working_sets,
        "volume": round(volume),
        "by_muscle": dict(sorted(by_muscle.items(), key=lambda kv: -kv[1])),
        "avg_duration_min": (round(sum(durations) / len(durations)) if durations else None),
    }
