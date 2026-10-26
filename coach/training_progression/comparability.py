"""P5-C：训练记录可比性判定。

recent ≠ comparable：
- recent 是近期真实记录，任何记录都可展示；
- comparable 必须通过记录类别、测量口径、训练方法、左右侧完整性、
  超级组组织和 HIIT 编排检查，才可用于同口径比较。

P5-C1.1 边界：结构可比与目标达成情况分离——
- 未达到目标次数的记录不因此被排除出结构可比集合（结构相同才谈得上
  "差多少"）；目标达成情况作为独立分类随上下文输出；
- 加重等"完成标准"判断仍由候选规则基于达成分类显式把关；
- HIIT 签名包含动作/自定义活动身份与顺序：不同活动即使计时编排相同，
  也不得默认可比。
"""
from __future__ import annotations

import re

from ..exercises import CUSTOM_HIIT_EXERCISE_ID

REP_MEASUREMENTS = {"weight_reps", "bodyweight_reps", "assisted_reps"}
CLASS_MIXED = "mixed"
DURATION_RE = re.compile(r"^(\d{1,4})\s*(秒|分|分钟)$")
RANGE_RE = re.compile(r"^(\d{1,3})\s*-\s*(\d{1,3})$")

# 目标达成分类（P5-C1.1）：候选规则与展示层共用的固定词表
ATTAINMENT_LEVELS = ("at_top", "met_min", "below_target", "above_range",
                     "insufficient_data")
ATTAINMENT_LABELS = {
    "at_top": "达到目标次数上沿",
    "met_min": "达到目标次数下沿",
    "below_target": "低于目标次数",
    "above_range": "超出目标范围",
    "insufficient_data": "数据不足",
}


