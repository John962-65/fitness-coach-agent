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
- 同一计划日标签 + 同一本地日期只计一次（同天多次训练≠多个任务）；
- 临时替换发生的会话仍算计划日执行，但单独标记 replacement_sessions，
  不把被替换动作视为原计划动作的等价完成。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from .activity_class import (
    CLASS_INTERVAL, CLASS_STEADY_CARDIO, classified_rows, classification_quality,
)
from .exercise_metrics import (entry_identity, entry_set_type,
                               exercise_sessions, session_local_date)
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


def _type_facts(group: list[dict], mtype: str, base: str, window: dict,
                exercise_id: str, quality: dict) -> list[dict]:
    """单一记录类型会话组的分型主指标事实（口径与「我的表现」完全一致）。"""
    srcs = [_src(s["checkin_id"], s.get("revision") or 0) for s in group]
    facts: list[dict] = []
    strength_sets = [st for s in group for st in s["sets"]
                     if st.get("activity_class") == "strength"]
    noninterval_sets = [st for s in group for st in s["sets"]
                        if st.get("activity_class") != "interval"]
    if mtype == "weight_reps":
        heavy = max(
            (st for st in strength_sets
             if st["weight_kg"] is not None),
            key=lambda st: st["weight_kg"], default=None)
        if heavy:
            facts.append(_fact(
                f"heaviest-set-{base}", "heaviest-set", heavy["weight_kg"],
                "kg", mtype, window, srcs,
                "max_working_set_weight_excluding_warmup", "observed",
                exercise_id=exercise_id, reps=heavy["reps"], **quality))
        best = max((s for s in group if s["best_e1rm"]),
                   key=lambda s: s["best_e1rm"], default=None)
        if best:
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
            (st for st in strength_sets if st["reps"]),
            key=lambda st: st["reps"], default=None)
        if best_reps:
            facts.append(_fact(
                f"max-reps-{base}", "max-reps", best_reps["reps"], "次",
                mtype, window, srcs, "max_working_set_reps", "observed",
                exercise_id=exercise_id,
                added_weight_kg=best_reps.get("added_weight_kg"), **quality))
        added = [st["added_weight_kg"] for st in strength_sets
                 if st.get("added_weight_kg")]
        if added:
            facts.append(_fact(
                f"max-added-weight-{base}", "max-added-weight", max(added),
                "kg", mtype, window, srcs, "max_added_weight_working_sets",
                "observed", exercise_id=exercise_id, **quality))
    elif mtype == "assisted_reps":
        best_reps = max(
            (st for st in strength_sets if st["reps"]),
            key=lambda st: st["reps"], default=None)
        if best_reps:
            facts.append(_fact(
                f"max-reps-{base}", "max-reps", best_reps["reps"], "次",
                mtype, window, srcs, "max_working_set_reps", "observed",
                exercise_id=exercise_id,
                assistance_kg=best_reps.get("assistance_kg"), **quality))
        assist = [st["assistance_kg"] for st in strength_sets
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
            (st for st in noninterval_sets if st.get("duration_seconds")),
            key=lambda st: st["duration_seconds"], default=None)
        if longest:
            facts.append(_fact(
                f"longest-set-{base}", "longest-set",
                longest["duration_seconds"], "秒", mtype, window, srcs,
                "max_working_set_duration", "observed",
                exercise_id=exercise_id, **quality))
    elif mtype == "distance_time":
        far = max(
            (st for st in noninterval_sets if st.get("distance_m")),
            key=lambda st: st["distance_m"], default=None)
        if far:
            facts.append(_fact(
                f"farthest-distance-{base}", "farthest-distance",
                far["distance_m"], "米", mtype, window, srcs,
                "max_working_set_distance", "observed",
                exercise_id=exercise_id, **quality))
    if mtype in ("weight_reps", "bodyweight_reps"):
        facts.append(_fact(
            f"volume-{base}", "volume",
            round(sum(s["volume"] for s in group)), "kg", mtype,
            window, srcs,
            ("sum_weight_times_reps_working_sets" if mtype == "weight_reps"
             else "sum_added_weight_times_reps_working_sets"),
            "observed", exercise_id=exercise_id, **quality))
    return facts


