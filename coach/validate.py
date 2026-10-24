"""落库前数据校验与强转（设计书 17.2 D1/D2：数据契约）

原则：能强转的强转（"84.5kg"→84.5、"5x5"→5），转不了的丢弃并报告，
绝不让坏数据进库后在复盘/定级时炸出来。
"""
from __future__ import annotations

import copy
import math
import re


def round_half(x: float) -> float:
    """取整到 0.5kg（处方重量最小刻度）"""
    return round(x * 2) / 2


def _to_number(v) -> float | None:
    """数字或含数字的字符串 → float；失败返回 None。

    中国用户报体重/重量经常用"斤"："150斤"是 75kg，不是 150kg——
    带"斤"的字符串按 1 斤 = 0.5 kg 换算（否则体重、三大项、定级全被翻倍）。
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            n = float(v)
        except OverflowError:
            return None
        return n if math.isfinite(n) else None
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            n = float(m.group())
            # "150斤"→75kg；但"公斤"里的"斤"不算（"84.5公斤"=84.5kg）
            if "斤" in v and "公斤" not in v:
                n *= 0.5
            return n if math.isfinite(n) else None
    return None


def _to_reps(v) -> int | None:
    """次数强转：5 → 5；"5" → 5；"5x5"/"5×5" → 5（取末段）；[5,5,5] → 5（取最好）"""
    if isinstance(v, list):
        nums = [_to_number(x) for x in v]
        nums = [n for n in nums if n is not None and n > 0]
        return int(max(nums)) if nums else None
    if isinstance(v, str) and re.search(r"[x×*]", v):
        parts = re.split(r"[x×*]", v)
        return _to_reps(parts[-1])
    n = _to_number(v)
    return int(n) if n is not None and n >= 1 and n.is_integer() else None


def coerce_checkin(type_: str, data) -> tuple[dict, list[str]]:
    """打卡落库前清洗。返回 (清洗后数据, 警告列表)。坏行剔除并说明。"""
    warnings: list[str] = []
    if not isinstance(data, dict):
        return {"raw": str(data)[:200]}, ["数据不是结构化对象，已按原文保存"]

    out = dict(data)
    if type_ == "training":
        clean_exs = []
        exercises = data.get("exercises") or []
        if not isinstance(exercises, list):
            warnings.append("exercises 必须是动作列表，已按原文保存")
            out["raw"] = out.get("raw") or str(data)[:200]
            exercises = []
        for ex in exercises:
            if not isinstance(ex, dict) or not isinstance(ex.get("name"), str) or not ex["name"].strip():
                warnings.append("一条动作记录缺少动作名，已跳过")
                continue
            ex = dict(ex)
            for field in ("weight_kg", "rpe"):
                if ex.get(field) is not None:
                    n = _to_number(ex[field])
                    if n is None or n < 0 or (field == "rpe" and not 0 <= n <= 10):
                        warnings.append(f"{ex['name']} 的 {field}={ex[field]!r} 无法识别，已丢弃该字段")
                        ex.pop(field)
                    else:
                        ex[field] = n
            for field in ("sets", "reps"):
                if ex.get(field) is not None:
                    n = _to_reps(ex[field])
                    if n is None:
                        warnings.append(f"{ex['name']} 的 {field}={ex[field]!r} 无法识别，已丢弃该字段")
                        ex.pop(field)
                    else:
                        ex[field] = n
            # M1.1 P0-4：逐组记录 set_logs——每组单独清洗（重量/次数/RPE/热身），
            # 坏组剔除并说明；聚合字段（sets/weight_kg/reps/rpe）由服务端从正式组派生。
            if ex.get("set_logs") is not None:
                logs = ex["set_logs"]
                clean_logs = []
                if isinstance(logs, list):
                    for s in logs[:50]:
                        if not isinstance(s, dict):
                            warnings.append(f"{ex['name']} 的一条逐组记录不是对象，已跳过")
                            continue
                        s = dict(s)
                        bad = False
                        # M6.4-A：类型化逐组记录——type 决定本组的本质量字段；
                        # 未带 type 的旧记录按 weight_reps 处理（向后兼容）。
                        if s.get("type") is not None and s["type"] not in (
                                "weight_reps", "bodyweight_reps", "assisted_reps",
                                "duration", "distance_time"):
                            warnings.append(f"{ex['name']} 某组的记录类型 {s['type']!r} 无法识别，该组剔除")
                            continue
                        for field in ("added_weight_kg", "assistance_kg",
                                      "distance_m", "duration_seconds"):
                            if s.get(field) is not None:
                                n = _to_number(s[field])
                                if n is None or n < 0:
                                    warnings.append(f"{ex['name']} 某组的 {field}={s[field]!r} 无法识别，已丢弃该字段")
                                    s.pop(field)
                                else:
                                    s[field] = n
                        for field in ("weight_kg", "rpe"):
                            if s.get(field) is not None:
                                n = _to_number(s[field])
                                if n is None or n < 0 or (field == "rpe" and not 0 <= n <= 10):
                                    if field == "weight_kg":
                                        warnings.append(f"{ex['name']} 某组的重量={s[field]!r} 无法识别，该组剔除")
                                        bad = True  # 声称有重量却识别不了：不能静默变成徒手组
                                    else:
                                        warnings.append(f"{ex['name']} 某组的 RPE={s[field]!r} 无法识别，已丢弃该字段")
                                        s.pop(field)
                                else:
                                    s[field] = n
                        if s.get("reps") is not None:
                            n = _to_number(s["reps"])
                            if n is None or n < 1 or not float(n).is_integer():
                                warnings.append(f"{ex['name']} 某组的次数={s['reps']!r} 无法识别，该组剔除")
                                continue  # 次数是组的本质量：无法识别则整组无意义
                            s["reps"] = int(n)
                        if not isinstance(s.get("warmup"), bool):
                            s.pop("warmup", None)
                        if bad:
                            continue
                        # M6.4-A.1：按记录类型校验必填字段——缺本质量字段的组剔除，
                        # 不允许"丢字段后继续入库"（数据可能来自离线恢复/API/导入）
                        t = s.get("type") or "weight_reps"
                        if t == "duration" and not s.get("duration_seconds"):
                            warnings.append(f"{ex['name']} 某组时长记录缺少时长，该组剔除")
                            continue
                        if t == "distance_time" and (not s.get("distance_m")
                                                     or not s.get("duration_seconds")):
                            warnings.append(f"{ex['name']} 某组距离记录缺少距离或用时，该组剔除")
                            continue
                        if t == "assisted_reps" and not s.get("assistance_kg"):
                            warnings.append(f"{ex['name']} 某组辅助记录缺少辅助重量，该组剔除")
                            continue
                        if t in ("weight_reps", "bodyweight_reps") and not s.get("reps"):
                            warnings.append(f"{ex['name']} 某组缺少次数，该组剔除")
                            continue
                        clean_logs.append(s)
                else:
                    warnings.append(f"{ex['name']} 的 set_logs 必须是列表，已丢弃")
                ex["set_logs"] = clean_logs
            clean_exs.append(ex)
        out["exercises"] = clean_exs
        if not clean_exs and data.get("exercises"):
            warnings.append("所有动作记录都无法识别，已按原文保存 raw")
            out["raw"] = out.get("raw") or str(data)[:200]

    if type_ == "body":
        for field in ("weight_kg", "waist_cm"):
            if data.get(field) is not None:
                n = _to_number(data[field])
                if n is None or n <= 0:
                    warnings.append(f"{field}={data[field]!r} 无法识别，已丢弃")
                    out.pop(field, None)
                else:
                    out[field] = n
    return out, warnings


# ---- 档案 patch 类型强转（D2）：LLM 写 "130kg" 不能让定级崩 ----

_NUM_PROFILE_FIELDS = {
    ("basic", "age"), ("basic", "height_cm"), ("basic", "weight_kg"),
    ("experience", "training_years"), ("experience", "recent_layoff_weeks"),
    ("resources", "days_per_week"), ("resources", "session_minutes"),
    ("nutrition", "meals_per_day"), ("nutrition", "sleep_hours"),
}


def coerce_profile_patch(patch: dict) -> tuple[dict, list[str]]:
    """档案 patch 数字字段强转。返回 (清洗后 patch, 警告列表)。"""
    warnings: list[str] = []
    if not isinstance(patch, dict):
        return {}, ["patch 不是对象，已整体忽略"]
    out = copy.deepcopy(patch)

    for sec, key in _NUM_PROFILE_FIELDS:
        sec_d = out.get(sec)
        if not isinstance(sec_d, dict) or key not in sec_d:
            continue
        n = _to_number(sec_d[key])
        integer = key in {"age", "recent_layoff_weeks", "days_per_week", "session_minutes", "meals_per_day"}
        lo, hi = {
            "days_per_week": (1, 7), "sleep_hours": (0, 24),
            "training_years": (0, None), "recent_layoff_weeks": (0, None),
        }.get(key, (0, None))
        valid = (n is not None and n >= lo and (hi is None or n <= hi)
                 and (key in {"training_years", "recent_layoff_weeks", "sleep_hours"} or n > 0)
                 and (not integer or n.is_integer()))
        if not valid:
            warnings.append(f"{sec}.{key}={sec_d[key]!r} 不是有效范围内的数字，已丢弃")
            del sec_d[key]
        else:
            sec_d[key] = int(n) if n == int(n) else n

    experience = out.get("experience")
    big3 = experience.get("big3") if isinstance(experience, dict) else None
    if isinstance(experience, dict) and "big3" in experience and not isinstance(big3, dict):
        warnings.append("experience.big3 必须是对象，已丢弃")
        del experience["big3"]
    if isinstance(big3, dict):
        for lift in list(big3):
            n = _to_number(big3[lift])
            if lift not in {"squat", "bench", "deadlift"} or n is None or n < 0:
                warnings.append(f"big3.{lift}={big3[lift]!r} 不是数字，已丢弃")
                del big3[lift]
            else:
                big3[lift] = n
    # 容器和文本也要校验，防止脏值落库后每次启动都崩溃（D1/D2/G1）。
    text_fields = {
        "basic": {"name", "gender"},
        "goal": {"primary", "phase", "target", "secondary", "timeline"},
        "resources": {"location"},
        "conditions": {"injuries_evidence", "health_screen_evidence"},
    }
    from .goals import SUPPORTED_GOALS
    for section, fields in text_fields.items():
        values = out.get(section)
        if not isinstance(values, dict):
            continue
        for field in fields & values.keys():
            value = values[field]
            valid = isinstance(value, str)
            if field == "primary":
                valid = valid and value in SUPPORTED_GOALS
            if field == "location":
                valid = valid and value in {"gym", "home"}
            if not valid:
                warnings.append(f"{section}.{field} 类型或取值无效，已丢弃")
                del values[field]
    conditions = out.get("conditions")
    if isinstance(conditions, dict):
        if "injuries" in conditions:
            injuries = conditions["injuries"]
            if not isinstance(injuries, list) or not all(isinstance(i, str) and i.strip() for i in injuries):
                warnings.append("conditions.injuries 必须是伤病描述列表，已丢弃")
                del conditions["injuries"]
        if "health_screen" in conditions:
            screen = conditions["health_screen"]
            if not isinstance(screen, dict):
                warnings.append("conditions.health_screen 必须是对象，已丢弃")
                del conditions["health_screen"]
            else:
                for key in list(screen):
                    if (key not in {"heart", "pregnancy", "medication", "clearance"}
                            or not isinstance(screen[key], (str, bool))
                            or (isinstance(screen[key], str) and not screen[key].strip())):
                        warnings.append(f"health_screen.{key} 类型或取值无效，已丢弃")
                        del screen[key]
    return out, warnings
