"""训练日历与周期汇总：按日期聚合训练记录。

口径（M6.3.1 修订）：
- 训练所属日期 = 会话元数据的用户本地日期（session_meta.local_date），
  旧记录回退服务器时间；
- 肌群归口按动作 primary 主肌群（内置 + 本人自定义统一解析），一组只记一次。
"""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta

from .exercise_metrics import entry_identity, parse_stamp, session_local_date

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


def _iter_working_sets(db, user_id: str, data: dict):
    """产出 (动作文档 | None, working_set)。文档按用户可见动作统一解析。"""
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
                yield doc, log


def month_calendar(db, user_id: str, year: int, month: int) -> dict:
    """某月训练日历：每天的训练次数/工作组数/容量（同日多次合并计数）。"""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    # 会话本地日期可能与服务端日期跨日（临近午夜），回看缓冲 1 天
    since = (first - timedelta(days=1)).isoformat()
    days: dict[str, dict] = {}
    for row, data in _load_training_rows(db, user_id, since=since):
        day = session_local_date(row["created_at"], data)
        if day < first.isoformat() or day > last.isoformat():
            continue
        slot = days.setdefault(day, {"date": day, "sessions": 0, "working_sets": 0, "volume": 0})
        slot["sessions"] += 1
        for _doc, log in _iter_working_sets(db, user_id, data):
            slot["working_sets"] += 1
            w, r = log.get("weight_kg"), log.get("reps")
            if w is not None and r:
                slot["volume"] += w * r
    return {
        "year": year, "month": month,
        "days": [days[k] for k in sorted(days)],
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
    """周期统计：训练次数 / 工作组数 / 容量 / 肌群分布 / 会话时长。

    会话时长优先使用 session_meta（真实起止，含休息）；旧记录回退逐组时间跨度。
    """
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
        session_dates.add(session_local_date(row["created_at"], data))
        stamps: list[str] = []
        for doc, log in _iter_working_sets(db, user_id, data):
            working_sets += 1
            w, r = log.get("weight_kg"), log.get("reps")
            if w is not None and r:
                volume += w * r
            muscle = (doc.get("primary") or ["other"])[0] if doc else "other"
            by_muscle[muscle] = by_muscle.get(muscle, 0) + 1
            if log.get("at"):
                stamps.append(log["at"])
        duration = _session_duration_min(data, stamps)
        if duration is not None:
            durations.append(duration)
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