def _exercise_facts(db, user_id: str, exercise_id: str, doc: dict,
                    window: dict, start: str, end: str) -> list[dict]:
    sessions, srcs = _sessions_in_window(db, user_id, exercise_id, start, end)
    # 每次会话的实际记录类型（库声明兜底）——混合类型分开统计（复查 P1-2）
    types: list[str] = []
    for s in sessions:
        t = entry_set_type(s["sets"]) or doc.get("measurement") or "weight_reps"
        s["_mtype"] = t
        if t not in types:
            types.append(t)
    # fact_id 必须唯一标识统计事实：动作 + 起始 + 结束（+ 类型后缀）。
    # 只含结束日期时，同日查询 7 天与 30 天窗口会产生重复 ID（复查 P1-1）。
    sc, ec = window["start"].replace("-", ""), window["end"].replace("-", "")
    base = f"{exercise_id}-{sc}-{ec}"
    gaps = _max_gap_days([s["date"] for s in sessions])
    corrected = sum(1 for s in sessions if (s.get("revision") or 0) > 0)
    quality = {
        "sessions": len(sessions),
        "date_gaps_max_days": gaps,
        "corrected_records": corrected,
    }
    # P5-A：复杂组说明（逻辑组=1，容量=各执行段和；单侧左右分别执行）
    methods = sorted({st.get("method") for s in sessions for st in s["sets"]
                      if st.get("method") and st["method"] != "straight_set"})
    if methods:
        label = {"drop_set": "递减组", "rest_pause": "休息暂停组",
                 "unilateral": "单侧训练"}.get(methods[0], methods[0])
        quality["complex_methods"] = methods
        quality.setdefault("notes", []).append(
            f"含{label}等复杂组：工作组按逻辑组计数（每条记录=1 组），"
            "容量按各执行段实际完成求和" + ("；单侧左右分别执行" if "unilateral" in methods else "")
            + "，不按段重复计组数")
    if corrected:
        quality["notes"] = [f"含已纠错记录 {corrected} 条（按当前有效版本统计）"]
    if len(sessions) == 1:
        quality.setdefault("notes", []).append("窗口内仅 1 次训练，趋势不可判")
    if len(types) > 1:
        quality.setdefault("notes", []).append(
            f"窗口内存在多种记录类型（{'、'.join(types)}）：已按类型分开统计，"
            "跨类型结果不可直接比较")
    if not sessions:
        # 已确认的"零次训练"是观察结果（observed 0），不是数据缺失——
        # 不与"表现类指标数据不足"（insufficient, value=None）混用（复查 P1-1）
        return [_fact(f"frequency-{base}", "sessions", 0, "次",
                      doc.get("measurement") or "weight_reps",
                      window, [], "count_training_sessions_by_local_date",
                      "observed", exercise_id=exercise_id, **quality,
                      note="窗口内无该动作训练记录（确认为 0 次）")]

    facts = [
        _fact(f"frequency-{base}", "sessions", len(sessions), "次",
              types[0] if len(types) == 1 else "mixed",
              window, srcs, "count_training_sessions_by_local_date",
              "observed", exercise_id=exercise_id, **quality),
        _fact(f"frequency-per-week-{base}", "sessions-per-week",
              round(len(sessions) * 7 / window["days"], 1), "次/周",
              types[0] if len(types) == 1 else "mixed",
              window, srcs, "sessions_x7_over_window_days", "observed",
              exercise_id=exercise_id, **quality),
        _fact(f"working-sets-{base}", "working-sets",
              sum(s["working_sets"] for s in sessions), "组",
              types[0] if len(types) == 1 else "mixed",
              window, srcs, "sum_working_sets_excluding_warmup", "observed",
              exercise_id=exercise_id, **quality),
    ]
    if len(types) == 1:
        facts.extend(_type_facts(sessions, types[0], base, window,
                                 exercise_id, quality))
    else:
        for t in types:
            group = [s for s in sessions if s["_mtype"] == t]
            facts.extend(_type_facts(group, t, f"{base}-{t}", window,
                                     exercise_id, quality))

    # RPE（用户主观自报，只汇总不推断）
    rpes = [st.get("rpe") for s in sessions for st in s["sets"]
            if isinstance(st.get("rpe"), (int, float))]
    if rpes:
        facts.append(_fact(
            f"rpe-average-{base}", "rpe-average",
            round(sum(rpes) / len(rpes), 1), "RPE",
            types[0] if len(types) == 1 else "mixed", window, srcs,
            "user_reported_mean_working_sets", "observed",
            exercise_id=exercise_id,
            note="RPE 为用户主观自报，非客观测量", **quality))

    # P5-B3：动作级有氧与间歇事实（与全局周期/月历同一分类口径）
    steady_seconds = sum(s.get("steady_cardio_seconds") or 0 for s in sessions)
    steady_distance = sum(s.get("steady_cardio_distance_m") or 0 for s in sessions)
    if steady_seconds > 0:
        facts.append(_fact(
            f"steady-cardio-seconds-{base}", "steady-cardio-seconds",
            round(steady_seconds), "秒", "cardio", window, srcs,
            "sum_steady_cardio_duration_excluding_interval", "observed",
            exercise_id=exercise_id, **quality))
    if steady_distance > 0:
        facts.append(_fact(
            f"steady-cardio-distance-{base}", "steady-cardio-distance",
            round(steady_distance), "米", "cardio", window, srcs,
            "sum_steady_cardio_distance_excluding_interval", "observed",
            exercise_id=exercise_id, **quality))
        if steady_seconds > 0:
            pace = steady_seconds / (steady_distance / 1000)
            facts.append(_fact(
                f"steady-cardio-pace-{base}", "steady-cardio-pace",
                round(pace, 1), "秒/公里", "cardio", window, srcs,
                "duration_seconds_over_distance_km", "observed",
                exercise_id=exercise_id,
                note="仅由有距离的记录计算；不同运动类型不可直接类比",
                **quality))
    interval_work = sum(s.get("interval_work_seconds") or 0 for s in sessions)
    if interval_work > 0 or any(
            s.get("activity_class") == "interval" for s in sessions):
        facts.append(_fact(
            f"interval-work-seconds-{base}", "interval-work-seconds",
            interval_work, "秒", "hiit", window, srcs,
            "sum_hiit_work_seconds_done", "observed",
            exercise_id=exercise_id, **quality))
        facts.append(_fact(
            f"interval-rest-seconds-{base}", "interval-rest-seconds",
            sum(s.get("interval_rest_seconds") or 0 for s in sessions),
            "秒", "hiit", window, srcs, "sum_hiit_rest_seconds_done",
            "observed", exercise_id=exercise_id, **quality))
        facts.append(_fact(
            f"interval-elapsed-seconds-{base}", "interval-elapsed-seconds",
            sum(s.get("interval_elapsed_seconds") or 0 for s in sessions),
            "秒", "hiit", window, srcs,
            "sum_hiit_recorded_elapsed_seconds", "observed",
            exercise_id=exercise_id, **quality))
        facts.append(_fact(
            f"interval-rounds-{base}", "interval-rounds",
            sum(s.get("interval_completed_rounds") or 0 for s in sessions),
            "轮", "hiit", window, srcs, "sum_hiit_completed_rounds",
            "observed", exercise_id=exercise_id,
            planned=sum(s.get("interval_planned_rounds") or 0 for s in sessions),
            skipped=sum(s.get("interval_skipped_rounds") or 0 for s in sessions),
            **quality))
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
    replacement_sessions: list[str] = []
    for row, data in _iter_training_rows(db, user_id):
        local = session_local_date(row["created_at"], data)
        if not (start <= local <= end):
            continue
        meta = data.get("session_meta") if isinstance(
            data.get("session_meta"), dict) else {}
        replaced = sum(
            1 for ex in data.get("exercises") or []
            if isinstance(ex, dict) and (
                ex.get("session_replacement_of")
                or isinstance(ex.get("session_replacement"), dict)))
        if replaced:
            replacement_sessions.append(_src(row["id"], row["revision"]))
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
              replacement_sessions=len(replacement_sessions),
              note=("自由/模板训练不计入计划完成；同日多次训练同一计划日只计一次；"
                    "临时替换按会话完成记录，但不视为原计划动作等价完成"
                    + (f"；含临时替换会话 {len(replacement_sessions)} 次"
                       if replacement_sessions else "")
                    + (f"；窗口内另有自由训练 {free_sessions} 次（不计入）"
                       if free_sessions else ""))),
    ]
    if replacement_sessions:
        facts.append(_fact(
            f"plan-replacement-sessions-{base}", "plan-replacement-sessions",
            len(replacement_sessions), "次", "session", window,
            replacement_sessions, "sessions_with_session_replacement",
            "observed",
            note="只表示发生临时替换；原计划动作完成情况不自动等同于实际动作"))
    if scheduled > 0:
        facts.append(_fact(
            f"plan-adherence-{base}", "plan-adherence",
            round(len(completed) / scheduled, 2), "比率", "session", window,
            srcs, "plan_completed_over_scheduled", status,
            replacement_sessions=len(replacement_sessions)))
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
    sc, ec = window["start"].replace("-", ""), window["end"].replace("-", "")
    for metric, unit, calc in (
            ("sessions", "次", "period_summary_sessions"),
            ("training_days", "天", "period_summary_training_days"),
            ("working_sets", "组", "period_summary_working_sets"),
            ("volume", "kg", "period_summary_volume"),
            ("avg_duration_min", "分钟", "period_summary_avg_duration")):
        value = ps.get(metric)
        facts.append(_fact(
            f"{metric}-{sc}-{ec}", metric, value, unit, "session", window,
            srcs, calc,
            "observed" if value is not None else "insufficient"))
    classification = ps.get("classification") or {}
    for metric, unit, calc in (
            ("training_sessions", "次", "period_summary_training_sessions"),
            ("strength_working_sets", "组", "period_summary_strength_working_sets"),
            ("strength_volume_kg", "kg", "period_summary_strength_volume_kg"),
            ("steady_cardio_seconds", "秒", "period_summary_steady_cardio_seconds"),
            ("steady_cardio_distance_m", "米",
             "period_summary_steady_cardio_distance_m"),
            ("interval_work_seconds", "秒", "period_summary_interval_work_seconds"),
            ("interval_rest_seconds", "秒", "period_summary_interval_rest_seconds"),
            ("interval_elapsed_seconds", "秒",
             "period_summary_interval_elapsed_seconds")):
        value = ps.get(metric)
        facts.append(_fact(
            f"{metric.replace('_', '-')}-{sc}-{ec}", metric,
            value, unit, "session", window, srcs, calc,
            "observed" if value is not None else "insufficient",
            classification=classification))

    facts.extend(_plan_adherence_facts(db, user_id, window, start, end))
    facts.extend(_cardio_interval_facts(db, user_id, window, start, end))
    return {
        "user_id": user_id,
        "window": window,
        "facts": facts,
        "exercises_covered": valid,
        "notes": notes,
        "caliber": "与「我的表现」（exercise_metrics）、「周期统计」"
                   "（period_summary）同源同口径；e1RM 为 Epley 估算",
    }


