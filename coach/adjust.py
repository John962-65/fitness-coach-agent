"""调整引擎：基于打卡数据的计划调整建议与执行

职责划分：
- suggest_adjustments()：确定性规则引擎，输出建议（不调 LLM）
- apply_adjustment()：确定性执行，生成新计划版本（带理由）
- LLM 的角色：把建议翻译成人话、在用户确认后选择执行哪个
  （动作空间被 ACTIONS 约束，LLM 不能自由生成计划）

R2：按动作库 id 匹配目标（根治 17.2 L1 匹配方向问题）；
每个 track_e1rm 主力动作独立评估（17.2 L3）；目标未命中直接报错。
"""
from __future__ import annotations

import copy
from datetime import date, timedelta

from .exercises import library as exercise_lib
from .review import (_same_exercise, _tracked_exercises, adherence, rpe_drift,
                     strength_trend)
from .validate import round_half

# 调整动作空间（LLM 只能从这里选）
ACTIONS = [
    "increase_weight",    # 加重
    "hold_weight",        # 维持重量（磨质量）
    "decrease_weight",    # 减重 10% 重新爬坡
    "add_volume",         # 加容量（+2 组）
    "deload",             # 卸载周
    "reduce_frequency",   # 降低计划频率（匹配真实执行力）
]

DELOAD_DAYS = 7
DELOAD_FACTOR = 0.5


def is_deload_active(plan: dict | None) -> bool:
    """卸载周是否仍在有效期内（A1：deload 是带到期日的状态）"""
    d = (plan or {}).get("deload") or {}
    until = d.get("until", "")
    return bool(until) and until >= date.today().isoformat()


# 动作 → 加重幅度（kg）：按动作模式，下肢大肌群 5，其余 2.5
def _increment(exercise: str) -> float:
    ex_id, _, _ = exercise_lib.normalize(exercise)
    if ex_id:
        pattern = exercise_lib.get(ex_id).get("pattern")
        if pattern in ("squat", "hinge", "lunge"):
            return 5.0
        return 2.5
    lower = ["深蹲", "硬拉", "倒蹬", "腿举"]
    return 5.0 if any(k in exercise for k in lower) else 2.5


def suggest_adjustments(db, user_id: str, plan: dict | None) -> list[dict]:
    """规则引擎：输出调整建议列表（确定性，可测试）"""
    if not plan or plan.get("medical_status", "allowed") != "allowed":
        return []
    checkins = db.list_checkins(user_id, limit=200)
    if not checkins:
        return []

    tracked = _tracked_exercises(plan)
    out: list[dict] = []
    profile = db.get_existing_profile(user_id)
    sleep = (profile.get("nutrition") or {}).get("sleep_hours")
    sleep_low = isinstance(sleep, (int, float)) and not isinstance(sleep, bool) and 0 < sleep < 6
    rising = [ex for ex in tracked if rpe_drift(checkins, ex) == "rising"]
    recovery_limited = bool(rising) or sleep_low or is_deload_active(plan)
    if sleep_low and tracked and not rising and not is_deload_active(plan):
        out.append({"action": "hold_weight", "target": tracked[0],
                    "reason": "已记录的睡眠偏少，先确认近期恢复与记录是否仍准确，暂不增加刺激",
                    "evidence": f"sleep_hours={sleep}"})

    # 规则 1：任一主力动作 RPE 漂移上升 → 卸载（整体，有效期内不重复建议）
    if not is_deload_active(plan):
        for ex in tracked:
            if rpe_drift(checkins, ex) == "rising":
                out.append({
                    "action": "deload",
                    "target": "整体",
                    "reason": f"{ex} 同重量 RPE 持续上升，疲劳在累积",
                    "evidence": "rpe_drift=rising",
                })
                break

    # 恢复受限/卸载中不同时建议增加训练刺激。
    for ex in ([] if recovery_limited else tracked):
        trend = strength_trend(checkins, ex)
        if len(trend) >= 3:
            recent = trend[-3:]
            if max(v for _, v in recent) - min(v for _, v in recent) < 0.5:
                out.append({
                    "action": "add_volume",
                    "target": ex,
                    "reason": f"{ex} 连续 {len(recent)} 次停滞在 "
                              f"{recent[-1][1]}kg，需要新刺激",
                    "evidence": f"e1rm_flat={recent[-1][1]}",
                })
                continue
        if len(trend) >= 2 and trend[-1][1] > trend[-2][1]:
            inc = _increment(ex)
            out.append({
                "action": "increase_weight",
                "target": ex,
                "reason": f"{ex} e1RM 在涨（{trend[-2][1]} → {trend[-1][1]}kg），"
                          f"按计划下次 +{inc}kg",
                "evidence": f"e1rm_up={trend[-1][1]}",
            })

    # 规则 4：执行率 < 50% → 降频率（计划要匹配真实生活）
    planned = len(plan.get("schedule") or []) or plan.get("days_per_week", 3)
    ad = adherence(checkins, planned)
    if ad["planned_days"] and ad["rate"] < 0.5:
        out.append({
            "action": "reduce_frequency",
            "target": "计划频率",
            "reason": f"本周执行率只有 {ad['trained_days']}/{ad['planned_days']}，"
                      "计划应该匹配真实时间，而不是理想时间",
            "evidence": f"adherence={ad['rate']}",
        })

    feasible = []
    for suggestion in out:
        if suggestion["action"] in ("add_volume", "reduce_frequency"):
            try:
                apply_adjustment(plan, suggestion["action"], suggestion["target"], suggestion["reason"])
            except ValueError:
                continue
        feasible.append(suggestion)
    return feasible


