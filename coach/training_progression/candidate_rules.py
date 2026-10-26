"""P5-C1：分类型、可追溯的确定性进阶候选规则。

候选是"可考虑方向"而不是处方或已完成记录；只有真实计划目标和可验证
器械档位才写入 proposed_targets。复杂组/超组/恢复/限制信息进入限制与
适用条件，不生成虚构数值。
"""
from __future__ import annotations

from ..analytics.activity_class import (
    CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH,
)
from .comparability import strength_completion

REP_TYPES = {"weight_reps", "bodyweight_reps", "assisted_reps"}


def _fact_ids(context: dict, metrics: list[str]) -> list[str]:
    refs = context.get("fact_refs") or []
    out = []
    for metric in metrics:
        hit = next((r["fact_id"] for r in refs if r.get("metric") == metric), None)
        if hit:
            out.append(hit)
    return list(dict.fromkeys(out))


def _source_ids(context: dict) -> list[str]:
    sessions = context.get("comparable_sessions") or []
    return [f"checkin:{s['checkin_id']}:revision:{s.get('revision') or 0}"
            for s in sessions[:6]]


def _scope(context: dict) -> list[str]:
    return ["session", "plan"] if context.get("plan_prescription_applies") else \
        ["session"]


def _targets(context: dict, *, include_weight: bool = True,
             include_assistance: bool = True) -> dict:
    p = context.get("current_prescription") or {}
    out = {}
    sets = p.get("sets")
    if isinstance(sets, int) and 1 <= sets <= 20:
        out["sets"] = sets
    target = p.get("reps_target")
    if target:
        out["reps"] = target.get("raw")
    if include_weight and isinstance(p.get("weight_kg"), (int, float)):
        out["weight_kg"] = float(p["weight_kg"])
    return out


def _option(option_id: str, category: str, title: str, targets: dict,
            context: dict, basis_metrics: list[str], tradeoffs: dict,
            limitations: list[str], data_quality: dict | None = None) -> dict:
    return {
        "option_id": option_id,
        "category": category,
        "title": title,
        "proposed_targets": targets,
        "basis_fact_ids": _fact_ids(context, basis_metrics),
        "source_ids": _source_ids(context),
        "data_quality": {
            "comparable_sessions": len(context.get("comparable_sessions") or []),
            **(data_quality or {}),
        },
        "limitations": limitations,
        "tradeoffs": tradeoffs,
        "action_scope": _scope(context),
        "requires_confirmation": True,
    }


def _base_limitations(context: dict) -> list[str]:
    dq = context.get("data_quality") or {}
    out = []
    if dq.get("temporary_replacement"):
        out.append("当前分析动作是训练中临时替换后的实际动作；"
                   "原计划动作和负重未被永久改写")
    if dq.get("superset"):
        out.append("记录属于超级组；总休息/轮次组织不等同于每个动作的独立组间休息")
    methods = dq.get("methods") or []
    complex_methods = [m for m in methods if m != "straight_set"]
    if complex_methods:
        out.append("含复杂组（" + "、".join(complex_methods) +
                   "）：逻辑组与执行段不同，不能取首段重量套用到所有阶段")
    if dq.get("recovery_missing"):
        out.append("最近没有恢复记录：不能推断恢复良好，只代表该维度未知")
    if dq.get("plan_context_stale"):
        out.append("计划上下文不是当前版本：长期目标不可直接引用，需重新读取计划")
    if dq.get("latest_session_comparable") is False:
        out.append("最近一次实际训练不符合当前可比口径；不据此生成进阶/降量数值")
    if any(str(source).endswith("_inferred")
           for source in (dq.get("classification_sources") or {})):
        out.append("最近记录的活动类别来自旧记录推断（非保存时快照）；"
                   "未静默改写历史，但需结合原始记录确认")
    return out


def _rep_context(context: dict) -> dict:
    target = (context.get("current_prescription") or {}).get("reps_target")
    comparable = context.get("comparable_sessions") or []
    target_sets = (context.get("current_prescription") or {}).get("sets")
    stats = [strength_completion(s, target, target_sets) for s in comparable[:3]]
    return {"target": target, "target_sets": target_sets,
            "stats": stats, "recent": comparable[:3]}


