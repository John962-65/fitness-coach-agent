"""落库前数据校验与强转（设计书 17.2 D1/D2：数据契约）

原则：能强转的强转（"84.5kg"→84.5、"5x5"→5），转不了的丢弃并报告，
绝不让坏数据进库后在复盘/定级时炸出来。
"""
from __future__ import annotations

import re


def _to_number(v) -> float | None:
    """数字或含数字的字符串 → float；失败返回 None"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            return float(m.group())
    return None


def _to_reps(v) -> int | None:
    """次数强转：5 → 5；"5" → 5；"5x5"/"5×5" → 5（取末段）；[5,5,5] → 5（取最好）"""
    if isinstance(v, list):
        nums = [_to_number(x) for x in v]
        nums = [n for n in nums if n]
        return int(max(nums)) if nums else None
    if isinstance(v, str) and re.search(r"[x×*]", v):
        parts = re.split(r"[x×*]", v)
        return _to_reps(parts[-1])
    n = _to_number(v)
    return int(n) if n else None


def coerce_checkin(type_: str, data) -> tuple[dict, list[str]]:
    """打卡落库前清洗。返回 (清洗后数据, 警告列表)。坏行剔除并说明。"""
    warnings: list[str] = []
    if not isinstance(data, dict):
        return {"raw": str(data)[:200]}, ["数据不是结构化对象，已按原文保存"]

    out = dict(data)
    if type_ == "training":
        clean_exs = []
        for ex in data.get("exercises") or []:
            if not isinstance(ex, dict) or not ex.get("name"):
                warnings.append("一条动作记录缺少动作名，已跳过")
                continue
            ex = dict(ex)
            for field in ("weight_kg", "rpe"):
                if ex.get(field) is not None:
                    n = _to_number(ex[field])
                    if n is None:
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
            clean_exs.append(ex)
        out["exercises"] = clean_exs
        if not clean_exs and data.get("exercises"):
            warnings.append("所有动作记录都无法识别，已按原文保存 raw")
            out["raw"] = out.get("raw") or str(data)[:200]

    if type_ == "body":
        for field in ("weight_kg", "waist_cm"):
            if data.get(field) is not None:
                n = _to_number(data[field])
                if n is None:
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
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in patch.items()}

    for sec, key in _NUM_PROFILE_FIELDS:
        sec_d = out.get(sec)
        if not isinstance(sec_d, dict) or key not in sec_d:
            continue
        n = _to_number(sec_d[key])
        if n is None:
            warnings.append(f"{sec}.{key}={sec_d[key]!r} 不是数字，已丢弃")
            del sec_d[key]
        else:
            sec_d[key] = int(n) if n == int(n) else n

    big3 = out.get("experience", {}).get("big3")
    if isinstance(big3, dict):
        for lift in list(big3):
            n = _to_number(big3[lift])
            if n is None:
                warnings.append(f"big3.{lift}={big3[lift]!r} 不是数字，已丢弃")
                del big3[lift]
            else:
                big3[lift] = n
    return out, warnings
