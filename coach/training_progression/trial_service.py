"""P5-C3：进阶候选 → 个人尝试（PersonalTrial）闭环。

复用既有 PersonalTrial（C4/M6.5-4），不建第二套实验系统：
- 从一个具体的确定性进阶候选创建尝试（服务端重新计算候选，构造关联：
  origin / exercise / plan 版本 / chosen_target / 观察指标与窗口 / 基线快照）；
- 观察期用真实训练记录评估（目标达成分类，与 P5-C 同口径）；
- 复盘草稿严格区分：已观察结果 / 可能解释 / 无法确认的原因——
  不把 AI 预测当结果，不因成绩变化宣称因果；
- 用户决策：保留 / 调整 / 结束 / 暂不判断继续观察；任何决策都不
  自动修改长期计划（需要写回计划时走 ChangeProposal 确认协议）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .comparability import parse_target, target_attainment
from .progression_service import PROGRESSION_RULES_VERSION, get_next_training_options
from ..analytics.activity_class import (
    CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH,
)
from ..analytics.exercise_metrics import exercise_sessions

TRIAL_ORIGIN_KIND = "next_training_candidate"

_DECISION_LABELS = {
    "keep": "保留当前安排",
    "adjust": "调整尝试方式",
    "stop": "结束尝试",
    "observe": "暂不判断，继续观察",
}


def _observation_spec(context: dict) -> tuple[str, str]:
    """观察指标（确定性映射）与观察说明。"""
    cls = context.get("activity_class")
    mtype = context.get("measurement_type")
    if cls == CLASS_STRENGTH and mtype == "duration":
        return "duration-attainment", "各组保持秒数是否达到目标时长"
    if cls == CLASS_STRENGTH:
        return "target-completion", "每次训练相对目标次数的达成分类（与进阶引擎同口径）"
    if cls == CLASS_STEADY_CARDIO:
        return "steady-cardio-seconds", "持续有氧时长是否达到目标"
    if cls == CLASS_INTERVAL:
        return "interval-completion", "HIIT 轮次是否完整完成（不把计划轮次当完成）"
    return "records", "训练记录是否稳定"


def _trial_target(context: dict, chosen: dict) -> dict | None:
    raw = chosen.get("reps")
    target = parse_target(raw) if raw is not None else None
    if target is None and context.get("activity_class") == CLASS_STEADY_CARDIO:
        # 有氧候选目标是时长（秒）口径时由 current_prescription 提供
        presc = context.get("current_prescription") or {}
        target = presc.get("reps_target")
    return target if target and target.get("kind") in ("reps", "duration") \
        else None


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    text = str(value)
    return int(text) if text.isdigit() else None


def _target_text(chosen: dict) -> str:
    parts = []
    if chosen.get("sets") is not None:
        parts.append(f"{chosen['sets']} 组")
    if chosen.get("reps") is not None:
        parts.append(f"{chosen['reps']} 次")
    if chosen.get("weight_kg") is not None:
        parts.append(f"{chosen['weight_kg']:g} kg")
    if chosen.get("assistance_kg") is not None:
        parts.append(f"辅助 {chosen['assistance_kg']:g} kg")
    return " · ".join(parts) or "维持当前安排"


def start_trial_from_candidate(db, user_id: str, exercise_id: str,
                               option_id: str, plan_context: dict | None = None,
                               window_days: int = 14,
                               min_sessions: int = 3) -> dict:
    """从一个确定性候选创建个人尝试（服务端重新计算，不信任前端数值）。"""
    if not isinstance(window_days, int) or isinstance(window_days, bool) \
            or not 1 <= window_days <= 180:
        raise ValueError("window_days 必须是 1-180 的整数")
    if not isinstance(min_sessions, int) or isinstance(min_sessions, bool) \
            or not 1 <= min_sessions <= 30:
        raise ValueError("min_sessions 必须是 1-30 的整数")
    result = get_next_training_options(db, user_id, exercise_id, plan_context)
    if not result.get("recommendations_allowed"):
        raise ValueError("当前安全/器械/口径条件不允许从候选创建尝试")
    option = next((o for o in result.get("options") or []
                   if o.get("option_id") == option_id), None)
    if not option:
        raise ValueError(f"候选 {option_id!r} 不存在或已过期，请重新获取建议")
    chosen = option.get("proposed_targets") or {}
    if not chosen:
        raise ValueError("该候选没有可观察的目标字段，不构成个人尝试对象")
    context = result["context"]
    metric, observe_text = _observation_spec(context)
    name = (context.get("planned_exercise") or {}).get("name") or exercise_id
    change_desc = f"{name}：{option['title']}"
    reason = (f"来自下一次训练建议（候选 {option_id}，"
              f"规则 {result['rules_version']}）")
    stop_rule = (f"观察 {window_days} 天或 {min_sessions} 次该动作训练后复盘"
                 "（以先到者为准）")
    latest_attainment = {}
    comparability = context.get("comparability") or {}
    if comparability.get("target_attainment"):
        first = next(iter(comparability["target_attainment"].values()))
        latest_attainment = {k: first.get(k)
                             for k in ("level", "label", "note") if first.get(k)}
    baseline = {
        "kind": "p5c_trial_baseline_v1",
        "exercise_id": exercise_id,
        "snapshot_at": datetime.now().isoformat(timespec="seconds"),
        "chosen_target": chosen,
        "rules_version": result["rules_version"],
        "last_actual_performance": context.get("last_actual_performance"),
        "comparable_session_count": (context.get("data_quality") or {})
        .get("comparable_session_count", 0),
        "latest_target_attainment": latest_attainment,
    }
    revisions = context.get("source_revisions") or {}
    baseline_revisions = {
        "checkins": revisions.get("checkins") or {},
        "plan": revisions.get("plan"),
        "restrictions_version": revisions.get("restrictions_version"),
        "equipment": revisions.get("equipment"),
        "rules_version": result["rules_version"],
    }
    insight_ref = result.get("insight") or {}
    origin = {
        "kind": TRIAL_ORIGIN_KIND,
        "origin_insight_id": insight_ref.get("id"),
        "origin_option_id": option_id,
        "rules_version": result["rules_version"],
    }
    trial_id = db.start_personal_trial(
        user_id, change_desc, reason, observe_text, stop_rule,
        review_days=window_days, baseline=json.dumps(baseline, ensure_ascii=False),
        origin=json.dumps(origin, ensure_ascii=False),
        exercise_id=exercise_id,
        plan_id=context.get("plan_id"), plan_version=context.get("plan_version"),
        chosen_target=json.dumps(chosen, ensure_ascii=False),
        observation_metric=metric,
        observation_window_days=window_days, min_sessions=min_sessions,
        baseline_source_revisions=json.dumps(baseline_revisions,
                                             ensure_ascii=False))
    trial = db.get_personal_trial(user_id, trial_id)
    return {"trial": public_trial(trial),
            "observation": trial_observation(db, user_id, trial),
            "note": "尝试已开始；观察期内照常训练并记录，复盘由真实记录生成"}


def public_trial(trial: dict) -> dict:
    out = dict(trial)
    for key in ("origin", "chosen_target", "baseline_source_revisions",
                "baseline"):
        raw = out.get(key)
        if raw:
            try:
                out[key] = json.loads(raw)
            except (ValueError, TypeError):
                out[key] = None
    for key in ("plan_id", "plan_version", "observation_window_days",
                "min_sessions"):
        if out.get(key) is not None and str(out[key]).isdigit():
            out[key] = int(out[key])
    return out


def _parse_target_from_trial(trial: dict):
    chosen = trial.get("chosen_target")
    if isinstance(chosen, str):
        try:
            chosen = json.loads(chosen)
        except (ValueError, TypeError):
            chosen = None
    if not isinstance(chosen, dict):
        return None
    raw = chosen.get("reps")
    return parse_target(raw) if raw is not None else None


def _session_meets(session: dict, metric: str, target, chosen: dict) -> bool | None:
    """单次训练是否达成观察指标（None=无法判定）。"""
    if metric == "target-completion":
        att = target_attainment(session, target)
        return att.get("level") in ("at_top",)
    if metric == "duration-attainment":
        att = target_attainment(session, target)
        return att.get("level") in ("at_top",)
    if metric == "steady-cardio-seconds":
        seconds = target["seconds"] if target and target.get("kind") == "duration" \
            else None
        value = session.get("steady_cardio_seconds")
        return bool(seconds and value and value >= seconds)
    if metric == "interval-completion":
        planned = session.get("interval_planned_rounds") or 0
        completed = session.get("interval_completed_rounds") or 0
        skipped = session.get("interval_skipped_rounds") or 0
        return bool(planned) and completed >= planned and skipped == 0 \
            and not session.get("interval_ended_early")
    del chosen
    return None


def trial_observation(db, user_id: str, trial: dict) -> dict:
    """观察期进展：真实训练记录 × 观察指标（确定性）。"""
    exercise_id = trial.get("exercise_id")
    start = str(trial.get("created_at") or "")[:10]
    metric = trial.get("observation_metric") or "records"
    target = _parse_target_from_trial(trial)
    chosen = trial.get("chosen_target")
    if isinstance(chosen, str):
        try:
            chosen = json.loads(chosen)
        except (ValueError, TypeError):
            chosen = {}
    chosen = chosen or {}
    sessions = [s for s in (exercise_sessions(db, user_id, exercise_id)
                            if exercise_id else [])
                if s["date"] >= start]
    results = []
    for s in sessions[:8]:
        meets = _session_meets(s, metric, target, chosen)
        results.append({
            "checkin_id": s["checkin_id"], "date": s["date"],
            "revision": s.get("revision") or 0,
            "meets": meets,
            **({"attainment": target_attainment(s, target)}
               if metric in ("target-completion", "duration-attainment") else {}),
        })
    now = datetime.now().isoformat(timespec="seconds")
    review_at = trial.get("review_at")
    window_elapsed = bool(review_at and review_at <= now)
    min_sessions = _int_or_none(trial.get("min_sessions"))
    sessions_due = (min_sessions is not None and len(results) >= min_sessions)
    plan_record = db.get_active_plan_record(user_id)
    trial_plan_version = _int_or_none(trial.get("plan_version"))
    plan_changed = bool(
        trial.get("plan_id")
        and plan_record
        and (str(plan_record["id"]), plan_record["version"])
        != (str(trial["plan_id"]),
            trial_plan_version if trial_plan_version is not None else -1))
    return {
        "observation_metric": metric,
        "target": target,
        "sessions_total": len(results),
        "sessions_met": sum(1 for r in results if r["meets"] is True),
        "sessions_unmet": sum(1 for r in results if r["meets"] is False),
        "sessions": results,
        "window_elapsed": window_elapsed,
        "review_at": review_at,
        "min_sessions": min_sessions,
        "sessions_due": sessions_due,
        "due_for_review": bool(window_elapsed or sessions_due),
        "plan_changed_since_start": plan_changed,
    }


def trial_review(db, user_id: str, trial: dict) -> dict:
    """复盘草稿：比较真实记录；区分已观察 / 可能解释 / 无法确认。"""
    observation = trial_observation(db, user_id, trial)
    baseline = trial.get("baseline")
    if isinstance(baseline, str):
        try:
            baseline = json.loads(baseline)
        except (ValueError, TypeError):
            baseline = None
    baseline = baseline or {}
    chosen = trial.get("chosen_target")
    if isinstance(chosen, str):
        try:
            chosen = json.loads(chosen)
        except (ValueError, TypeError):
            chosen = {}
    chosen = chosen or {}
    observed: list[str] = []
    unconfirmed: list[str] = []
    before = baseline.get("last_actual_performance") or {}
    if before:
        observed.append(
            "尝试前："
            + (f"{before.get('date')} 完成 {before.get('working_sets', 0)} 组"
               + (f"，次数 {before.get('rep_values')}" if before.get("rep_values")
                  else ""))
            + f"（基线快照 {baseline.get('snapshot_at', '')[:10]}）")
    if observation["sessions_total"] == 0:
        unconfirmed.append("尝试开始后还没有该动作的训练记录，无法评估")
    else:
        observed.append(
            f"尝试期间：{observation['sessions_total']} 次训练，"
            f"达成观察指标 {observation['sessions_met']} 次"
            + (f"，未达成 {observation['sessions_unmet']} 次"
               if observation["sessions_unmet"] else ""))
        for r in observation["sessions"][:3]:
            att = r.get("attainment") or {}
            if att.get("label"):
                observed.append(f"{r['date']}：{att['label']}"
                                + (f"（{att['note']}）" if att.get("note") else ""))
    if observation["sessions_total"] < 3:
        unconfirmed.append(
            f"达成判定基于 {observation['sessions_total']} 次训练，样本偏少；"
            "继续记录可以让复盘更可靠")
    if observation.get("plan_changed_since_start"):
        unconfirmed.append(
            "尝试期间训练计划版本已变化——同期发生了其他变化，"
            "结果不能完全归因于本尝试")
    explanations = []
    if observation["sessions_met"] > 0:
        explanations.append(
            f"达成情况可能与「{trial.get('change_desc')}」有关，"
            "也可能来自恢复、饮食或同时期的其他变化")
    unconfirmed.append("单人尝试带混杂因素，结论仅适用于本人，不推广为通用结论")
    unconfirmed.append("本复盘由确定性规则生成，不构成因果证明或处方")
    decision_options = [
        {"decision": key, "label": label,
         "note": _decision_note(key)}
        for key, label in _DECISION_LABELS.items()]
    return {
        "trial_id": trial["id"],
        "change_desc": trial.get("change_desc"),
        "observe": trial.get("observe"),
        "stop_rule": trial.get("stop_rule"),
        "chosen_target": chosen,
        "sections": {
            "observed": observed,
            "possible_explanations": explanations,
            "unconfirmed": unconfirmed,
        },
        "baseline_summary": {
            "snapshot_at": baseline.get("snapshot_at"),
            "comparable_session_count":
                baseline.get("comparable_session_count"),
            "latest_target_attainment":
                baseline.get("latest_target_attainment"),
        },
        "observation": observation,
        "decision_options": decision_options,
        "decision_note": ("以上是复盘草稿；保留/调整/结束/继续观察由你决定，"
                          "系统不会替你提交长期计划修改"),
    }


def _decision_note(decision: str) -> str:
    if decision == "keep":
        return ("保留当前安排；若当前计划处方与尝试目标还不一致，"
                "需要通过修改提案确认流程另行写入，不会自动修改计划")
    if decision == "adjust":
        return "结束本尝试；下次可以用新的候选再开一个尝试"
    if decision == "stop":
        return "结束尝试，回到之前的安排；不会自动改回计划"
    return "保持尝试进行中，延长观察窗口，稍后复盘"


def decide_trial(db, user_id: str, trial_id: int, decision: str,
                 note: str = "") -> dict:
    """用户决策。任何分支都不自动修改长期计划。"""
    trial = db.get_personal_trial(user_id, trial_id)
    if not trial:
        raise ValueError("尝试不存在")
    if trial["status"] != "active":
        raise ValueError(f"尝试状态为 {trial['status']}，不能再决策")
    if decision not in _DECISION_LABELS:
        raise ValueError("decision 必须是 keep/adjust/stop/observe 之一")
    if decision == "observe":
        days = trial.get("observation_window_days")
        days = int(days) if str(days or "").isdigit() else 7
        db.extend_personal_trial(user_id, trial_id, days)
        fresh = db.get_personal_trial(user_id, trial_id)
        return {"trial": public_trial(fresh), "status": "active",
                "note": "已延长观察窗口；暂不判断，继续观察"}
    review = trial_review(db, user_id, trial)
    outcome = note.strip() or "；".join(
        review["sections"]["observed"][:3]
        + review["sections"]["unconfirmed"][:2])
    if not db.end_personal_trial(user_id, trial_id, outcome, decision):
        raise ValueError("尝试已结束或不存在")
    fresh = db.get_personal_trial(user_id, trial_id)
    hint = ""
    if decision == "keep":
        hint = ("如需把该安排写入长期计划，请使用训练建议中的"
                "「申请修改长期计划」走确认流程；本决策不自动修改计划")
    return {"trial": public_trial(fresh), "status": "ended",
            "decision": decision, "review": review, "note": hint}
