"""确定性营养计算（2.0 §3.3）：
- 全部由代码完成，LLM 不参与；
- item = 食物营养值 ×（克数 / reference_amount），按参考数量换算，
  「每 100 克」与「每份」不混用；
- 未知营养素保持 None；汇总时分别统计「已统计项数/未知项数」，
  绝不用 0 冒充；
- 餐次条目保存营养快照——之后食物库更新不影响历史记录。
"""
from __future__ import annotations

NUTRIENTS = ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g",
             "fiber_g", "sodium_mg")


def unit_to_grams(food: dict, amount: float, unit: str) -> float:
    """份量换算：单位 → 克。找不到单位报错（不静默按克算）。"""
    for u in food.get("serving_units") or []:
        if u.get("unit") == unit:
            return float(amount) * float(u["grams"])
    units = "、".join(u["unit"] for u in food.get("serving_units") or [])
    raise ValueError(f"食物「{food['name']}」不支持单位「{unit}」（可用：{units}）")


def scale(food: dict, grams: float) -> dict:
    """食物营养值 → 指定克数的摄入量（未知保持 None）。"""
    ref = float(food.get("reference_amount") or 100)
    factor = grams / ref
    out: dict = {}
    for key in NUTRIENTS:
        v = food.get(key)
        out[key] = None if v is None else round(float(v) * factor, 2)
    return out


def build_item(food: dict, amount: float, unit: str) -> dict:
    """构造 MealItem：记录时营养快照 + 换算后的本次摄入量。"""
    grams = unit_to_grams(food, amount, unit)
    return {
        "food_id": food["id"],
        "food_name": food["name"],
        "amount": float(amount),
        "unit": unit,
        "grams": round(grams, 1),
        "nutrition_snapshot": {key: food.get(key) for key in NUTRIENTS},
        "snapshot_meta": {
            "reference_amount": food.get("reference_amount"),
            "reference_unit": food.get("reference_unit"),
            "source_name": food.get("source_name"),
            "verified_status": food.get("verified_status"),
        },
        "intake": scale(food, grams),
    }


def summarize(items: list[dict]) -> dict:
    """一组 MealItem → 营养合计（区分未知项；不完整记录仍给出已记录量）。"""
    totals = {key: 0.0 for key in NUTRIENTS}
    unknown = {key: 0 for key in NUTRIENTS}
    known = {key: 0 for key in NUTRIENTS}
    for item in items:
        intake = item.get("intake") or {}
        snap = item.get("nutrition_snapshot") or {}
        for key in NUTRIENTS:
            v = intake.get(key)
            if v is None:
                # 摄入量未知：要么快照本身缺，要么换算缺失
                unknown[key] += 1
            else:
                totals[key] += float(v)
                known[key] += 1
    out = {"totals": {k: round(v, 1) for k, v in totals.items()},
           "items_count": len(items),
           "data_quality": {}}
    for key in NUTRIENTS:
        if unknown[key]:
            out["data_quality"][key] = {
                "known": known[key], "unknown": unknown[key]}
    return out


def summarize_day(meals: list[dict]) -> dict:
    """一天的餐次 → 分餐合计 + 全天已记录合计。"""
    by_type: dict[str, dict] = {}
    all_items: list[dict] = []
    for meal in meals:
        items = meal.get("items") or []
        all_items.extend(items)
        by_type[meal["meal_type"]] = summarize(items)
        by_type[meal["meal_type"]]["meal_id"] = meal["id"]
        by_type[meal["meal_type"]]["notes"] = meal.get("notes") or ""
    day = summarize(all_items)
    return {"by_meal": by_type, "day": day}
