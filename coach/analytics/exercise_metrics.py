"""动作级历史与个人纪录：从 checkins 的逐组记录直接计算。

M6.3.1 统一身份解析：动作匹配直接比较"用户可见的稳定动作 ID"（内置 + 本人
自定义，与 exercise_service.get_exercise 同口径）；只有旧记录缺少 ID 时才
按名称/别名回退解析（本人自定义动作同样参与）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .. import exercise_service
from ..review import e1rm

E1RM_MAX_REPS = 12  # Epley 在低-中次数区间才相对可靠


def parse_stamp(s: str) -> datetime:
    """解析逐组完成时间（浏览器 ISO 带 Z / 服务端本地 ISO 均支持），统一为 naive UTC。"""
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def session_local_date(row_created_at: str, data: dict) -> str:
    """训练所属日期：优先会话元数据里的用户本地日期，旧记录回退服务器时间。"""
    meta = data.get("session_meta") if isinstance(data, dict) else None
    ld = meta.get("local_date") if isinstance(meta, dict) else None
    if isinstance(ld, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", ld):
        return ld
    return row_created_at[:10]


def entry_identity(db, user_id: str | None, ex: dict) -> str | None:
    """一条动作记录的身份：已验证稳定 ID 优先；旧记录按名称/别名回退解析。"""
    ex_id = ex.get("exercise_id")
    if isinstance(ex_id, str) and ex_id and exercise_service.get_exercise(db, user_id, ex_id):
        return ex_id
    name = str(ex.get("name") or "")
    got, _, _ = exercise_service.library.normalize(name)
    if got:
        return got
    n = exercise_service._norm(name)
    for doc in (db.get_custom_exercises(user_id) if user_id else []):
        if n == exercise_service._norm(str(doc.get("name") or "")) or n in {
                exercise_service._norm(a) for a in (doc.get("aliases") or [])}:
            return doc.get("id")
    return None


def _working_sets(set_logs: list) -> list[dict]:
    out = []
    for log in set_logs:
        if not isinstance(log, dict) or log.get("warmup"):
            continue
        weight, reps = log.get("weight_kg"), log.get("reps")
        est = e1rm(weight, reps) if isinstance(reps, int) and 1 <= reps <= E1RM_MAX_REPS else None
        out.append({
            "weight_kg": weight,
            "reps": reps,
            "at": log.get("at"),
            "e1rm": est,
            "volume": (weight or 0) * (reps or 0) if (weight is not None and reps) else 0,
        })
    return out


def _iter_user_training(db, user_id: str):
    """按时间倒序产出 (row, data)。坏行跳过。"""
    rows = db.conn.execute(
        "SELECT id, data, created_at FROM checkins WHERE user_id=? AND type='training'"
        " ORDER BY created_at DESC, id DESC", (user_id,)).fetchall()
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            yield row, data


def _duration_min(working: list[dict], data: dict) -> int | None:
    # 会话元数据（真实起止，含休息）优先；旧记录回退逐组完成时间跨度
    meta = data.get("session_meta") if isinstance(data.get("session_meta"), dict) else {}
    if meta.get("started_at") and meta.get("completed_at"):
        try:
            span = (parse_stamp(meta["completed_at"]) - parse_stamp(meta["started_at"])).total_seconds()
            return max(0, round(span / 60))
        except ValueError:
            pass
    stamps = sorted(parse_stamp(l["at"]) for l in working if l.get("at"))
    if len(stamps) < 2:
        return None
    return round((stamps[-1] - stamps[0]).total_seconds() / 60)


def exercise_sessions(db, user_id: str, exercise_id: str) -> list[dict]:
    """某动作的历史训练会话（新→旧），指标全部来自逐组记录。

    exercise_id 必须是用户可见动作（内置或本人自定义）；自定义动作同样可查。
    """
    if not exercise_service.get_exercise(db, user_id, exercise_id):
        return []
    sessions: list[dict] = []
    for row, data in _iter_user_training(db, user_id):
        for ex in data.get("exercises", []) or []:
            if not isinstance(ex, dict) or entry_identity(db, user_id, ex) != exercise_id:
                continue
            logs = ex.get("set_logs") if isinstance(ex.get("set_logs"), list) else []
            working = _working_sets([l for l in logs if isinstance(l, dict)])
            if not working:
                continue
            heavy = max((s for s in working if s["weight_kg"] is not None),
                        key=lambda s: s["weight_kg"], default=None)
            sessions.append({
                "checkin_id": row["id"],
                "date": session_local_date(row["created_at"], data),
                "working_sets": len(working),
                "reps_total": sum(s["reps"] or 0 for s in working),
                # 自重组（无外部负重）容量贡献 0，如实呈现
                "volume": round(sum(s["volume"] for s in working)),
                "best_set": ({"weight_kg": heavy["weight_kg"], "reps": heavy["reps"]}
                             if heavy else None),
                "best_e1rm": max((s["e1rm"] for s in working if s["e1rm"]), default=None),
                "duration_min": _duration_min(working, data),
                "sets": working,
            })
    return sessions


def personal_records(sessions: list[dict]) -> dict:
    """个人纪录：最大重量 / 最佳估算 1RM / 最多次数 / 单次训练最大容量。

    口径区分：重量纪录看绝对负重；e1RM 是模型估计（1-12 次区间）；
    次数纪录服务自重/轻负重场景；容量纪录是单次会话的总量。
    """
    heaviest = best_e1rm = max_reps = best_vol = None
    for s in sessions:
        for st in s["sets"]:
            if st["weight_kg"] is not None and (
                    heaviest is None or st["weight_kg"] > heaviest["weight_kg"]):
                heaviest = {"weight_kg": st["weight_kg"], "reps": st["reps"], "date": s["date"]}
            if st["e1rm"] is not None and (best_e1rm is None or st["e1rm"] > best_e1rm["e1rm"]):
                best_e1rm = {"e1rm": st["e1rm"], "weight_kg": st["weight_kg"],
                             "reps": st["reps"], "date": s["date"]}
            if st["reps"] and (max_reps is None or st["reps"] > max_reps["reps"]):
                max_reps = {"reps": st["reps"], "weight_kg": st["weight_kg"], "date": s["date"]}
        if best_vol is None or s["volume"] > best_vol["volume"]:
            best_vol = {"volume": s["volume"], "working_sets": s["working_sets"], "date": s["date"]}
    return {"heaviest": heaviest, "best_e1rm": best_e1rm,
            "max_reps": max_reps, "best_volume_session": best_vol}
