"""M6.5-0：统一 AI 训练事实服务——结构化数据，不是拼好的大段文本。

设计纪律：
1. **完全复用** `exercise_metrics`（逐组指标）与 `training_calendar.period_summary`
   （周期汇总）——「我的表现」「周期统计」「AI 训练事实」三个接口的数值、
   单位与口径一致由构造保证，绝不另写一套公式。
2. 分型口径不混用：weight_reps / bodyweight_reps / assisted_reps /
   duration / distance_time 各自适用各自指标（e1RM 只属于 1-12 次的
   weight_reps）。
3. 日期 = 会话本地日期（session_meta.local_date，旧记录回退服务器日期），
   支持任意时间窗查询，不依赖"最近 N 条"固定窗口。
4. 排除热身组；读 checkins 当前行（历史纠错后的当前有效版本），
   source_ids 保留 `checkin:{id}:revision:{n}` 追溯链。
5. 缺数据 → status=insufficient + value=None，绝不用 0 冒充。
6. 区分：observed（客观记录/算术汇总）、estimated（模型估算，如 e1RM）、
   insufficient；用户主观自报（RPE）在 calculation 与 data_quality 里明示。

计划完成率规则（M6.5-0）：
- 只有 session_meta.mode=='planned' 且 plan_id==当前生效计划的会话计入
  计划完成；自由训练与模板训练**不**自动算作完成计划训练日；
- 同一计划日标签 + 同一本地日期只计一次（同天多次训练≠多个任务）。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from .exercise_metrics import (entry_set_type, exercise_sessions,
                               session_local_date)
from .training_calendar import period_summary

MAX_WINDOW_DAYS = 400  # 与 training_calendar._MAX_SCAN_DAYS 对齐

# 每种记录类型的“主进步指标”与可选指标（分析/建议层按此选择可比指标）
MEASUREMENT_METRICS: dict[str, dict] = {
    "weight_reps": {
        "primary": "best-estimated-1rm",
        "available": ["heaviest-set", "best-estimated-1rm", "volume",
                      "max-reps-at-weight"],
    },
    "bodyweight_reps": {
        "primary": "max-reps",
        "available": ["max-reps", "max-added-weight", "volume"],
    },
    "assisted_reps": {
        "primary": "max-reps",
        "available": ["max-reps", "min-assistance-kg"],
    },
    "duration": {
        "primary": "longest-set",
        "available": ["longest-set"],
    },
    "distance_time": {
        "primary": "farthest-distance",
        "available": ["farthest-distance"],
    },
}


def _fact(fact_id: str, metric: str, value, unit: str, measurement_type: str,
          window: dict, source_ids: list[str], calculation: str, status: str,
          exercise_id: str | None = None, **quality) -> dict:
    return {
        "fact_id": fact_id,
        "metric": metric,
        **({"exercise_id": exercise_id} if exercise_id else {}),
        "value": value,
        "unit": unit,
        "measurement_type": measurement_type,
        "window": dict(window),
        "source_ids": source_ids,
        "calculation": calculation,
        "data_quality": dict(quality) if quality else {},
        "status": status,
    }


def _iter_training_rows(db, user_id: str):
    """当前有效训练记录（含修订计数，用于追溯与数据质量说明）。"""
    rows = db.conn.execute(
        "SELECT c.id, c.data, c.created_at,"
        " (SELECT COUNT(*) FROM checkin_revisions r WHERE r.checkin_id=c.id)"
        " AS revision"
        " FROM checkins c WHERE c.user_id=? AND c.type='training'"
        " ORDER BY c.created_at DESC, c.id DESC", (user_id,)).fetchall()
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            yield row, data


def _src(checkin_id: int, revision: int) -> str:
    return f"checkin:{checkin_id}:revision:{revision}"


def _max_gap_days(dates: list[str]) -> int | None:
    if len(dates) < 2:
        return None
    ds = sorted(date.fromisoformat(d) for d in dates)
    return max((b - a).days for a, b in zip(ds, ds[1:]))


def _sessions_in_window(db, user_id: str, exercise_id: str,
                        start: str, end: str) -> tuple[list[dict], list[str]]:
    """动作会话按本地日期窗口过滤；返回 (会话, 来源链)。"""
    out, srcs = [], []
    for s in exercise_sessions(db, user_id, exercise_id):
        if not (start <= s["date"] <= end):
            continue
        out.append(s)
        srcs.append(_src(s["checkin_id"], s.get("revision") or 0))
    return out, srcs


def _exercise_facts(db, user_id: str, exercise_id: str, doc: dict,
                    window: dict, start: str, end: str) -> list[dict]:
    sessions, srcs = _sessions_in_window(db, user_id, exercise_id, start, end)
    # 实际记录类型优先（用户按辅助/时长记录时按该口径统计），库声明兜底
    mtype = (entry_set_type(sessions[0]["sets"]) if sessions else None) \
        or doc.get("measurement") or "weight_reps"
    base = f"{exercise_id}-{window['end'].replace('-', '')}"
    dates = [s["date"] for s in sessions]
    gaps = _max_gap_days(dates)
    corrected = sum(1 for s in sessions if (s.get("revision") or 0) > 0)
    quality = {
        "sessions": len(sessions),
        "date_gaps_max_days": gaps,
        "corrected_records": corrected,
    }
    if corrected:
        quality["notes"] = [f"含已纠错记录 {corrected} 条（按当前有效版本统计）"]
    if len(sessions) == 1:
        quality.setdefault("notes", []).append("窗口内仅 1 次训练，趋势不可判")
    if not sessions:
        return [_fact(f"frequency-{base}", "sessions", 0, "次", mtype,
                      window, [], "count_training_sessions_by_local_date",
                      "insufficient", exercise_id=exercise_id, **quality)]

    facts = [
        _fact(f"frequency-{base}", "sessions", len(sessions), "次", mtype,
              window, srcs, "count_training_sessions_by_local_date",
              "observed", exercise_id=exercise_id, **quality),
        _fact(f"frequency-per-week-{base}", "sessions-per-week",
              round(len(sessions) * 7 / window["days"], 1), "次/周", mtype,
              window, srcs, "sessions_x7_over_window_days", "observed",
              exercise_id=exercise_id, **quality),
        _fact(f"working-sets-{base}", "working-sets",
              sum(s["working_sets"] for s in sessions), "组", mtype,
              window, srcs, "sum_working_sets_excluding_warmup", "observed",
              exercise_id=exercise_id, **quality),
    ]

    # ---- 分型主指标（口径与「我的表现」完全一致）----
    if mtype == "weight_reps":
        heavy = max(
            (st for s in sessions for st in s["sets"]
             if st["weight_kg"] is not None),
            key=lambda st: st["weight_kg"], default=None)
        if heavy:
            facts.append(_fact(
                f"heaviest-set-{base}", "heaviest-set", heavy["weight_kg"],
                "kg", mtype, window, srcs,
                "max_working_set_weight_excluding_warmup", "observed",
                exercise_id=exercise_id, reps=heavy["reps"], **quality))
        e1rms = [s["best_e1rm"] for s in sessions if s["best_e1rm"]]
        if e1rms:
            best = max((s for s in sessions if s["best_e1rm"]),
                       key=lambda s: s["best_e1rm"])
            facts.append(_fact(
                f"best-estimated-1rm-{base}", "best-estimated-1rm",
                best["best_e1rm"], "kg", mtype, window, srcs,
                "epley_best_valid_set_reps_1_12", "estimated",
                exercise_id=exercise_id,
                note="Epley 公式估算值，非实测极限", **quality))
        else:
            facts.append(_fact(
                f"best-estimated-1rm-{base}", "best-estimated-1rm", None,
                "kg", mtype, window, srcs,
                "epley_best_valid_set_reps_1_12", "insufficient",
                exercise_id=exercise_id,
                note="窗口内没有 1-12 次区间的有效正式组", **quality))
    elif mtype == "bodyweight_reps":
        best_reps = max(
            (st for s in sessions for st in s["sets"] if st["reps"]),
            key=lambda st: st["reps"], default=None)
        if best_reps:
            facts.append(_fact(
                f"max-reps-{base}", "max-reps", best_reps["reps"], "次",
                mtype, window, srcs, "max_working_set_reps", "observed",
                exercise_id=exercise_id,
                added_weight_kg=best_reps.get("added_weight_kg"), **quality))
        added = [st["added_weight_kg"] for s in sessions for st in s["sets"]
                 if st.get("added_weight_kg")]
        if added:
            facts.append(_fact(
                f"max-added-weight-{base}", "max-added-weight", max(added),
                "kg", mtype, window, srcs, "max_added_weight_working_sets",
                "observed", exercise_id=exercise_id, **quality))
    elif mtype == "assisted_reps":
        best_reps = max(
            (st for s in sessions for st in s["sets"] if st["reps"]),
            key=lambda st: st["reps"], default=None)
        if best_reps:
            facts.append(_fact(
                f"max-reps-{base}", "max-reps", best_reps["reps"], "次",
                mtype, window, srcs, "max_working_set_reps", "observed",
                exercise_id=exercise_id,
                assistance_kg=best_reps.get("assistance_kg"), **quality))
        assist = [st["assistance_kg"] for s in sessions for st in s["sets"]
                  if st.get("assistance_kg") is not None]
        if assist:
            facts.append(_fact(
                f"min-assistance-kg-{base}", "min-assistance-kg",
                min(assist), "kg", mtype, window, srcs,
                "min_assistance_working_sets", "observed",
                exercise_id=exercise_id,
                note="辅助重量越小=自承担越多（方向与负重类相反）", **quality))
    elif mtype == "duration":
        longest = max(
            (st for s in sessions for st in s["sets"]
             if st.get("duration_seconds")),
            key=lambda st: st["duration_seconds"], default=None)
        if longest:
            facts.append(_fact(
                f"longest-set-{base}", "longest-set",
                longest["duration_seconds"], "秒", mtype, window, srcs,
                "max_working_set_duration", "observed",
                exercise_id=exercise_id, **quality))
    elif mtype == "distance_time":
        far = max(
            (st for s in sessions for st in s["sets"] if st.get("distance_m")),
            key=lambda st: st["distance_m"], default=None)
        if far:
            facts.append(_fact(
                f"farthest-distance-{base}", "farthest-distance",
                far["distance_m"], "米", mtype, window, srcs,
                "max_working_set_distance", "observed",
                exercise_id=exercise_id, **quality))

    # 容量（只有负重类产生 kg 容量；口径=set_volume 全站唯一公式）
    if mtype in ("weight_reps", "bodyweight_reps"):
        facts.append(_fact(
            f"volume-{base}", "volume",
            round(sum(s["volume"] for s in sessions)), "kg", mtype,
            window, srcs,
            ("sum_weight_times_reps_working_sets" if mtype == "weight_reps"
             else "sum_added_weight_times_reps_working_sets"),
            "observed", exercise_id=exercise_id, **quality))

    # RPE（用户主观自报，只汇总不推断）
    rpes = [st.get("rpe") for s in sessions for st in s["sets"]
            if isinstance(st.get("rpe"), (int, float))]
    if rpes:
        facts.append(_fact(
            f"rpe-average-{base}", "rpe-average",
            round(sum(rpes) / len(rpes), 1), "RPE", mtype, window, srcs,
            "user_reported_mean_working_sets", "observed",
            exercise_id=exercise_id,
            note="RPE 为用户主观自报，非客观测量", **quality))
    return facts


def _plan_adherence_facts(db, user_id: str, window: dict,
                          start: str, end: str) -> list[dict]:
    """计划完成率（规则见模块 docstring）。"""
    record = db.get_active_plan_record(user_id)
    if not record:
        return []
    plan = record.get("content") if isinstance(record.get("content"), dict) else {}
    day_labels = [d.get("day") for d in (plan.get("schedule") or [])
                  if isinstance(d, dict) and d.get("day")]
    if not day_labels:
        return []
    weeks = max(1.0, window["days"] / 7)
    scheduled = round(len(day_labels) * weeks)
    completed: set[tuple[str, str]] = set()
    srcs: list[str] = []
    free_sessions = 0
    for row, data in _iter_training_rows(db, user_id):
        local = session_local_date(row["created_at"], data)
        if not (start <= local <= end):
            continue
        meta = data.get("session_meta") if isinstance(
            data.get("session_meta"), dict) else {}
        if meta.get("mode") == "planned" and meta.get("plan_id") == record["id"]:
            day = str(meta.get("day") or "")
            if day in day_labels and (day, local) not in completed:
                completed.add((day, local))
                srcs.append(_src(row["id"], row["revision"]))
        elif meta.get("mode") != "planned":
            free_sessions += 1
    base = f"plan{record['id']}-{window['end'].replace('-', '')}"
    # 有计划会话或存在自由训练（观察到了"没按计划练"）→ observed；
    # 窗口内既无计划会话也无自由训练 → 没有可观察对象，insufficient
    status = "observed" if (completed or free_sessions) else "insufficient"
    facts = [
        _fact(f"plan-scheduled-{base}", "plan-scheduled-sessions", scheduled,
              "次", "session", window, [], "plan_days_per_week_x_window_weeks",
              "estimated", note="按计划每周训练日数×窗口周数推算的应练次数"),
        _fact(f"plan-completed-{base}", "plan-completed-days",
              len(completed), "个训练日", "session", window, srcs,
              "distinct_planned_day_local_date_pairs", status,
              note=("自由/模板训练不计入计划完成；同日多次训练同一计划日只计一次"
                    + (f"；窗口内另有自由训练 {free_sessions} 次（不计入）"
                       if free_sessions else ""))),
    ]
    if scheduled > 0:
        facts.append(_fact(
            f"plan-adherence-{base}", "plan-adherence",
            round(len(completed) / scheduled, 2), "比率", "session", window,
            srcs, "plan_completed_over_scheduled", status))
    return facts


def get_training_facts(db, user_id: str, window_days: int = 30,
                       exercise_ids: list[str] | None = None) -> dict:
    """统一训练事实入口（M6.5-0 十项要求见模块 docstring）。"""
    from .. import exercise_service
    days = max(1, min(int(window_days), MAX_WINDOW_DAYS))
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    window = {"start": start, "end": end, "days": days}

    # 动作范围：显式指定 → 逐一校验；未指定 → 覆盖窗口内出现过的动作
    if exercise_ids is not None:
        valid, skipped = [], []
        for ex_id in exercise_ids:
            (valid if exercise_service.get_exercise(db, user_id, ex_id)
             else skipped).append(ex_id)
        notes = ([f"未识别的动作 ID 未统计：{('、'.join(skipped))}"]
                 if skipped else [])
    else:
        seen: list[str] = []
        for row, data in _iter_training_rows(db, user_id):
            if not (start <= session_local_date(row["created_at"], data) <= end):
                continue
            for ex in data.get("exercises") or []:
                if not isinstance(ex, dict):
                    continue
                from .exercise_metrics import entry_identity
                ex_id = entry_identity(db, user_id, ex)
                if ex_id and ex_id not in seen:
                    seen.append(ex_id)
        valid, notes = seen, []

    facts: list[dict] = []
    for ex_id in valid:
        doc = exercise_service.get_exercise(db, user_id, ex_id) or {}
        facts.extend(_exercise_facts(db, user_id, ex_id, doc, window,
                                     start, end))

    # 会话级周期事实：直接复用「周期统计」接口同一函数
    ps = period_summary(db, user_id, days)
    srcs = [_src(row["id"], row["revision"])
            for row, data in _iter_training_rows(db, user_id)
            if start <= session_local_date(row["created_at"], data) <= end]
    wend = window["end"].replace("-", "")
    for metric, unit, calc in (
            ("sessions", "次", "period_summary_sessions"),
            ("training_days", "天", "period_summary_training_days"),
            ("working_sets", "组", "period_summary_working_sets"),
            ("volume", "kg", "period_summary_volume"),
            ("avg_duration_min", "分钟", "period_summary_avg_duration")):
        value = ps.get(metric)
        facts.append(_fact(
            f"{metric}-{wend}", metric, value, unit, "session", window, srcs,
            calc,
            "observed" if value is not None else "insufficient"))

    facts.extend(_plan_adherence_facts(db, user_id, window, start, end))
    return {
        "user_id": user_id,
        "window": window,
        "facts": facts,
        "exercises_covered": valid,
        "notes": notes,
        "caliber": "与「我的表现」（exercise_metrics）、「周期统计」"
                   "（period_summary）同源同口径；e1RM 为 Epley 估算",
    }


def exercise_progress(db, user_id: str, exercise_id: str,
                      window_days: int = 60) -> dict:
    """单动作进度（M6.5-1 工具用）：事实 + 逐会话序列（供趋势分析）。"""
    from .. import exercise_service
    doc = exercise_service.get_exercise(db, user_id, exercise_id)
    if not doc:
        return {"exercise_id": exercise_id, "error": "动作不存在（或非本人自定义）"}
    facts = get_training_facts(db, user_id, window_days,
                               exercise_ids=[exercise_id])
    days = facts["window"]["days"]
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    sessions, _srcs = _sessions_in_window(db, user_id, exercise_id, start, end)
    series = [{"date": s["date"], "working_sets": s["working_sets"],
               "volume": s["volume"], "best_e1rm": s["best_e1rm"],
               "best_set": s["best_set"],
               "duration_total_s": s["duration_total_s"],
               "distance_total_m": s["distance_total_m"]}
              for s in reversed(sessions)]  # 旧→新
    return {
        "exercise_id": exercise_id,
        "name": doc.get("name"),
        "measurement_type": doc.get("measurement") or "weight_reps",
        "window": facts["window"],
        "facts": facts["facts"],
        "series": series,
        "caliber": facts["caliber"],
    }