def _maintain(context: dict) -> dict:
    limitations = _base_limitations(context)
    if len(context.get("comparable_sessions") or []) < 2:
        limitations.append("可比记录不足 2 次：当前只能维持并继续观察，"
                           "不能据此判定力量增长")
    return _option(
        "keep-current", "maintain", "维持当前安排并继续观察",
        _targets(context), context,
        ["working-sets", "volume", "sessions"],
        {"benefits": "不引入新变量，便于继续观察真实表现",
         "costs": "短期进阶速度可能较慢",
         "conditions": "动作质量正常、无疼痛加重、当前计划仍与目标一致"},
        limitations)


def _complete_reps(context: dict, rule: dict) -> dict | None:
    target = rule["target"]
    if not target or target.get("kind") != "reps" or not rule["stats"]:
        return None
    latest = rule["stats"][0]
    limitations = _base_limitations(context)
    plan_weight = (context.get("current_prescription") or {}).get("weight_kg")
    actual_weight = latest["loads"][0] if latest.get("uniform_load") \
        and latest.get("loads") else None
    under_plan_weight = bool(
        isinstance(plan_weight, (int, float))
        and isinstance(actual_weight, (int, float))
        and actual_weight < float(plan_weight) - 0.01)
    if latest["all_at_high"] and not under_plan_weight:
        return None
    targets = _targets(context)
    if not targets:
        limitations.append("没有可引用的当前计划次数目标；不虚构次数处方")
        return None
    if latest["rpe_missing"]:
        limitations.append("部分工作组未记录 RPE；完成次数可核实，但主观难度未知")
    if under_plan_weight:
        limitations.append(
            f"最近实际负重 {actual_weight:g}kg 低于当前计划处方 {plan_weight:g}kg；"
            "先把实际完成提升到当前处方，不能把计划重量当作已完成基数")
    return _option(
        "complete-target-reps", "complete-target-reps",
        (f"先按当前处方完成 {plan_weight:g}kg × "
         f"{target['min']}-{target['max']} 次" if under_plan_weight
         else f"先完成既有目标次数（{target['min']}-{target['max']} 次）"),
        targets, context,
        ["working-sets", "volume", "sessions"],
        {"benefits": "在既定动作和负重下积累稳定完成证据",
         "costs": "短期不增加负重刺激",
         "conditions": "动作质量稳定；若出现疼痛或明显不适则停止进阶"},
        limitations,
        {"target_min": target["min"], "target_max": target["max"],
         "latest_all_at_high": latest["all_at_high"],
         "under_plan_weight": under_plan_weight})


