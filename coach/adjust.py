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

from .exercises import library as exercise_lib
from .review import (_same_exercise, _tracked_exercises, adherence, rpe_drift,
                     strength_trend)

# 调整动作空间（LLM 只能从这里选）
ACTIONS = [
    "increase_weight",    # 加重
    "hold_weight",        # 维持重量（磨质量）
    "decrease_weight",    # 减重 10% 重新爬坡
    "add_volume",         # 加容量（+2 组）
    "deload",             # 卸载周
    "reduce_frequency",   # 降低计划频率（匹配真实执行力）
]

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
    if not plan:
        return []
    checkins = db.list_checkins(user_id, limit=200)
    if not checkins:
        return []

    tracked = _tracked_exercises(plan)
    out: list[dict] = []

    # 规则 1：任一主力动作 RPE 漂移上升 → 卸载（整体，只建议一次）
    for ex in tracked:
        if rpe_drift(checkins, ex) == "rising":
            out.append({
                "action": "deload",
                "target": "整体",
                "reason": f"{ex} 同重量 RPE 持续上升，疲劳在累积",
                "evidence": "rpe_drift=rising",
            })
            break

    # 规则 2/3：每个主力动作独立判断停滞（加容量）或进步（加重）
    for ex in tracked:
        trend = strength_trend(checkins, ex)
        if len(trend) >= 3:
            recent = trend[-3:]
            if abs(recent[-1][1] - recent[0][1]) < 0.5:
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

    return out


def apply_adjustment(plan: dict, action: str, target: str, reason: str) -> dict:
    """确定性执行调整，返回新计划（不修改原对象）"""
    if action not in ACTIONS:
        raise ValueError(f"非法调整动作: {action}")

    new = copy.deepcopy(plan)
    new["adjust_reason"] = reason
    new["adjust_action"] = action

    def _find(ex_name: str):
        for day in new["schedule"]:
            for ex in day["exercises"]:
                if _same_exercise(ex_name, ex["name"]):
                    return ex
        return None

    if action in ("increase_weight", "hold_weight", "decrease_weight", "add_volume"):
        ex = _find(target)
        if ex is None:
            raise ValueError(
                f"计划中找不到目标动作「{target}」，未做任何修改。"
                "请用计划里的动作名或其常用叫法。"
            )
        if action == "increase_weight":
            inc = _increment(ex["name"])
            ex["note"] = (ex.get("note") or "") + f"｜下次 +{inc}kg"
        elif action == "hold_weight":
            ex["note"] = (ex.get("note") or "") + "｜重量不变，打磨动作质量"
        elif action == "decrease_weight":
            ex["note"] = (ex.get("note") or "") + "｜减重 10% 重新爬坡"
        elif action == "add_volume":
            ex["sets"] = int(ex["sets"]) + 2

    elif action == "deload":
        new["notes"] = ["⚠️ 本周卸载周：所有动作强度降到 50%，以恢复为目的"] + list(
            new.get("notes", [])
        )
        for day in new["schedule"]:
            day["focus"] += "（卸载）"

    elif action == "reduce_frequency":
        if len(new["schedule"]) > 1:
            dropped = new["schedule"].pop()
            new["notes"] = [
                f"频率调整：砍掉「{dropped['day']}·{dropped['focus']}」，"
                "先把现有天数练满再说"
            ] + list(new.get("notes", []))

    return new
