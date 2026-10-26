"""P6：专家意见生成（SpecialistOpinion）。

每位专业顾问只读取事实包中自己领域的条目，在其领域内生成观点——
观察 / 解释 / 建议 / 依据 / 局限，全部由既有确定性口径派生，不引入
新公式、不调 LLM、不因主教练需要统一结论而抹平分歧。
"""
from __future__ import annotations

from ..analytics.activity_class import CLASS_STRENGTH
from .models import specialist_opinion

_HIGH_FATIGUE = 4
_SHORT_SLEEP = 6


def _facts(bundle: dict, domain: str) -> list[dict]:
    return [f for f in bundle.get("facts", []) if f.get("domain") == domain]


def run_training_opinion(question: str, bundle: dict) -> dict:
    facts = _facts(bundle, "training")
    observations, evidence, limitations = [], [], []
    interpretations: list[str] = []
    directions: list[dict] = []
    sessions = next((f for f in facts if f["metric"] == "sessions"), None)
    if sessions and isinstance(sessions.get("value"), (int, float)) \
            and sessions["value"] > 0:
        observations.append(
            f"窗口内训练 {sessions['value']} 次"
            + (f"（{sessions['unit']}）" if sessions.get("unit") else ""))
        evidence.append(sessions["fact_id"])
    plan_fact = next((f for f in facts if f["metric"] == "plan-version"), None)
    adherence = next((f for f in facts if "adherence" in f["metric"]), None)
    if adherence and sessions and (sessions.get("value") or 0) > 0:
        observations.append(f"计划执行情况：{adherence['value']}")
        evidence.append(adherence["fact_id"])
    e1rm = next((f for f in facts
                 if f["metric"] == "best-estimated-1rm"), None)
    trend = next((f for f in facts if f["metric"] == "exercise-trend"), None)
    if e1rm:
        observations.append(
            f"最佳 e1RM（估算口径）{e1rm['value']}{e1rm.get('unit', '')}")
        evidence.append(e1rm["fact_id"])
        limitations.append("e1RM 为 Epley 公式估算值（1-12 次区间），非实测极限")
    trend_verdict = ((trend or {}).get("value") or {}).get("verdict")
    if trend_verdict == "declining":
        interpretations.append("训练表现指标在窗口内下行（趋势口径），"
                               "但单一下行不能归因于单一原因")
        directions.append({"direction": "investigate_decline",
                           "basis_fact_ids": [trend["fact_id"]],
                           "note": "表现下行需要结合恢复与饮食共同判断"})
    elif e1rm:
        directions.append({"direction": "maintain_or_progress",
                           "basis_fact_ids": [e1rm["fact_id"]],
                           "note": "在完成标准满足时按进阶引擎推进"})
    if not observations:
        limitations.append("窗口内没有训练记录：训练表现维度未知"
                           "（未记录不解释为零表现）")
        directions.append({"direction": "insufficient_data",
                           "basis_fact_ids": [], "note": "训练数据不足"})
    return specialist_opinion(
        specialist="training_science", question=question,
        directions=directions, observations=observations,
        interpretations=interpretations + [
            "进阶判断以 P5-C 确定性候选引擎为准；"
            "本意见只提供训练表现侧的事实与方向"],
        recommendations=["训练侧：按下一次训练建议的确定性候选推进或维持"],
        evidence_refs=evidence, limitations=limitations,
    )