def _increase_load(context: dict, rule: dict) -> dict | None:
    context_class = context.get("activity_class")
    measurement = context.get("measurement_type")
    if context_class != CLASS_STRENGTH or measurement not in (
            "weight_reps", "assisted_reps"):
        return None
    stats = rule["stats"]
    if len(rule["recent"]) < 2 or len(stats) < 2:
        return None
    if any(s["has_complex"] or s["rpe_high"] or not s["all_at_high"]
           for s in stats[:2]):
        return None
    target = rule["target"]
    if not target or target.get("kind") != "reps":
        return None
    dq = context.get("data_quality") or {}
    limitations = _base_limitations(context)
    if any(s["rpe_missing"] for s in stats[:2]):
        limitations.append("最近可比训练缺少 RPE：加重候选只在完成目标次数时成立，"
                           "不能确认主观余力")
    if dq.get("superset"):
        limitations.append("加重不改变超级组轮次/休息组织")
    equipment = context.get("equipment_context") or {}
    increment = equipment.get("increment_kg")
    source = equipment.get("increment_source")
    targets = _targets(context, include_weight=False)
    if not targets:
        return None
    if measurement == "weight_reps":
        loads = []
        for session_stat in stats[:2]:
            if not session_stat.get("uniform_load") or not session_stat.get("loads"):
                return None
            loads.append(round(float(session_stat["loads"][0]), 3))
        if len(set(loads)) != 1:
            limitations.append("最近可比训练的负重不一致：不做自动跨档加重")
            return None
        base = loads[0]
        plan_weight = (context.get("current_prescription") or {}).get("weight_kg")
        if isinstance(plan_weight, (int, float)) and abs(base - float(plan_weight)) > 0.01:
            limitations.append("最近实际完成负重低于当前计划处方；"
                               "不能把计划重量当作已完成基数，先完成当前处方")
            return None
        if isinstance(increment, (int, float)) and increment > 0 \
                and not dq.get("superset"):
            targets["weight_kg"] = round(float(base) + increment, 2)
            title = f"在完成目标次数后考虑下一档负重（约 {targets['weight_kg']:g} kg）"
        else:
            title = "在完成目标次数后考虑使用实际可用的下一档负重"
            if dq.get("superset"):
                limitations.append("超级组内只给方向：不改变组织/休息，也不虚构单动作加重值")
            else:
                limitations.append("未知当前器械的实际档位：只给方向，不虚构精确重量")
        metrics = ["best-estimated-1rm", "working-sets", "volume"]
        conditions = ("最近至少两次可比训练均在目标次数上沿完成，且无高 RPE；"
                      "只能从实际可调档位中选择，下一次仍需重新确认动作质量")
    else:
        assists = []
        for session_stat in stats[:2]:
            if not session_stat.get("uniform_assistance") \
                    or not session_stat.get("assistance"):
                return None
            assists.append(round(float(session_stat["assistance"][0]), 3))
        if len(set(assists)) != 1:
            limitations.append("最近可比训练的辅助重量不一致：不做自动跨档调整")
            return None
        base = assists[0]
        if isinstance(increment, (int, float)) and increment > 0 \
                and not dq.get("superset"):
            targets["assistance_kg"] = max(0.0, round(float(base) - increment, 2))
            title = f"在完成目标次数后考虑降低辅助（约 {targets['assistance_kg']:g} kg）"
        else:
            title = "在完成目标次数后考虑使用下一档更低辅助"
            if dq.get("superset"):
                limitations.append("超级组内只给方向：不改变组织/休息，也不虚构辅助档位")
            else:
                limitations.append("未知辅助器械档位：只给方向，不虚构精确数值")
        metrics = ["max-reps", "min-assistance-kg", "working-sets"]
        conditions = "完成次数不下降且动作条件一致时再考虑降低辅助，不能只看辅助重量变小"
    return _option(
        "consider-increase-load", "increase-load", title, targets, context,
        metrics,
        {"benefits": "在完成目标次数的前提下增加渐进刺激",
         "costs": "动作难度和恢复压力上升",
         "conditions": conditions + f"（档位来源：{source}）"},
        limitations,
        {"increment_kg": increment, "increment_source": source})


def _complete_non_rep(context: dict, rule: dict) -> dict | None:
    context_class = context.get("activity_class")
    target = rule.get("target")
    latest = (context.get("last_actual_performance") or {})
    limitations = _base_limitations(context)
    if context_class == CLASS_INTERVAL:
        planned = latest.get("interval_planned_rounds") or 0
        completed = latest.get("interval_completed_rounds") or 0
        skipped = latest.get("interval_skipped_rounds") or 0
        if not planned or (completed >= planned and skipped == 0
                           and not latest.get("interval_ended_early")):
            return None
        limitations.append("计划轮次来自实际记录的编排，不等于已完成轮次；"
                           "不自动缩短休息或增加轮次")
        return _option(
            "complete-interval-plan", "complete-target-reps",
            "先按当前编排完成未完成轮次", {}, context,
            ["interval-work-seconds", "interval-rounds"],
            {"benefits": "先获得完整执行证据，再讨论间歇进阶",
             "costs": "不增加新刺激",
             "conditions": "保持同一工作/休息编排；出现异常不适则停止"},
            limitations,
            {"planned_rounds": planned, "completed_rounds": completed,
             "skipped_rounds": skipped})
    if not target or target.get("kind") != "duration":
        return None
    targets = _targets(context)
    if not targets:
        return None
    if context_class == CLASS_STEADY_CARDIO:
        seconds = latest.get("steady_cardio_seconds") or 0
        if seconds and seconds >= target["seconds"]:
            return None
        limitations.append("有氧完成量按真实时长记录；没有距离时不推导配速或距离目标")
        return _option(
            "complete-cardio-target", "complete-target-reps",
            f"先完成当前持续时间目标（约 {target['seconds']} 秒）",
            targets, context,
            ["steady-cardio-seconds", "steady-cardio-distance"],
            {"benefits": "在不提高强度的前提下完成既定有氧量",
             "costs": "不新增强度刺激",
             "conditions": "器械可用、无异常不适；不同器械/地形不可直接类比"},
            limitations,
            {"latest_steady_cardio_seconds": seconds})
    if context_class == CLASS_STRENGTH and context.get("measurement_type") == "duration":
        durations = [st.get("duration_seconds") for st in latest.get("sets") or []
                     if isinstance(st.get("duration_seconds"), (int, float))]
        if durations and all(d >= target["seconds"] for d in durations):
            return None
        limitations.append("静态/时长动作按实际保持秒数观察；不估算 e1RM 或负重容量")
        return _option(
            "complete-duration-target", "complete-target-reps",
            f"先完成既有保持时长目标（约 {target['seconds']} 秒）",
            targets, context,
            ["longest-set", "working-sets"],
            {"benefits": "在同一动作条件下积累达到目标时长的记录",
             "costs": "不增加负重刺激",
             "conditions": "动作质量稳定，疼痛或动作变形时停止"},
            limitations,
            {"latest_durations_s": durations})
    return None