def apply_adjustment(plan: dict, action: str, target: str, reason: str,
                     last_weight: float | None = None) -> dict:
    """确定性执行调整，返回新计划（不修改原对象）。

    last_weight：目标动作最近打卡重量（A5 算处方重量用，可空）。
    """
    if action not in ACTIONS:
        raise ValueError(f"非法调整动作: {action}")
    if plan.get("medical_status", "allowed") != "allowed":
        raise ValueError("训练处方已因医疗限制暂停，不能执行训练调整")

    new = copy.deepcopy(plan)
    new["adjust_reason"] = reason
    new["adjust_action"] = action

    def _find_all(ex_name: str) -> list[dict]:
        return [ex for day in new["schedule"] for ex in day["exercises"]
                if _same_exercise(ex_name, ex)]

    if action in ("increase_weight", "hold_weight", "decrease_weight", "add_volume"):
        matches = _find_all(target)
        if not matches:
            raise ValueError(
                f"计划中找不到目标动作「{target}」，未做任何修改。"
                "请用计划里的动作名或其常用叫法。"
            )
        if action == "increase_weight":
            for ex in matches:
                inc = _increment(ex["name"])
                base = ex.get("weight_kg") or last_weight
                if base:
                    ex["weight_kg"] = round_half(base + inc)
                else:
                    ex["note"] = (ex.get("note") or "") + f"｜下次按最近完成重量 +{inc}kg"
        elif action == "hold_weight":
            for ex in matches:
                ex["note"] = (ex.get("note") or "") + "｜重量不变，打磨动作质量"
        elif action == "decrease_weight":
            for ex in matches:
                base = ex.get("weight_kg") or last_weight
                if base:
                    ex["weight_kg"] = round_half(base * 0.9)
                else:
                    ex["note"] = (ex.get("note") or "") + "｜减重 10% 重新爬坡"
        elif action == "add_volume":
            for ex in matches:  # A3：按动作 id 批量修改全部出现
                ex["sets"] = int(ex["sets"]) + 2

    elif action == "deload":
        if is_deload_active(new):
            raise ValueError(
                f"当前已在卸载周（至 {new['deload']['until']}），到期前不能重复卸载"
            )
        until = (date.today() + timedelta(days=DELOAD_DAYS)).isoformat()
        new["deload"] = {"until": until, "factor": DELOAD_FACTOR}
        new["notes"] = [
            f"⚠️ 本周卸载周（至 {until}）：所有动作强度按 "
            f"{int(DELOAD_FACTOR * 100)}%，以恢复为目的"
        ] + list(new.get("notes", []))

    elif action == "reduce_frequency":
        days = new["schedule"]
        if len(days) <= 1:
            raise ValueError("计划只有 1 天，无法再降频")
        # A2：降频 = 主项重组成更少的全身天，不是砍掉最后一天
        pool: list[dict] = []
        for day in days:
            for ex in day["exercises"][:2]:
                if not any(_same_exercise(ex, p) for p in pool):
                    pool.append(copy.deepcopy(ex))
        if not pool:
            raise ValueError("计划里没有可重组的动作")
        n = len(days) - 1
        new_days = [{"day": f"第 {i + 1} 练", "focus": "全身（降频重组）",
                     "exercises": []} for i in range(n)]
        for i, ex in enumerate(pool):
            new_days[i % n]["exercises"].append(ex)
        new["schedule"] = new_days
        new["notes"] = [
            f"频率调整：{len(days)} 天 → {n} 天全身重组，"
            "主项全部保留、辅助动作暂减，先把主项练满"
        ] + list(new.get("notes", []))

    if new.get("time_budget_minutes") is not None:
        from .programming import estimate_minutes
        for day in new["schedule"]:
            duration = estimate_minutes(day["exercises"])
            if duration > new["time_budget_minutes"]:
                raise ValueError("调整将超出已有时间预算，请先确认时间或重排方案")
            day["estimated_minutes"] = duration
    return new
