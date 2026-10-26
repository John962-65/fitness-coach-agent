"""P5-C：下一次训练确定性候选服务。

只读取事实并返回候选方向；不修改当前会话、不创建计划提案、不写历史。
P5-C2：为可长期采用的候选附上基于差异的 plan_proposal（统一修改协议的
操作输入）；没有实际差异的候选不生成提案操作。
"""
from __future__ import annotations

from .candidate_rules import build_candidates
from .context_service import build_next_training_context

PROGRESSION_RULES_VERSION = "p5c-progression-rules-v1.1"


def _plan_proposal(context: dict, option: dict) -> dict | None:
    """候选 → 长期计划修改操作（仅当与当前处方存在实际差异）。

    返回 None 表示该候选与当前计划一致或不可长期化——只作本次参考。
    提案创建仍走 ChangeProposal 确认协议；确认前服务端会重新校验
    计划版本与安全状态（建议生成时安全不代表确认时安全）。
    """
    if "plan" not in (option.get("action_scope") or []):
        return None
    if not context.get("plan_prescription_applies"):
        return None
    day = context.get("planned_day")
    index = context.get("planned_index")
    if not day or index is None:
        return None
    current = context.get("current_prescription") or {}
    targets = option.get("proposed_targets") or {}
    patch: dict = {}
    if targets.get("sets") is not None and targets["sets"] != current.get("sets"):
        patch["sets"] = targets["sets"]
    if targets.get("reps") is not None \
            and str(targets["reps"]) != str(current.get("reps") or ""):
        patch["reps"] = targets["reps"]
    if targets.get("weight_kg") is not None \
            and abs(float(targets["weight_kg"])
                    - float(current.get("weight_kg") or 0)) > 0.01:
        patch["weight_kg"] = targets["weight_kg"]
    if not patch:
        return None
    return {"day": day, "index": index,
            "operations": [{"op": "edit_set_prescription", "day": day,
                            "index": index, **patch}]}


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
    for option in options:
        option["plan_proposal"] = _plan_proposal(context_dict, option)
    return {
        "rules_version": PROGRESSION_RULES_VERSION,
        "context": context_dict,
        "options": options,
        "recommendations_allowed": allowed,
        "blocked_reasons": reasons,
        # 顶层版本快照（P5-C2）：长期提案 base_version 与洞察失效判断共用
        "source_revisions": context_dict.get("source_revisions") or {},
        "caliber": "候选只来自真实记录、当前计划与确定性规则；"
                   "不是处方、不是已完成记录，也不会自动修改计划或训练组",
        "requires_user_confirmation": True,
    }