def _adjust_volume(context: dict, rule: dict) -> dict | None:
    context_class = context.get("activity_class")
    measurement = context.get("measurement_type")
    dq = context.get("data_quality") or {}
    limitations = _base_limitations(context)
    comparable = context.get("comparable_sessions") or []
    if context_class == CLASS_STRENGTH and measurement in REP_TYPES:
        stats = rule["stats"]
        if measurement == "bodyweight_reps" and len(stats) >= 2 \
                and all(s["all_at_high"] and not s["rpe_high"]
                        for s in stats[:2]):
            limitations.append("自重训练不套用外部负重 e1RM；增加额外负重前"
                               "仍需确认动作条件和完成次数")
            return _option(
                "bodyweight-reps-direction", "adjust-volume",
                "完成目标次数后，考虑提高次数或增加额外负重", {}, context,
                ["max-reps", "working-sets"],
                {"benefits": "用次数/额外负重逐步增加自重动作难度",
                 "costs": "更高次数或负重会增加动作与恢复压力",
                 "conditions": "动作质量稳定、左右侧完整；仅给方向，不虚构负重"},
                limitations,
                {"stable_sessions": len(stats[:2])})
        if len(stats) < 3:
            return None
        missing = [s for s in stats if not s["met_min"]]
        if len(missing) < 2 and not any(s["rpe_high"] for s in stats):
            return None
        limitations.append("这是方向而非自动减组：至少需要 3 次可比记录，"
                           "且不能把单次困难当作降量依据")
        return _option(
            "adjust-volume-direction", "adjust-volume",
            "结合连续完成情况，考虑调整组数或次数目标", {}, context,
            ["working-sets", "volume"],
            {"benefits": "减少反复失败带来的挫败与动作变形风险",
             "costs": "训练量可能下降；需要重新积累可比记录",
             "conditions": "仅作为方向；先检查动作、恢复和记录缺口，再与用户确认具体调整"},
            limitations,
            {"sessions_below_target": len(missing),
             "comparable_sessions": len(stats)})
    if context_class == CLASS_STRENGTH and measurement == "duration":
        target = rule.get("target")
        latest_sets = (context.get("last_actual_performance") or {}).get("sets") or []
        durations = [st.get("duration_seconds") for st in latest_sets
                     if isinstance(st.get("duration_seconds"), (int, float))]
        if target and target.get("kind") == "duration" and len(comparable) >= 2 \
                and durations and all(d >= target["seconds"] for d in durations):
            limitations.append("时长动作只按实际保持秒数观察；不估算 e1RM 或负重容量")
            return _option(
                "duration-volume-direction", "adjust-volume",
                "保持动作质量，考虑逐步延长保持时间或增加组数", {}, context,
                ["longest-set", "working-sets"],
                {"benefits": "在无负重条件下渐进延长有效保持时间",
                 "costs": "局部疲劳与动作变形风险增加",
                 "conditions": "动作质量稳定、无疼痛；具体增幅由用户确认"},
                limitations,
                {"latest_durations_s": durations})
    if context_class == CLASS_STEADY_CARDIO:
        if len(comparable) < 3:
            return None
        limitations.append("不同器械、地形和天气的配速/距离不能直接类比；"
                           "单次变快不构成自动加量依据")
        return _option(
            "adjust-cardio-direction", "adjust-volume",
            "在持续记录可比的前提下，考虑调整时长或距离目标", {}, context,
            ["steady-cardio-seconds", "steady-cardio-distance"],
            {"benefits": "以可比较的持续记录逐步调整有氧负荷",
             "costs": "恢复压力与时间成本上升",
             "conditions": "至少 3 次同类型可比记录；无距离不得推断配速"},
            limitations,
            {"steady_cardio_seconds": sum(
                s.get("steady_cardio_seconds") or 0 for s in comparable)})
    if context_class == CLASS_INTERVAL:
        if len(comparable) < 2:
            return None
        full = [s for s in comparable[:3]
                if (s.get("interval_completed_rounds") or 0)
                >= (s.get("interval_planned_rounds") or 0)
                and not (s.get("interval_skipped_rounds") or 0)]
        if len(full) == len(comparable[:3]) and len(comparable[:3]) >= 2:
            limitations.append("只有在同一编排下连续完整完成，才值得再评估增加轮次"
                               "或缩短休息；本轮不自动生成数值")
            return _option(
                "interval-volume-direction", "adjust-volume",
                "保持当前编排，再评估是否调整轮次或休息", {}, context,
                ["interval-work-seconds", "interval-rounds"],
                {"benefits": "先巩固完整完成能力，再增加间歇密度",
                 "costs": "提升节奏可能影响恢复和动作质量",
                 "conditions": "同一 HIIT 编排、连续完整完成且无异常不适"},
                limitations,
                {"stable_full_sessions": len(full)})
        return None
    return None