def _cardio_interval_facts(db, user_id: str, window: dict,
                           start: str, end: str) -> list[dict]:
    """有氧与间歇事实：统一分类后累计，HIIT 不重复计入持续性有氧。"""
    cardio_sessions: set[int] = set()
    cardio_seconds = 0.0
    cardio_distance = 0.0
    cardio_srcs: list[str] = []
    interval_sessions: set[int] = set()
    planned_rounds = 0
    completed_rounds = 0
    work_seconds = 0
    rest_seconds = 0
    elapsed_seconds = 0
    interval_srcs: list[str] = []
    skipped_count = 0
    ended_early = 0
    classifications: list[dict] = []
    for row, data in _iter_training_rows(db, user_id):
        local = session_local_date(row["created_at"], data)
        if not (start <= local <= end):
            continue
        src = _src(row["id"], row["revision"])
        session_steady = False
        session_interval = False
        for _ex, _doc, st, cls in classified_rows(db, user_id, data):
            classifications.append(cls)
            category = cls["class"]
            if category == CLASS_INTERVAL:
                session_interval = True
                h = st.get("hiit") or {}
                completed_rounds += int(h.get("completed_rounds") or 0)
                planned_rounds += int(h.get("planned_rounds") or 0)
                work_seconds += int(h.get("work_seconds_done") or 0)
                rest_seconds += int(h.get("rest_seconds_done") or 0)
                elapsed_seconds += int(st.get("duration_seconds") or 0)
                skipped_count += len(h.get("skipped") or [])
                if h.get("ended_early"):
                    ended_early += 1
            elif category == CLASS_STEADY_CARDIO:
                session_steady = True
                cardio_seconds += float(st.get("duration_seconds") or 0)
                cardio_distance += float(st.get("distance_m") or 0)
        if session_steady:
            cardio_sessions.add(row["id"])
            cardio_srcs.append(src)
        if session_interval:
            interval_sessions.add(row["id"])
            interval_srcs.append(src)

    w = window
    sc = w["start"].replace("-", "")
    ec = w["end"].replace("-", "")
    quality = classification_quality(classifications)
    out: list[dict] = []
    all_c_srcs = sorted(set(cardio_srcs))
    out.append(_fact(
        f"steady-cardio-sessions-{sc}-{ec}", "steady-cardio-sessions",
        len(cardio_sessions), "次", "cardio", w, all_c_srcs,
        "sessions_with_steady_cardio_excluding_interval",
        "observed" if cardio_sessions else "insufficient",
        classification=quality,
        note="持续性有氧=分类后的 steady_cardio；有效 HIIT 不重复计入"))
    out.append(_fact(
        f"steady-cardio-seconds-{sc}-{ec}", "steady-cardio-seconds",
        round(cardio_seconds), "秒", "cardio", w, all_c_srcs,
        "sum_steady_cardio_duration_excluding_interval",
        "observed" if cardio_seconds else "insufficient",
        classification=quality,
        note="不包含 HIIT 工作/休息秒数" if cardio_seconds else None))
    out.append(_fact(
        f"steady-cardio-distance-{sc}-{ec}", "steady-cardio-distance",
        round(cardio_distance), "米", "cardio", w, all_c_srcs,
        "sum_steady_cardio_distance_excluding_interval",
        "observed" if cardio_distance else "insufficient",
        classification=quality,
        note="无距离记录不生成配速；不同运动类型距离不可直接类比"
             if cardio_distance else None))
    # 兼容旧字段（语义固定为 steady_cardio，不含 interval）
    out.append(_fact(
        f"cardio-sessions-{sc}-{ec}", "cardio-sessions", len(cardio_sessions),
        "次", "cardio", w, all_c_srcs, "alias_of_steady_cardio_sessions",
        "observed" if cardio_sessions else "insufficient",
        classification=quality, deprecated=True))
    out.append(_fact(
        f"cardio-total-duration-{sc}-{ec}", "cardio-total-duration",
        round(cardio_seconds / 60, 1), "分钟", "cardio", w, all_c_srcs,
        "alias_of_steady_cardio_seconds",
        "observed" if cardio_seconds else "insufficient",
        classification=quality, deprecated=True))
    out.append(_fact(
        f"cardio-total-distance-{sc}-{ec}", "cardio-total-distance",
        round(cardio_distance / 1000, 2), "公里", "cardio", w, all_c_srcs,
        "alias_of_steady_cardio_distance",
        "observed" if cardio_distance else "insufficient",
        classification=quality, deprecated=True))
    out.append(_fact(
        f"interval-sessions-{sc}-{ec}", "interval-sessions",
        len(interval_sessions), "次", "hiit", w, interval_srcs,
        "sessions_with_valid_hiit_metadata",
        "observed" if interval_sessions else "insufficient",
        classification=quality))
    if interval_sessions:
        out.append(_fact(
            f"interval-planned-rounds-{sc}-{ec}", "interval-planned-rounds",
            planned_rounds, "轮", "hiit", w, interval_srcs,
            "sum_hiit_planned_rounds", "observed", classification=quality))
        out.append(_fact(
            f"interval-completed-rounds-{sc}-{ec}", "interval-completed-rounds",
            completed_rounds, "轮", "hiit", w, interval_srcs,
            "sum_hiit_completed_rounds", "observed",
            skipped=skipped_count, ended_early=ended_early,
            classification=quality,
            note="实际完成轮次；跳过/提前结束按真实执行计"))
        out.append(_fact(
            f"interval-skipped-rounds-{sc}-{ec}", "interval-skipped-rounds",
            skipped_count, "轮", "hiit", w, interval_srcs,
            "sum_hiit_skipped_rounds", "observed", classification=quality))
        out.append(_fact(
            f"interval-work-seconds-{sc}-{ec}", "interval-work-seconds",
            work_seconds, "秒", "hiit", w, interval_srcs,
            "sum_hiit_work_seconds_done", "observed", classification=quality,
            note="工作/休息/总经过时长分别累计；不折算力量容量"))
        out.append(_fact(
            f"interval-rest-seconds-{sc}-{ec}", "interval-rest-seconds",
            rest_seconds, "秒", "hiit", w, interval_srcs,
            "sum_hiit_rest_seconds_done", "observed", classification=quality))
        out.append(_fact(
            f"interval-elapsed-seconds-{sc}-{ec}", "interval-elapsed-seconds",
            elapsed_seconds, "秒", "hiit", w, interval_srcs,
            "sum_hiit_recorded_elapsed_seconds", "observed",
            classification=quality))
    return out


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
    series = [{"date": s["date"],
               "activity_class": s.get("activity_class"),
               "activity_classes": s.get("activity_classes") or [],
               "strength_working_sets": s.get("strength_working_sets", 0),
               "working_sets": s["working_sets"],
               "volume": s["volume"], "best_e1rm": s["best_e1rm"],
               "best_set": s["best_set"],
               "duration_total_s": s["duration_total_s"],
               "steady_cardio_seconds": s.get("steady_cardio_seconds"),
               "steady_cardio_distance_m": s.get("steady_cardio_distance_m"),
               "interval_work_seconds": s.get("interval_work_seconds"),
               "interval_rest_seconds": s.get("interval_rest_seconds"),
               "interval_elapsed_seconds": s.get("interval_elapsed_seconds"),
               "interval_planned_rounds": s.get("interval_planned_rounds"),
               "interval_completed_rounds": s.get("interval_completed_rounds"),
               "interval_skipped_rounds": s.get("interval_skipped_rounds"),
               "longest_set_s": s.get("longest_set_s"),
               "distance_total_m": s["distance_total_m"],
               "farthest_set_m": s.get("farthest_set_m")}
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