def run_recovery_opinion(question: str, bundle: dict) -> dict:
    facts = _facts(bundle, "recovery")
    observations, evidence, limitations = [], [], []
    directions: list[dict] = []

    def _avg(prefix: str):
        return next((f for f in facts if str(f.get("metric", "")).startswith(prefix)
                     and isinstance(f.get("value"), (int, float))), None)

    fatigue = _avg("fatigue-avg")
    soreness = _avg("muscle_soreness-avg")
    sleep = _avg("sleep-hours-avg")
    high = [f for f in (fatigue, soreness) if f and f["value"] >= _HIGH_FATIGUE]
    for f in high:
        observations.append(f"{f['metric']}={f['value']}（自报偏高）")
        evidence.append(f["fact_id"])
    if sleep:
        observations.append(f"平均睡眠 {sleep['value']}{sleep.get('unit', '')}")
        evidence.append(sleep["fact_id"])
        if sleep["value"] < _SHORT_SLEEP:
            observations.append("睡眠少于 6 小时（仅为事实记录）")
    if not facts:
        limitations.append("窗口内没有恢复记录：恢复状态未知，不代表恢复良好")
        directions.append({"direction": "insufficient_data",
                           "basis_fact_ids": [], "note": "恢复数据缺失"})
    elif high or (sleep and sleep["value"] < _SHORT_SLEEP):
        directions.append({"direction": "observe_and_reduce_risk",
                           "basis_fact_ids": [f["fact_id"] for f in high]
                           + ([sleep["fact_id"]] if sleep else []),
                           "note": "自报信号偏高：建议观察并控制当次压力，"
                                   "不是过度训练诊断"})
    else:
        directions.append({"direction": "no_signal",
                           "basis_fact_ids": evidence,
                           "note": "自报恢复信号未见持续偏高"})
    return specialist_opinion(
        specialist="recovery", question=question,
        directions=directions, observations=observations,
        interpretations=["自报恢复与训练表现不是确定因果关系"],
        recommendations=["恢复侧：把自报信号作为观察事实，"
                         "由用户决定是否调整当次训练压力"],
        evidence_refs=evidence,
        limitations=["主观自报；无记录不代表恢复良好"],
    )


def run_nutrition_opinion(question: str, bundle: dict) -> dict:
    facts = _facts(bundle, "nutrition")
    observations, limitations, evidence = [], [], []
    directions: list[dict] = []
    summary = next((f for f in facts
                    if f["metric"] == "nutrition-window-summary"), None)
    if not summary:
        limitations.append("营养事实不可用")
        directions.append({"direction": "insufficient_data",
                           "basis_fact_ids": [], "note": "营养数据缺失"})
        return specialist_opinion(
            specialist="nutrition", question=question, directions=directions,
            observations=observations, interpretations=[],
            recommendations=[], evidence_refs=[], limitations=limitations)
    value = summary.get("value") or {}
    dq = summary.get("data_quality") or {}
    days = value.get("days_recorded", 0)
    window_days = summary.get("time_window", {}).get("days", 0)
    observations.append(
        f"窗口 {window_days} 天中记录了 {days} 天饮食"
        f"（完整度 {dq.get('completeness')}），平均 "
        f"{value.get('avg_calories')} kcal / 蛋白质约 "
        f"{value.get('avg_protein_g')} g/天")
    evidence.append(summary["fact_id"])
    targets = next((f for f in facts
                    if f["metric"] == "nutrition-targets"), None)
    if targets:
        tval = targets.get("value") or {}
        if tval.get("protein_g"):
            observations.append(
                f"用户营养目标蛋白质 {tval['protein_g']} g/天；"
                f"已记录均值 {value.get('avg_protein_g')} g/天"
                "（观察对照，未记录餐次使该对照偏保守）")
            evidence.append(targets["fact_id"])
    if days < window_days * 0.6:
        limitations.append(f"记录完整度不足（{days}/{window_days} 天）："
                           "不能把已记录摄入当作真实摄入分析")
        directions.append({"direction": "records_incomplete",
                           "basis_fact_ids": [summary["fact_id"]],
                           "note": "记录不完整，先补记录再谈调整"})
    else:
        directions.append({"direction": "records_observable",
                           "basis_fact_ids": [summary["fact_id"]],
                           "note": "记录相对完整，可支撑观察性分析"})
    return specialist_opinion(
        specialist="nutrition", question=question,
        directions=directions, observations=observations,
        interpretations=["已记录摄入是观察值，未记录餐次不代表未摄入"],
        recommendations=["营养侧：如记录不足，先提高记录完整度；"
                         "目标调整由用户在营养目标中自行确定"],
        evidence_refs=[summary["fact_id"]], limitations=limitations,
    )