def _recovery_option(context: dict) -> dict | None:
    recovery = context.get("recovery_context") or {}
    signals = recovery.get("signals") or []
    if not signals:
        return None
    limitations = [
        "恢复信号为用户主观自报；疲劳、睡眠或酸痛与训练表现之间不是确定因果关系",
        "没有恢复记录不代表恢复良好；有记录也不替用户作医疗判断",
    ]
    return {
        "option_id": "observe-recovery", "category": "observe-recovery",
        "title": "结合近期恢复记录，考虑维持或降低当次压力并继续观察",
        "proposed_targets": {},
        "basis_fact_ids": [f["fact_id"] for f in recovery.get("facts") or []],
        "source_ids": recovery.get("source_ids") or [],
        "data_quality": {"recovery_records": recovery.get("records_count", 0),
                         "signals": [s["metric"] for s in signals]},
        "limitations": limitations,
        "tradeoffs": {
            "benefits": "把疲劳/睡眠/酸痛作为观察事实，避免在状态不明时强行加重",
            "costs": "短期训练刺激可能减少",
            "conditions": "仅调整本次训练安排；不据此诊断过度训练或疾病",
        },
        "action_scope": _scope(context),
        "requires_confirmation": True,
    }


def build_candidates(context: dict) -> list[dict]:
    if not (context.get("safety_context") or {}).get("recommendations_allowed"):
        return []
    equipment = context.get("equipment_context") or {}
    if equipment.get("executable") is not True:
        return []
    if context.get("activity_class") == "mixed":
        return []
    dq = context.get("data_quality") or {}
    rule = _rep_context(context) if context.get("activity_class") == CLASS_STRENGTH \
        else {"target": (context.get("current_prescription") or {}).get("reps_target"),
              "target_sets": (context.get("current_prescription") or {}).get("sets"),
              "stats": [], "recent": context.get("comparable_sessions") or []}
    options = [_maintain(context)]
    if dq.get("latest_session_comparable", True):
        complete = _complete_reps(context, rule)
        if complete:
            options.append(complete)
        else:
            complete_nonrep = _complete_non_rep(context, rule)
            if complete_nonrep:
                options.append(complete_nonrep)
        load = _increase_load(context, rule)
        if load:
            options.append(load)
        adjust = _adjust_volume(context, rule)
        if adjust:
            options.append(adjust)
    recovery = _recovery_option(context)
    if recovery:
        options.append(recovery)
    # 固定顺序 + 去重，避免把相关候选当成等价处方
    order = {"maintain": 0, "complete-target-reps": 1, "increase-load": 2,
             "adjust-volume": 3, "observe-recovery": 4}
    seen, out = set(), []
    for option in sorted(options, key=lambda o: order.get(o["category"], 9)):
        if option["option_id"] in seen:
            continue
        seen.add(option["option_id"])
        out.append(option)
    return out
