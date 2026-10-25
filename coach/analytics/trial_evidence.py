"""M6.5-4：个人训练尝试的基线快照、证据收集与复盘草稿。

复用 PersonalTrial（不建第二套实验对象）：
- 开始尝试时自动固定**基线**（当时的训练事实快照，含观察指标口径）；
- 复盘时收集尝试期间事实 + 执行情况（计划完成率、训练缺口）；
- 草稿严格分节：已观察结果 / 可能解释 / 无法确认的原因——执行缺口
  存在时明确"变化不能完全归因于方案"。
"""
from __future__ import annotations

import json
from datetime import date, datetime

from .fact_service import get_training_facts
from .progress_analysis import analyze_progress


def _compact(facts: dict) -> dict:
    """保留主指标事实及其**完整追溯链**（复查 P1-2：基线/复盘都要能仅凭
    快照确认数值来自哪次训练、哪次修订、当时的数据质量）。"""
    keep = []
    primary = {"best-estimated-1rm", "max-reps", "min-assistance-kg",
               "longest-set", "farthest-distance", "max-added-weight",
               "heaviest-set", "sessions", "plan-completed-days",
               "plan-adherence", "rpe-average"}
    for f in facts.get("facts", []):
        if f.get("metric") in primary and f.get("status") != "insufficient":
            keep.append({k: f[k] for k in ("fact_id", "metric", "value",
                                           "unit", "exercise_id",
                                           "measurement_type", "window",
                                           "source_ids", "calculation",
                                           "data_quality", "status")
                         if k in f})
    return {"window": facts.get("window"), "facts": keep}


def snapshot_baseline(db, user_id: str, observe: str,
                      window_days: int = 30) -> str:
    """尝试开始前的基线（JSON 字符串，随 trial 落库）。"""
    facts = get_training_facts(db, user_id, window_days)
    return json.dumps({
        "kind": "trial_baseline_v1",
        "observe": observe,
        "snapshot_at": datetime.now().isoformat(timespec="seconds"),
        **_compact(facts),
    }, ensure_ascii=False)


def _parse_baseline(trial: dict) -> dict | None:
    raw = trial.get("baseline")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) and data.get("kind") else None
    except (ValueError, TypeError):
        return None


def trial_evidence(db, user_id: str, trial: dict) -> dict:
    """尝试证据：基线 + 尝试期间事实 + 趋势 + 执行情况。"""
    baseline = _parse_baseline(trial)
    start = str(trial.get("created_at") or "")[:10]
    today = date.today().isoformat()
    try:
        during_days = max(1, (date.fromisoformat(today)
                              - date.fromisoformat(start)).days + 1)
    except ValueError:
        during_days = 30
    during_days = min(during_days, 400)
    during = get_training_facts(db, user_id, during_days)
    # 尝试期间每个基线动作的趋势
    trends = []
    if baseline:
        from .fact_service import exercise_progress
        for ex_id in dict.fromkeys(
                f["exercise_id"] for f in baseline.get("facts", [])
                if f.get("exercise_id")):
            prog = exercise_progress(db, user_id, ex_id,
                                     window_days=during_days)
            verdict = analyze_progress(prog.get("series") or [],
                                       prog.get("measurement_type") or
                                       "weight_reps")
            trends.append({"exercise_id": ex_id, **verdict})
    adherence = next((f for f in during["facts"]
                      if f["metric"] == "plan-adherence"), None)
    gaps = max((f.get("data_quality", {}).get("date_gaps_max_days") or 0
                for f in during["facts"] if f.get("exercise_id")), default=0)
    return {
        "trial": {"id": trial.get("id"),
                  "change_desc": trial.get("change_desc"),
                  "reason": trial.get("reason"),
                  "observe": trial.get("observe"),
                  "stop_rule": trial.get("stop_rule"),
                  "status": trial.get("status"),
                  "created_at": trial.get("created_at"),
                  "review_at": trial.get("review_at"),
                  "outcome": trial.get("outcome"),
                  "decision": trial.get("decision")},
        "baseline": baseline,
        "during_window": during.get("window"),
        "during_facts": _compact(during)["facts"],
        "trends": trends,
        "execution": {
            "plan_adherence": (adherence or {}).get("value"),
            "max_gap_days": gaps or None,
            "note": ("尝试期间存在训练缺口或计划完成率低时，"
                     "结果变化不能主要归因于方案本身。"),
        },
    }


def review_draft(db, user_id: str, trial: dict) -> dict:
    """复盘草稿（用户决定 keep/adjust/stop，AI 不代替决定）。"""
    ev = trial_evidence(db, user_id, trial)
    observed, explanations, unconfirmed = [], [], []
    for t in ev["trends"]:
        if t.get("verdict") == "insufficient":
            unconfirmed.append(
                f"{t['exercise_id']}：样本/跨度不足（{t.get('limitations')}）")
        else:
            e = t.get("evidence") or {}
            observed.append(
                f"{t['exercise_id']}：{t['metric']} 前后半窗中位数 "
                f"{e.get('first_half_median')}→{e.get('second_half_median')}"
                f"（判定 {t['verdict']}）")
            explanations.append(
                f"{t['exercise_id']} 的变化可能与「{ev['trial']['change_desc']}」"
                "有关，也可能来自同时期的其他变量（睡眠、饮食、重量选择）")
    ex = ev["execution"]
    if ex["plan_adherence"] is not None and ex["plan_adherence"] < 0.6:
        unconfirmed.append(
            f"尝试期间计划完成率约 {ex['plan_adherence']}，执行不完全——"
            "效果归因不可靠")
    if ex.get("max_gap_days") and ex["max_gap_days"] >= 7:
        unconfirmed.append(f"尝试期间最大训练间隔 {ex['max_gap_days']} 天")
    if not observed:
        observed.append("尝试期间没有形成可比较的指标变化结论")
        unconfirmed.append("尝试期间训练记录样本不足，无法评估该调整的效果")
    unconfirmed.append("单人尝试带混杂因素，结论仅适用于本人，不推广为通用结论")
    return {
        "trial_id": ev["trial"]["id"],
        "change_desc": ev["trial"]["change_desc"],
        "observe": ev["trial"]["observe"],
        "sections": {
            "observed": observed,
            "possible_explanations": explanations,
            "unconfirmed": unconfirmed,
        },
        "evidence": ev,
        "decision_note": ("以上是复盘草稿；保留/调整/放弃由用户决定"
                          "（keep / adjust / stop）"),
    }
