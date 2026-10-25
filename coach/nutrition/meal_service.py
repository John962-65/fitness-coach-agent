"""餐次记录服务：保存/修改/复制/趋势/常用食物 + 日状态版本（漂移失效依据）。

口径纪律（2.0 §3.3）：
- 记录不完整的日期只展示「已记录摄入量」，分析同样如此；
- 修改份量后统计按快照重算（快照是食物营养值，份量换算即时进行）；
- day_version 随任何增删改变化——作为 MealRecorded 的幂等锚点和
  洞察 source_revision 的漂移检测依据。
"""
from __future__ import annotations

from . import nutrient_calculator
from .food_catalog import ensure_builtin_foods

MEAL_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐",
               "snack": "加餐"}


def resolve_items(db, user_id: str, raw_items: list) -> list[dict]:
    """[{food_id, amount, unit}] → MealItem（快照在服务端构造，不信任客户端）。"""
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("至少需要一个食物条目")
    if len(raw_items) > 30:
        raise ValueError("单餐最多 30 个条目")
    out = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("条目必须是 {food_id, amount, unit}")
        food_id = str(raw.get("food_id") or "")
        food = db.get_food(user_id, food_id)
        if not food:
            raise ValueError(f"食物 {food_id!r} 不存在（或不是你的自定义食物）")
        amount = raw.get("amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) \
                or not 0 < amount <= 10000:
            raise ValueError(f"「{food['name']}」的 amount 必须是 0-10000 的数值")
        unit = str(raw.get("unit") or "克")
        out.append(nutrient_calculator.build_item(food, float(amount), unit))
    return out


def record_meal(db, user_id: str, local_date: str, meal_type: str,
                raw_items: list, notes: str = "", trigger_event: bool = True) -> dict:
    """保存餐次并触发 MealRecorded（专家失败不影响保存）。"""
    items = resolve_items(db, user_id, raw_items)
    meal_id = db.save_meal(user_id, local_date, meal_type, items, notes)
    if trigger_event:
        _fire_meal_recorded(db, user_id, local_date)
    return {"meal_id": meal_id, "summary": nutrient_calculator.summarize(items)}


def update_meal(db, user_id: str, meal_id: int, raw_items: list,
                notes: str | None, meal_type: str | None = None) -> dict:
    meal = db.get_meal(user_id, meal_id)
    if not meal:
        raise ValueError("餐次不存在")
    items = resolve_items(db, user_id, raw_items)
    if not db.update_meal(user_id, meal_id, items, notes, meal_type):
        raise ValueError("餐次不存在")
    _fire_meal_recorded(db, user_id, meal["local_date"])
    return {"meal_id": meal_id, "summary": nutrient_calculator.summarize(items)}


def delete_meal(db, user_id: str, meal_id: int) -> None:
    meal = db.get_meal(user_id, meal_id)
    if not meal:
        raise ValueError("餐次不存在")
    db.delete_meal(user_id, meal_id)
    _fire_meal_recorded(db, user_id, meal["local_date"])


def _fire_meal_recorded(db, user_id: str, local_date: str) -> None:
    """MealRecorded → 营养顾问日分析。

    幂等锚 = 日期 + 当日记录版本 + 目标版本——任何影响分析结论的状态
    变化（加餐/改份量/完整标记/目标更新）都会触发新一轮而非被去重掉。
    """
    from ..experts import task_dispatcher
    try:
        refs = {"local_date": local_date,
                "day_version": day_version(db, user_id, local_date)}
        targets = db.get_nutrition_targets(user_id)
        if targets.get("updated_at"):
            refs["targets_version"] = targets["updated_at"]
        task_dispatcher.on_event(db, user_id, "MealRecorded", refs)
    except Exception:  # noqa: BLE001 记录主流程已成功，专家链路只留任务日志
        pass


def day_summary(db, user_id: str, local_date: str) -> dict:
    meals = db.meals_on(user_id, local_date)
    result = nutrient_calculator.summarize_day(meals)
    result.update({
        "user_id": user_id, "local_date": local_date,
        "meal_types_recorded": sorted({m["meal_type"] for m in meals}),
        "complete_mark": db.day_complete(user_id, local_date),
        "meals": [{"id": m["id"], "meal_type": m["meal_type"],
                   "notes": m.get("notes") or "",
                   "items": m["items"],
                   **nutrient_calculator.summarize(m["items"])}
                  for m in meals],
        "note": "以下为已记录摄入量；未记录的餐次不代表摄入为 0",
    })
    return result


def day_version(db, user_id: str, local_date: str) -> str:
    """日状态版本：条目数 + 最后更新时间 + 完整标记。

    任何增删改、以及"当天记录是否完整"的标记变化都会改变版本——
    它同时是 MealRecorded 的幂等锚点与洞察漂移检测依据。
    """
    row = db.conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(MAX(updated_at),'') AS last"
        " FROM meal_entries WHERE user_id=? AND local_date=?",
        (user_id, local_date)).fetchone()
    complete = 1 if db.day_complete(user_id, local_date) else 0
    return f"{row['n']}:{row['last']}:{complete}"


def trends(db, user_id: str, days: int = 7) -> dict:
    """近 N 天每日已记录合计（只含当天实际条目，无记录的天不造 0 行——
    但趋势展示需要连续轴时由前端自行留空）。"""
    days = max(1, min(days, 90))
    meals = db.meal_history(user_id, days)
    complete = db.complete_days(user_id, days)
    by_date: dict[str, dict] = {}
    for meal in meals:
        d = by_date.setdefault(meal["local_date"], {"by_meal": {}, "items": []})
        d["by_meal"][meal["meal_type"]] = nutrient_calculator.summarize(meal["items"])
        d["items"].extend(meal["items"])
    out = []
    for date, d in sorted(by_date.items()):
        day = nutrient_calculator.summarize(d["items"])
        out.append({"local_date": date,
                    "complete_mark": date in complete,
                    "meal_types": sorted(d["by_meal"].keys()),
                    "totals": day["totals"],
                    "data_quality": day["data_quality"]})
    return {"days_window": days, "days": out,
            "note": "均为已记录摄入量；未记录日期不表示摄入为 0"}


def frequent_foods(db, user_id: str, limit: int = 12) -> list[dict]:
    """常用食物（按最近 90 天出现次数）。"""
    meals = db.meal_history(user_id, 90)
    counts: dict[str, dict] = {}
    for meal in meals:
        for item in meal["items"]:
            slot = counts.setdefault(item["food_id"], {
                "food_id": item["food_id"], "food_name": item["food_name"],
                "count": 0, "last_unit": item.get("unit"),
                "last_amount": item.get("amount")})
            slot["count"] += 1
    ranked = sorted(counts.values(), key=lambda x: -x["count"])[:limit]
    for slot in ranked:
        food = db.get_food(user_id, slot["food_id"])
        if food:
            slot["serving_units"] = food["serving_units"]
    return ranked


def init_nutrition(db) -> None:
    """启动装载内置食物目录（幂等）。"""
    ensure_builtin_foods(db)
