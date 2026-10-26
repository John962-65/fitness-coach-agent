"""P5-C1：下一次训练确定性候选服务。

只读取事实并返回候选方向；不修改当前会话、不创建计划提案、不写历史。
"""
from __future__ import annotations

from .candidate_rules import build_candidates
from .context_service import build_next_training_context

PROGRESSION_RULES_VERSION = "p5c-progression-rules-v1"


def get_next_training_options(db, user_id: str, exercise_id: str,
                              plan_context: dict | None = None) -> dict:
    context = build_next_training_context(
        db, user_id, exercise_id, plan_context=plan_context)
    context_dict = context.as_dict()
    safety = context_dict.get("safety_context") or {}
    equipment = context_dict.get("equipment_context") or {}
    reasons = []
    allowed = True
    if not safety.get("recommendations_allowed"):
        allowed = False
        reasons.append("当前安全/训练限制不允许为该动作生成可执行进阶方案；"
                       "仍可查看真实记录")
    if equipment.get("executable") is not True:
        allowed = False
        reasons.append("当前地点无法执行该动作或未配置地点/器械；"
                       "不生成假定的可执行目标")
    if context_dict.get("activity_class") == "mixed":
        allowed = False
        reasons.append("最近记录混合了多个活动类别，需先明确本次训练类别")
    if context_dict.get("data_quality", {}).get("plan_context_stale"):
        reasons.append("计划上下文已过期：未使用旧计划目标，需重新读取当前计划")
    options = build_candidates(context_dict) if allowed else []
    return {
        "rules_version": PROGRESSION_RULES_VERSION,
        "context": context_dict,
        "options": options,
        "recommendations_allowed": allowed,
        "blocked_reasons": reasons,
        "caliber": "候选只来自真实记录、当前计划与确定性规则；"
                   "不是处方、不是已完成记录，也不会自动修改计划或训练组",
        "requires_user_confirmation": True,
    }