def run_rehab_opinion(question: str, bundle: dict) -> dict:
    facts = _facts(bundle, "rehabilitation")
    observations, evidence = [], []
    directions: list[dict] = []
    permission = next((f for f in facts
                       if f["metric"] == "training-permission-status"), None)
    restrictions = [f for f in facts if f["metric"] == "active-restriction"]
    episodes = [f for f in facts if f["metric"] == "symptom-episode"]
    if permission:
        observations.append(f"训练许可状态：{permission['value']}")
        evidence.append(permission["fact_id"])
    for r in restrictions:
        observations.append(f"生效限制：{r['value']}")
        evidence.append(r["fact_id"])
    urgent = []
    for ep in episodes:
        value = ep.get("value") or {}
        action = value.get("triage_action")
        observations.append(
            f"症状事件（{value.get('status')}）：{value.get('description')}"
            f"——分流：{action}")
        evidence.append(ep["fact_id"])
        if action == "urgent_evaluation":
            urgent.append(ep)
    # 许可状态：prohibited/pending/limited/allowed（allowed 为未阻断）
    blocked = bool(restrictions) or (
        permission and permission["value"] in ("prohibited", "pending",
                                               "limited"))
    if urgent:
        directions.append({"direction": "safety_gate",
                           "basis_fact_ids": [f["fact_id"] for f in urgent],
                           "note": "存在需要尽快专业评估的分流结果；"
                                   "该提示优先于任何训练/恢复建议，"
                                   "且不由多数意见覆盖"})
    elif blocked:
        directions.append({"direction": "safety_gate",
                           "basis_fact_ids": evidence,
                           "note": "P3 安全门优先级高于任何训练/恢复建议"})
    else:
        directions.append({"direction": "no_restriction",
                           "basis_fact_ids": evidence or [],
                           "note": "当前无生效限制或未决症状事件"})
    return specialist_opinion(
        specialist="rehabilitation", question=question,
        directions=directions, observations=observations,
        interpretations=["安全限制不由多数意见覆盖"],
        recommendations=["康复侧：存在限制时所有方案必须先通过安全门"],
        evidence_refs=evidence,
        limitations=["本系统不提供医疗诊断或治疗建议"],
    )


def run_movement_opinion(question: str, bundle: dict) -> dict:
    facts = _facts(bundle, "movement")
    observations, evidence, limitations = [], [], []
    profile = next((f for f in facts
                    if f["metric"] == "motion-profile-version"), None)
    analyses = [f for f in facts if f["metric"] == "motion-analysis"]
    if profile:
        observations.append(f"动作视频档案版本：{profile['value']}")
        evidence.append(profile["fact_id"])
    observations.append(f"近期动作技术分析记录 {len(analyses)} 条")
    evidence.extend(f["fact_id"] for f in analyses)
    limitations.append("二维视频分析受视角、光线、遮挡限制；"
                       "不生成统一动作正确性评分")
    return specialist_opinion(
        specialist="movement", question=question,
        directions=[{"direction": "observational_only",
                     "basis_fact_ids": evidence,
                     "note": "动作技术只做保守观察与教学参考"}],
        observations=observations, interpretations=[],
        recommendations=["动作侧：技术观察不与伤病归因混同"],
        evidence_refs=evidence, limitations=limitations,
    )


RUNNERS = {
    "training_science": run_training_opinion,
    "recovery": run_recovery_opinion,
    "nutrition": run_nutrition_opinion,
    "rehabilitation": run_rehab_opinion,
    "movement": run_movement_opinion,
}


def run_opinion(specialist: str, question: str, bundle: dict) -> dict:
    if specialist not in RUNNERS:
        raise ValueError(f"未知专家 {specialist!r}")
    return RUNNERS[specialist](question, bundle)
