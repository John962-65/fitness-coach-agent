"""营养目标服务（2.0 §3.4）。

纪律：目标由用户手动设置；系统只提供**有依据的参考估算**（Mifflin-St Jeor
公式 + 活动系数），明确标注适用条件与局限，不替用户决定，不强设统一目标。
"""
from __future__ import annotations

ACTIVITY_FACTORS = {
    "sedentary": ("久坐（几乎不运动）", 1.2),
    "light": ("轻度（每周 1-3 次训练）", 1.375),
    "moderate": ("中度（每周 3-5 次训练）", 1.55),
    "high": ("高度（每周 6-7 次训练）", 1.725),
}


def estimate_reference(profile: dict) -> dict:
    """按档案估算维持能量参考（Mifflin-St Jeor）+ 常用蛋白参考区间。

    缺字段 → 相应建议保持 None（不编造）。返回值仅作参考展示，
    目标落库仍由用户显式保存。
    """
    basic = (profile or {}).get("basic") or {}
    goal = (profile or {}).get("goal") or {}
    age = basic.get("age")
    height = basic.get("height_cm")
    weight = basic.get("weight_kg")
    gender = basic.get("gender")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
               for v in (age, height, weight)) or gender not in ("男", "女"):
        return {"energy_kcal": None,
                "note": "档案缺少年龄/身高/体重/性别，无法给参考估算——可手动设置目标"}
    bmr = (10 * weight + 6.25 * height - 5 * age
           + (5 if gender == "男" else -161))
    factors = {}
    for key, (label, factor) in ACTIVITY_FACTORS.items():
        factors[key] = {"label": label, "tdee": round(bmr * factor)}
    primary = goal.get("primary")
    note = ("Mifflin-St Jeor 公式估算，个体差异可达 ±10% 以上；"
            "减脂/增肌的能量调整建议在 TDEE 基础上小幅偏移并由你观察调整")
    return {"bmr": round(bmr), "activity_factors": factors,
            "protein_reference": {
                "note": "常用参考区间 1.2-2.0 g/kg 体重（因目标与人群而异）",
                "per_kg_range": [1.2, 2.0],
                "at_weight_kg": weight},
            "goal_primary": primary,
            "note": note}