def parse_target(value) -> dict | None:
    """计划目标 → {kind: reps|duration, min,max/seconds, raw}。"""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if float(value).is_integer() and value >= 1:
            return {"kind": "reps", "min": int(value), "max": int(value),
                    "raw": value}
        return None
    text = str(value).strip()
    if text.isdigit():
        n = int(text)
        return {"kind": "reps", "min": n, "max": n, "raw": value} if n >= 1 else None
    m = RANGE_RE.match(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return {"kind": "reps", "min": lo, "max": hi,
                "raw": text.replace(" ", "")} if 1 <= lo <= hi else None
    m = DURATION_RE.match(text)
    if m:
        seconds = int(m.group(1)) * (60 if m.group(2) in ("分", "分钟") else 1)
        return {"kind": "duration", "seconds": seconds,
                "raw": text.replace(" ", "")}
    return None


def plan_prescription(entry: dict | None, measurement_type: str) -> dict:
    if not isinstance(entry, dict):
        return {}
    out = {}
    sets = entry.get("sets")
    if isinstance(sets, (int, float)) and not isinstance(sets, bool) \
            and float(sets).is_integer() and sets > 0:
        out["sets"] = int(sets)
    target = parse_target(entry.get("reps"))
    if target:
        out["reps_target"] = target
        out["reps"] = target["raw"]
        out["reps_min"] = target.get("min")
        out["reps_max"] = target.get("max")
    if entry.get("weight_kg") is not None:
        try:
            out["weight_kg"] = float(entry["weight_kg"])
        except (TypeError, ValueError):
            pass
    if entry.get("note"):
        out["note"] = str(entry["note"])
    out["measurement_type"] = measurement_type
    return out


def _strength_sets(session: dict) -> list[dict]:
    return [s for s in session.get("sets") or []
            if s.get("activity_class") == "strength"]


def _hiit_block_identity(block: dict) -> str:
    """块的稳定身份：已验证动作 ID 优先；自定义活动用名称身份。

    routes 保存时会把无法解析的块 exercise_id 重置为 custom_hiit，
    此时块名是唯一的自定义活动身份（归一大小写/空白后参与签名）。
    """
    bid = block.get("exercise_id")
    if isinstance(bid, str) and bid and bid != CUSTOM_HIIT_EXERCISE_ID:
        return str(bid)
    name = str(block.get("name") or "").strip().lower()
    return f"custom:{name}"


def _hiit_signature(session: dict) -> tuple | None:
    """HIIT 签名：动作/自定义身份 + 顺序 + 工作/休息/轮次（P5-C1.1）。"""
    hiit = next((s.get("hiit") for s in session.get("sets") or []
                 if isinstance(s.get("hiit"), dict)), None)
    if not hiit:
        return None
    return tuple(
        (_hiit_block_identity(b), b.get("work_seconds"),
         b.get("rest_seconds"), b.get("rounds"))
        for b in hiit.get("blocks") or [] if isinstance(b, dict))


def _hiit_diff_reason(reference_sig, candidate_sig) -> str:
    ref_ident = tuple(t[0] for t in (reference_sig or ()))
    cand_ident = tuple(t[0] for t in (candidate_sig or ()))
    if ref_ident == cand_ident:
        return "HIIT 计时编排（工作/休息/轮次）不同"
    return ("HIIT 动作身份或顺序不同：不同活动即使计时编排相同，"
            "也不可直接比较运动表现")


def session_profile(session: dict) -> dict:
    sets = session.get("sets") or []
    methods = sorted({s.get("method") or "straight_set" for s in sets
                      if s.get("activity_class") == "strength"})
    sides = sorted({seg.get("side") for s in sets for seg in (
        s.get("segments") or []) if isinstance(seg, dict) and seg.get("side")})
    superset = any(bool(s.get("superset_group")) for s in sets) \
        or bool(session.get("superset_group"))
    types = sorted({s.get("type") or "weight_reps" for s in sets})
    return {
        "activity_classes": sorted(session.get("activity_classes") or []),
        "measurement_types": types,
        "methods": methods,
        "sides": sides,
        "superset": superset,
        "hiit_signature": _hiit_signature(session),
    }


def comparable_with(reference: dict, candidate: dict,
                    target_class: str) -> tuple[bool, list[str]]:
    """结构可比判断（P5-C1.1：不再把目标次数范围作为可比前提）。

    目标达成情况是独立维度（见 target_attainment）；这里只回答
    "两条记录是不是同一种训练"。
    """
    reasons: list[str] = []
    rp = session_profile(reference)
    cp = session_profile(candidate)
    if (candidate.get("duplicate_entries") or 1) > 1:
        reasons.append("同一训练内该动作重复出现，无法作为单次会话比较")
    if CLASS_MIXED in cp["activity_classes"] or len(cp["activity_classes"]) != 1:
        reasons.append("记录混有多个活动类别")
    if cp["activity_classes"] != [target_class]:
        reasons.append(f"活动类别为 {cp['activity_classes']}，目标为 {target_class}")
    if cp["measurement_types"] != rp["measurement_types"]:
        reasons.append("测量类型不同")
    if cp["methods"] != rp["methods"]:
        reasons.append("训练方法/复杂组结构不同")
    if cp["superset"] != rp["superset"]:
        reasons.append("超级组执行组织不同")
    if cp["hiit_signature"] != rp["hiit_signature"]:
        reasons.append(_hiit_diff_reason(rp["hiit_signature"],
                                         cp["hiit_signature"]))
    if target_class == "strength":
        sets = _strength_sets(candidate)
        if not sets:
            reasons.append("没有力量工作组")
        if "unilateral" in cp["methods"]:
            if set(cp["sides"]) != {"left", "right"}:
                reasons.append("单侧记录左右侧不完整")
    return (not reasons), reasons


def target_attainment(session: dict, target: dict | None) -> dict:
    """结构可比会话相对当前计划目标的达成分类（P5-C1.1）。

    分类至少区分：达到上沿 / 达到下沿 / 低于目标 / 超出目标范围 /
    数据不足。这是展示与规则的输入，不是执行记录的改写。
    """
    out: dict = {"level": "insufficient_data",
                 "label": ATTAINMENT_LABELS["insufficient_data"]}
    if not target:
        out["note"] = "没有可用的计划目标，无法分类目标达成情况"
        return out
    if target["kind"] == "reps":
        reps = [s.get("reps") for s in _strength_sets(session)]
        if not reps or any(not isinstance(r, int) for r in reps):
            out["note"] = "没有完整的工作组次数记录"
            return out
        out.update({"reps": reps, "target_min": target["min"],
                    "target_max": target["max"]})
        if all(r > target["max"] for r in reps):
            level = "above_range"
        elif all(r >= target["max"] for r in reps):
            level = "at_top"
        elif all(r >= target["min"] for r in reps):
            level = "met_min"
        else:
            level = "below_target"
        out["level"] = level
        out["label"] = ATTAINMENT_LABELS[level]
        if level == "met_min" and any(r > target["max"] for r in reps):
            out["note"] = "部分组超出目标范围上沿"
        elif level == "below_target":
            above = any(r > target["max"] for r in reps)
            if above:
                out["note"] = "部分组超出目标范围上沿、部分组低于下沿"
            elif any(r >= target["min"] for r in reps):
                out["note"] = "部分组在目标范围内、部分组低于下沿"
        return out
    if target["kind"] == "duration":
        seconds = [s.get("duration_seconds") for s in _strength_sets(session)
                   if isinstance(s.get("duration_seconds"), (int, float))]
        if not seconds:
            out["note"] = "没有可核实的保持时长记录"
            return out
        out.update({"durations_s": seconds, "target_seconds": target["seconds"]})
        level = "at_top" if all(d >= target["seconds"] for d in seconds) \
            else "below_target"
        out["level"] = level
        out["label"] = ("达到目标时长" if level == "at_top" else "低于目标时长")
        return out
    out["note"] = "该目标类型没有通用的达成分类口径"
    return out


def select_comparable(recent: list[dict],
                      target_class: str) -> tuple[list[dict], dict]:
    """以最近一条可用记录为结构参照，返回结构可比会话与排除原因。

    P5-C1.1：未达目标次数的会话只要结构相同就保持可比；
    目标达成情况由 target_attainment 单独给出。
    """
    if not recent:
        return [], {}
    reference = next(
        (s for s in recent
         if len(s.get("activity_classes") or []) == 1
         and (s.get("activity_classes") or [None])[0] == target_class),
        recent[0])
    out, excluded = [], {}
    for session in recent:
        ok, reasons = comparable_with(reference, session, target_class)
        if ok:
            out.append(session)
        else:
            excluded[str(session.get("checkin_id"))] = reasons
    return out, excluded


def strength_completion(session: dict, target: dict | None,
                        target_sets: int | None = None) -> dict:
    sets = _strength_sets(session)
    reps = [s.get("reps") for s in sets if isinstance(s.get("reps"), int)]
    rpes = [s.get("rpe") for s in sets
            if isinstance(s.get("rpe"), (int, float))]
    loads = [s.get("weight_kg") for s in sets
             if isinstance(s.get("weight_kg"), (int, float))]
    assisted = [s.get("assistance_kg") for s in sets
                if isinstance(s.get("assistance_kg"), (int, float))]
    added = [s.get("added_weight_kg") for s in sets
             if isinstance(s.get("added_weight_kg"), (int, float))]
    enough_sets = target_sets is None or len(sets) >= target_sets
    if target and target["kind"] == "reps":
        all_at_high = bool(reps) and enough_sets and all(
            r >= target["max"] for r in reps)
        met_min = bool(reps) and enough_sets and all(
            r >= target["min"] for r in reps)
    else:
        all_at_high = met_min = False
    return {
        "sets": len(sets),
        "reps": reps,
        "rpes": rpes,
        "rpe_high": any(r >= 8 for r in rpes),
        "rpe_missing": len(rpes) < len(sets),
        "loads": loads,
        "assistance": assisted,
        "added_weight": added,
        "uniform_load": len(set(loads)) == 1 if loads else False,
        "uniform_assistance": len(set(assisted)) == 1 if assisted else False,
        "uniform_added_weight": len(set(added)) == 1 if added else False,
        "all_at_high": all_at_high,
        "met_min": met_min,
        "enough_sets": enough_sets,
        "has_complex": any((s.get("method") or "straight_set") != "straight_set"
                           for s in sets),
        "superset": any(bool(s.get("superset_group")) for s in sets)
                    or bool(session.get("superset_group")),
    }


def performance_summary(session: dict) -> dict:
    """仅从实际记录生成可展示摘要，不补计划值。"""
    classes = session.get("activity_classes") or []
    out = {
        "checkin_id": session.get("checkin_id"),
        "revision": session.get("revision") or 0,
        "date": session.get("date"),
        "activity_classes": classes,
        "working_sets": session.get("working_sets", 0),
        "rep_values": [s.get("reps") for s in _strength_sets(session)
                       if isinstance(s.get("reps"), int)],
        "rpe_values": [s.get("rpe") for s in session.get("sets") or []
                       if isinstance(s.get("rpe"), (int, float))],
        "best_set": session.get("best_set"),
        "best_e1rm": session.get("best_e1rm"),
        "steady_cardio_seconds": session.get("steady_cardio_seconds"),
        "steady_cardio_distance_m": session.get("steady_cardio_distance_m"),
        "interval_work_seconds": session.get("interval_work_seconds"),
        "interval_rest_seconds": session.get("interval_rest_seconds"),
        "interval_elapsed_seconds": session.get("interval_elapsed_seconds"),
        "interval_planned_rounds": session.get("interval_planned_rounds"),
        "interval_completed_rounds": session.get("interval_completed_rounds"),
        "interval_skipped_rounds": session.get("interval_skipped_rounds"),
        "interval_ended_early": any(
            bool((st.get("hiit") or {}).get("ended_early"))
            for st in session.get("sets") or []),
        "superset_group": session.get("superset_group"),
        "replacement": session.get("replacement"),
        "sets": session.get("sets") or [],
    }
    seconds = session.get("steady_cardio_seconds")
    distance = session.get("steady_cardio_distance_m")
    if seconds and distance:
        out["pace_sec_per_km"] = round(seconds / (distance / 1000), 1)
        out["speed_mps"] = round(distance / seconds, 3)
    else:
        out["pace_sec_per_km"] = None
        out["speed_mps"] = None
    return out
