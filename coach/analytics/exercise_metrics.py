"""动作级历史与个人纪录：从 checkins 的逐组记录直接计算。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..exercises import library as exercise_lib
from ..review import _same_exercise, e1rm

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


def _iter_exercise_checkins(db, user_id: str, exercise_id: str):
    """按时间倒序遍历训练记录，产出 (row, working_sets)。匹配规则与复盘一致（ID 优先）。"""
    lib_name = exercise_lib.get(exercise_id)["name"] if exercise_lib.get(exercise_id) else exercise_id
    rows = db.conn.execute(
        "SELECT id, data, created_at FROM checkins WHERE user_id=? AND type='training'"
        " ORDER BY created_at DESC, id DESC", (user_id,)).fetchall()
    for row in rows:
        data = json.loads(row["data"])
        if not isinstance(data, dict):
            continue
        for ex in data.get("exercises", []) or []:
            if not isinstance(ex, dict) or not _same_exercise(lib_name, ex):
                continue
            logs = ex.get("set_logs") if isinstance(ex.get("set_logs"), list) else []
            yield row, [l for l in logs if isinstance(l, dict)]


def _duration_min(working: list[dict]) -> int | None:
    stamps = sorted(parse_stamp(l["at"]) for l in working if l.get("at"))
    if len(stamps) < 2:
        return None
    return round((stamps[-1] - stamps[0]).total_seconds() / 60)


def exercise_sessions(db, user_id: str, exercise_id: str) -> list[dict]:
    """某动作的历史训练会话（新→旧），指标全部来自逐组记录。"""
    sessions: list[dict] = []
    for row, logs in _iter_exercise_checkins(db, user_id, exercise_id):
        working = _working_sets(logs)
        if not working:
            continue
        heavy = max((s for s in working if s["weight_kg"] is not None),
                    key=lambda s: s["weight_kg"], default=None)
        sessions.append({
            "checkin_id": row["id"],
            "date": row["created_at"][:10],
            "working_sets": len(working),
            "reps_total": sum(s["reps"] or 0 for s in working),
            # 自重组（无外部负重）容量贡献 0，如实呈现
            "volume": round(sum(s["volume"] for s in working)),
            "best_set": ({"weight_kg": heavy["weight_kg"], "reps": heavy["reps"]}
                         if heavy else None),
            "best_e1rm": max((s["e1rm"] for s in working if s["e1rm"]), default=None),
            "duration_min": _duration_min(working),
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
