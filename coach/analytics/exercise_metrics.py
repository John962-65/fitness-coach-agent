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
from .activity_class import (
    ACTIVITY_CLASS_VERSION, CLASS_INTERVAL, CLASS_STRENGTH,
    classify_training_record, classification_quality,
)

E1RM_MAX_REPS = 12  # Epley 在低-中次数区间才相对可靠


def set_volume(log: dict) -> int:
    """单组容量（kg）——全站唯一公式：
    weight_reps = 负重×次数；bodyweight_reps = 额外负重×次数（自重不可比，不计入）；
    assisted_reps / duration / distance_time 不产生 kg 容量。
    P5-A：复杂组（method+segments）容量 = 各执行段按同公式求和——
    一个逻辑组仍计一次（工作组数不按段重复），容量反映实际完成总量。
    """
    segs = log.get("segments")
    if log.get("method") in ("drop_set", "rest_pause", "unilateral")             and isinstance(segs, list) and segs:
        return int(sum(_segment_volume(seg, log.get("type") or "weight_reps")
                       for seg in segs))
    t = log.get("type") or "weight_reps"
    if t not in ("weight_reps", "bodyweight_reps"):
        return 0
    r = log.get("reps")
    if not r:
        return 0
    w = log.get("weight_kg") if t == "weight_reps" else log.get("added_weight_kg")
    return int((w or 0) * r)


def _segment_volume(seg: dict, t: str) -> int:
    """执行段容量（与主组同公式；无有效次数的段计 0）。"""
    r = seg.get("reps")
    if not r:
        return 0
    if t == "bodyweight_reps":
        return int((seg.get("added_weight_kg") or 0) * r)
    if t == "weight_reps":
        return int((seg.get("weight_kg") or 0) * r)
    return 0


def set_e1rm(log: dict, max_reps: int = E1RM_MAX_REPS):
    """单组估算 1RM——仅 weight_reps 类型在 1-12 次区间计算；
    bodyweight/assisted/duration/distance 不适用该口径（返回 None）。
    P5-A：复杂组取各段中最大的有效 e1RM（同口径）。"""
    t = log.get("type") or "weight_reps"
    if t != "weight_reps":
        return None
    if log.get("method") in ("drop_set", "rest_pause", "unilateral")             and isinstance(log.get("segments"), list):
        best = None
        for seg in log["segments"]:
            reps = seg.get("reps")
            if isinstance(reps, int) and 1 <= reps <= max_reps                     and seg.get("weight_kg"):
                score = e1rm(seg["weight_kg"], reps)
                if score is not None and (best is None or score > best):
                    best = score
        return best
    reps = log.get("reps")
    if not isinstance(reps, int) or not (1 <= reps <= max_reps):
        return None
    return e1rm(log.get("weight_kg"), reps)


def entry_set_type(logs) -> str | None:
    """一条动作记录的逐组类型（首个正式组；无 type 返回 None=旧记录 weight_reps 口径）。"""
    if not isinstance(logs, list):
        return None
    for l in logs:
        if isinstance(l, dict) and not l.get("warmup"):
            return l.get("type") or "weight_reps"
    return None


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


def _working_sets(set_logs: list, doc: dict | None = None) -> list[dict]:
    """逐组记录：在测量类型字段之外附加统一活动类别。"""
    out = []
    for log in set_logs:
        if not isinstance(log, dict) or log.get("warmup"):
            continue
        method = log.get("method")
        segs = log.get("segments")             if method in ("drop_set", "rest_pause", "unilateral") else None
        cls = classify_training_record(doc, log)
        entry = {
            "type": log.get("type") or "weight_reps",
            "method": method or "straight_set",
            "segments": segs,
            "weight_kg": log.get("weight_kg"),
            "reps": log.get("reps"),
            "at": log.get("at"),
            "e1rm": set_e1rm(log),
            "volume": set_volume(log),
            "duration_seconds": log.get("duration_seconds"),
            "distance_m": log.get("distance_m"),
            "added_weight_kg": log.get("added_weight_kg"),
            "assistance_kg": log.get("assistance_kg"),
            "rpe": log.get("rpe"),
            "hiit": log.get("hiit"),
            "activity_class": cls["class"],
            "activity_class_source": cls["source"],
            "activity_class_version": ACTIVITY_CLASS_VERSION,
        }
        if segs:
            # 复杂组：主级字段=代表段（容量最大段）；总次数=各段和
            # （reps_total 用它；best_set 取代表段；逻辑组仍计 1）
            best_seg = max(segs, key=lambda g: _segment_volume(
                g, log.get("type") or "weight_reps"), default=None)
            entry["reps"] = sum(g.get("reps") or 0 for g in segs)
            if best_seg:
                if entry["type"] == "weight_reps":
                    entry["weight_kg"] = best_seg.get("weight_kg")
                elif entry["type"] == "bodyweight_reps":
                    entry["added_weight_kg"] = best_seg.get("added_weight_kg")
        out.append(entry)
    return out


