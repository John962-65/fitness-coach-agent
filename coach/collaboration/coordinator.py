"""P6：主教练协作协调器（coordinator）。

联合分析流程：
共享事实包 → 各专家在自己领域生成观点 → 确定性冲突裁决 → 主教练整合
（保留分歧）→ 只读候选方案与决策要求 → 以 `collaboration-review` 类型
ExpertInsight 持久化（复用任务队列/生命周期/证据校验/options）。

调整计划仍必须走 ChangeProposal 确认协议；本模块绝不直接修改计划。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .conflict_resolver import resolve
from .evidence_bundle import build_evidence_bundle
from .models import COLLAB_RULES_VERSION, collaboration_report
from .specialist_runner import run_opinion

EXPIRE_DAYS = 7


class Scenario:
    def __init__(self, key: str, label: str, question: str, domains: list,
                 participants: list, options_builder):
        self.key = key
        self.label = label
        self.question = question
        self.domains = domains
        self.participants = participants
        self.options_builder = options_builder


# 场景注册表（P6-B 实现三个核心场景的候选方案构造器）
def _options_training_recovery(opinions, resolved, bundle):
    options = [{
        "option_id": "keep-current",
        "title": "保持当前计划，继续观察",
        "detail": "双方共同事实基础上先继续观察；维持现状始终可选。",
        "basis": _fact_ids(opinions),
        "action": "advisory",
    }, {
        "option_id": "adjust-session-pressure",
        "title": "本次训练适当下调压力并记录感受",
        "detail": "把恢复自报作为观察事实；只调整当次安排，不改长期计划。",
        "basis": _fact_ids(opinions),
        "action": "advisory",
    }]
    return options


def _options_training_nutrition(opinions, resolved, bundle):
    options = [{
        "option_id": "keep-current",
        "title": "维持当前训练与饮食安排",
        "detail": "数据不足以支持归因时，维持现状是默认选项。",
        "basis": _fact_ids(opinions),
        "action": "advisory",
    }, {
        "option_id": "improve-records",
        "title": "提高饮食记录完整度后再复盘",
        "detail": "记录完整度不足时先补记录；未记录餐次不代表未摄入。",
        "basis": _fact_ids(opinions),
        "action": "advisory",
    }]
    return options


def _options_movement_rehab(opinions, resolved, bundle):
    options = [{
        "option_id": "observe-only",
        "title": "并列查看技术观察与安全限制，不做归因",
        "detail": "视频异常不推断为伤病原因；限制按 P3 安全门执行。",
        "basis": _fact_ids(opinions),
        "action": "advisory",
    }]
    return options


SCENARIOS: dict[str, Scenario] = {
    "training-recovery": Scenario(
        "training-recovery", "训练 × 恢复联合复盘",
        "近期自报恢复状态与训练表现之间，下一次训练应当如何安排？",
        ["training", "recovery", "rehabilitation"],
        ["training_science", "recovery", "rehabilitation"],
        _options_training_recovery),
    "training-nutrition": Scenario(
        "training-nutrition", "训练 × 营养联合复盘",
        "训练表现变化是否与已记录营养有关？当前数据能否支持进一步分析？",
        ["training", "nutrition", "rehabilitation"],
        ["training_science", "nutrition", "rehabilitation"],
        _options_training_nutrition),
    "movement-rehab": Scenario(
        "movement-rehab", "动作技术 × 康复辅助",
        "动作视频观察与当前身体不适/限制应如何并列理解？",
        ["movement", "rehabilitation"],
        ["movement", "rehabilitation"],
        _options_movement_rehab),
}


def _fact_ids(opinions: list[dict]) -> list[str]:
    out = []
    for o in opinions:
        out.extend(o.get("evidence_refs") or [])
        for d in o.get("directions") or []:
            out.extend(d.get("basis_fact_ids") or [])
    return sorted(set(out))


def analyze_collaboration(db, user_id: str, input_refs: dict) -> dict:
    """ExpertTask 分析器：返回 `collaboration-review` 类型洞察载荷。"""
    scenario_key = str(input_refs.get("scenario") or "")
    scenario = SCENARIOS.get(scenario_key)
    if not scenario:
        raise ValueError(f"未知协作场景 {scenario_key!r}（可选："
                         f"{sorted(SCENARIOS)}）")
    exercise_id = input_refs.get("exercise_id") or None
    window_days = input_refs.get("window_days") or 14

    bundle = build_evidence_bundle(db, user_id, scenario.domains,
                                   window_days=window_days,
                                   exercise_id=exercise_id)
    if exercise_id and "training" in scenario.domains:
        # 趋势判定复用既有 progress_analysis 口径（确定性）
        from ..analytics.exercise_metrics import exercise_sessions
        from ..analytics.progress_analysis import analyze_progress
        sessions = exercise_sessions(db, user_id, exercise_id)
        series = [{"date": s["date"], "best_e1rm": s.get("best_e1rm"),
                   "best_set": s.get("best_set"),
                   "longest_set_s": s.get("longest_set_s"),
                   "farthest_set_m": s.get("farthest_set_m")}
                  for s in reversed(sessions)]
        if series:
            trend = analyze_progress(
                series, measurement_type=sessions[0].get("actual_measurement")
                or "weight_reps",
                activity_class=sessions[0].get("activity_class") or "strength")
            bundle["facts"].append({
                "fact_id": f"exercise-trend-{exercise_id}",
                "domain": "training", "metric": "exercise-trend",
                "value": {"verdict": trend.get("verdict"),
                          "metric": trend.get("metric")},
                "unit": "", "time_window": bundle["window"],
                "source_ids": [f"checkin:{s['checkin_id']}:revision:"
                               f"{s.get('revision') or 0}"
                               for s in sessions[:6]],
                "source_revisions": {},
                "calculation": "progress_analysis 前后半窗中位数（既有口径）",
                "data_quality": {}, "limitations": list(
                    trend.get("limitations") or [])})
    opinions = [run_opinion(s, scenario.question, bundle)
                for s in scenario.participants]
    resolved = resolve(opinions, bundle)
    options = scenario.options_builder(opinions, resolved, bundle)
    if resolved["safety_gates"]:
        for o in options:
            o["limitations"] = list(
                o.get("limitations") or []) + [
                "存在生效训练限制/许可问题：任何执行类决定必须先通过 P3 安全门"]
        options = [o for o in options
                   if o.get("option_id") in ("keep-current", "observe-only")]

    report = collaboration_report(
        scenario=scenario.key, question=scenario.question,
        participants=list(scenario.participants),
        shared_facts=bundle["facts"],
        specialist_opinions=opinions,
        agreements=resolved["agreements"],
        disagreements=resolved["disagreements"],
        unknowns=resolved["unknowns"],
        candidate_options=options,
        decision_requirements=[
            "所有方案均为只读建议；是否采纳由用户决定",
            "调整长期计划必须走 ChangeProposal 确认协议",
            "忽略 / 继续观察 / 仅本次采用 / 申请长期调整均可随时选择",
        ],
        safety_gates=resolved["safety_gates"],
        source_revisions=bundle["source_revisions"])

    findings = []
    for o in opinions:
        text = f"{o['specialist']}：{'；'.join(o['observations']) or '本领域无可报告事实'}"
        findings.append({
            "finding_id": f"op-{o['specialist']}",
            "kind": "specialist-opinion",
            "text": text,
            "fact_ids": o.get("evidence_refs") or [],
            "source_ids": [],
        })
    for dg in resolved["disagreements"]:
        pos = "；".join(
            f"{p['specialist']} 认为 {p['direction']}（{p['note']}）"
            for p in dg["positions"])
        findings.append({
            "finding_id": f"disagree-{dg['kind']}",
            "kind": "disagreement",
            "text": f"专家分歧（{dg['kind']}）：{pos}。"
                    f"缺少信息：{'、'.join(dg['missing_information'])}。"
                    f"{dg['maintain_option']}。",
            "fact_ids": dg["shared_facts"],
            "source_ids": [],
        })
    for u in resolved["unknowns"]:
        findings.append({
            "finding_id": f"unknown-{u['specialist']}",
            "kind": "unknown",
            "text": f"{u['specialist']}：数据不足（{u['note']}）——"
                    "未知不解释为正常值或零值",
            "fact_ids": [],
            "source_ids": [],
        })

    insufficient = len(resolved["unknowns"])
    if resolved["safety_gates"]:
        confidence, basis = "low", "存在安全门：只提供事实与限制说明"
    elif insufficient >= len(opinions) - 1:
        confidence, basis = "low", f"{insufficient} 个领域数据不足"
    elif insufficient == 0 and resolved["disagreements"]:
        confidence, basis = "medium", ("数据完整但专家存在分歧——分歧是结果的一部分，"
                                       "不是低置信度")
    else:
        confidence, basis = "medium", "主要领域均有数据，分歧已并列展示"

    name = exercise_id or scenario.label
    summary = (f"{scenario.label}：{len(opinions)} 位顾问基于共享事实包各自分析，"
               f"共识 {len(resolved['agreements'])} 项、分歧 "
               f"{len(resolved['disagreements'])} 项、数据不足 "
               f"{insufficient} 项"
               + ("；存在生效安全限制" if resolved["safety_gates"] else "")
               + f"。共 {len(options)} 个只读方案，由你决定。")

    return {
        "specialist": "collaboration",
        "insight_type": "collaboration-review",
        "title": f"跨专家协作 · {scenario.label}",
        "summary": summary,
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        # 完整 CollaborationReport 随洞察持久化（工作台直接读取）
        "facts_snapshot": {"facts": bundle["facts"],
                           "caliber": "跨领域事实包（P6 同源口径）",
                           "collaboration": report},
        "knowledge_refs": [],
        "options": options,
        "limitations": [
            f"联合分析规则 {COLLAB_RULES_VERSION}；分歧被保留而非投票合并",
            "本报告是只读结果；修改计划需走确认协议",
        ],
        "confidence": confidence,
        "confidence_basis": basis,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "expires_at": (datetime.now() + timedelta(days=EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": bundle["source_revisions"],
        "input_refs": {"scenario": scenario.key,
                       **({"exercise_id": exercise_id} if exercise_id else {}),
                       "window_days": window_days},
    }