def _iter_user_training(db, user_id: str):
    """按时间倒序产出 (row, data)。坏行跳过。"""
    rows = db.conn.execute(
        "SELECT id, data, created_at,"
        " (SELECT COUNT(*) FROM checkin_revisions r WHERE r.checkin_id=checkins.id)"
        " AS revision FROM checkins WHERE user_id=? AND type='training'"
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
            doc = exercise_service.get_exercise(db, user_id, exercise_id)
            working = _working_sets([l for l in logs if isinstance(l, dict)], doc)
            if not working:
                continue
            strength = [s for s in working if s["activity_class"] == CLASS_STRENGTH]
            intervals = [s for s in working if s["activity_class"] == CLASS_INTERVAL]
            classes = sorted({s["activity_class"] for s in working})
            heavy = max((s for s in strength if s["weight_kg"] is not None),
                        key=lambda s: s["weight_kg"], default=None)
            dur_sets = [s for s in working if s["type"] == "duration"
                        and s["duration_seconds"]]
            steady_dur = [s for s in dur_sets
                          if s["activity_class"] != CLASS_INTERVAL]
            dist_sets = [s for s in working if s["type"] == "distance_time"
                         and s["distance_m"]]
            work_seconds = sum(int((s.get("hiit") or {}).get("work_seconds_done") or 0)
                               for s in intervals)
            rest_seconds = sum(int((s.get("hiit") or {}).get("rest_seconds_done") or 0)
                               for s in intervals)
            interval_elapsed = sum(int(s.get("duration_seconds") or 0)
                                   for s in intervals)
            replacement = ex.get("session_replacement") \
                if isinstance(ex.get("session_replacement"), dict) else None
            if not replacement and ex.get("session_replacement_of"):
                replacement = {"planned_exercise_id": ex.get("session_replacement_of"),
                               "scope": "session"}
            sessions.append({
                "checkin_id": row["id"],
                "revision": row["revision"],
                "date": session_local_date(row["created_at"], data),
                "activity_class": classes[0] if len(classes) == 1 else "mixed",
                "activity_classes": classes,
                "classification": classification_quality(working),
                "strength_working_sets": len(strength),
                "reps_total": sum(s["reps"] or 0 for s in strength),
                # 兼容字段：working_sets/volume 现在明确只表示力量口径
                "working_sets": len(strength),
                "volume": round(sum(s["volume"] for s in strength)),
                "best_set": ({"weight_kg": heavy["weight_kg"], "reps": heavy["reps"]}
                             if heavy else None),
                "best_e1rm": max((s["e1rm"] for s in strength if s["e1rm"]),
                                 default=None),
                "interval_work_seconds": work_seconds,
                "interval_rest_seconds": rest_seconds,
                "interval_elapsed_seconds": interval_elapsed,
                "interval_planned_rounds": sum(
                    int((s.get("hiit") or {}).get("planned_rounds") or 0)
                    for s in intervals),
                "interval_completed_rounds": sum(
                    int((s.get("hiit") or {}).get("completed_rounds") or 0)
                    for s in intervals),
                "interval_skipped_rounds": sum(
                    len((s.get("hiit") or {}).get("skipped") or []) for s in intervals),
                "duration_total_s": round(sum(s["duration_seconds"] or 0 for s in dur_sets))
                                    if dur_sets else None,
                "steady_cardio_seconds": round(sum(
                    s["duration_seconds"] or 0 for s in working
                    if s["activity_class"] != CLASS_STRENGTH
                    and s["activity_class"] != CLASS_INTERVAL)) or None,
                "steady_cardio_distance_m": round(sum(
                    s["distance_m"] or 0 for s in dist_sets)) or None,
                # 单组表现只取非间歇记录；HIIT 使用 interval_* 指标
                "longest_set_s": max((s["duration_seconds"] for s in steady_dur),
                                     default=None),
                "distance_total_m": round(sum(s["distance_m"] or 0 for s in dist_sets))
                                    if dist_sets else None,
                "farthest_set_m": max((s["distance_m"] for s in dist_sets),
                                      default=None),
                "duration_min": _duration_min(working, data),
                "actual_measurement": (working[0].get("type") or "weight_reps"),
                "replacement": replacement,
                "sets": working,
            })
    return sessions


def personal_records(sessions: list[dict]) -> dict:
    """个人纪录：最大重量 / 最佳估算 1RM / 最多次数 / 单次训练最大容量。

    口径区分：重量纪录看绝对负重；e1RM 是模型估计（1-12 次区间）；
    次数纪录服务自重/轻负重场景；容量纪录是单次会话的总量。
    """
    heaviest = best_e1rm = max_reps = best_vol = None
    longest = farthest = None
    for s in sessions:
        for st in s["sets"]:
            if st["weight_kg"] is not None and (
                    heaviest is None or st["weight_kg"] > heaviest["weight_kg"]):
                heaviest = {"weight_kg": st["weight_kg"], "reps": st["reps"], "date": s["date"]}
            if st["e1rm"] is not None and (best_e1rm is None or st["e1rm"] > best_e1rm["e1rm"]):
                best_e1rm = {"e1rm": st["e1rm"], "weight_kg": st["weight_kg"],
                             "reps": st["reps"], "date": s["date"]}
            is_strength = st.get("activity_class") == CLASS_STRENGTH
            if is_strength and st["reps"] and (
                    max_reps is None or st["reps"] > max_reps["reps"]):
                max_reps = {"reps": st["reps"], "weight_kg": st["weight_kg"], "date": s["date"]}
            if st.get("activity_class") != CLASS_INTERVAL \
                    and st["duration_seconds"] and (longest is None
                                                    or st["duration_seconds"] > longest["duration_seconds"]):
                longest = {"duration_seconds": st["duration_seconds"], "date": s["date"]}
            if st["distance_m"] and (farthest is None or st["distance_m"] > farthest["distance_m"]):
                farthest = {"distance_m": st["distance_m"], "date": s["date"]}
        if s.get("strength_working_sets", s["working_sets"]) > 0 and (
                best_vol is None or s["volume"] > best_vol["volume"]):
            best_vol = {"volume": s["volume"],
                        "working_sets": s.get("strength_working_sets", s["working_sets"]),
                        "date": s["date"]}
    return {"heaviest": heaviest, "best_e1rm": best_e1rm,
            "max_reps": max_reps, "best_volume_session": best_vol,
            "longest_set": longest, "farthest": farthest}
