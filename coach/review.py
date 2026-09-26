"""复盘引擎：从打卡数据算趋势，生成教练视角的数据叙事

职责划分（设计原则）：
- 本模块只做"确定性计算"（e1RM/周均体重/执行率/RPE 漂移）
- 叙事表达留给 LLM（Agent 把本模块的输出注入上下文后生成）
- 登录复盘（login_recap）是纯文本，不调 LLM，零成本

R2 数据契约：
- 动作按动作库 id 匹配（读侧归一，兼容归一前落库的旧数据），根治 17.2 L1
- 追踪计划内全部 track_e1rm 动作，不再只追第一个（17.2 L3）
- 逐行容错：坏数据行跳过并计数，绝不让一条脏打卡炸掉整个复盘（17.2 D1）
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .exercises import library as exercise_lib
from .validate import _to_number, _to_reps


# ---------- 基础计算 ----------

def e1rm(weight_kg: float, reps: int | None) -> float | None:
    """估算单次极限（Epley 公式）。无次数数据时退化为重量本身。"""
    if not weight_kg:
        return None
    if not reps or reps <= 1:
        return float(weight_kg)
    return round(weight_kg * (1 + reps / 30.0), 1)


def _day(checkin: dict) -> str:
    return checkin["at"][:10]


def _parse(at: str) -> datetime:
    return datetime.fromisoformat(at)


def _same_exercise(name_a: str, name_b: str) -> bool:
    """按动作库 id 判断两个叫法是否同一动作；都未入库时退化为子串匹配"""
    id_a, _, _ = exercise_lib.normalize(name_a or "")
    id_b, _, _ = exercise_lib.normalize(name_b or "")
    if id_a and id_b:
        return id_a == id_b
    return bool(name_a and name_b and (name_a in name_b or name_b in name_a))


def _iter_exercise_rows(checkins: list[dict]):
    """逐条产出 (日期, ex dict)，坏行跳过（D1 读侧容错）"""
    for c in checkins:
        if c["type"] != "training" or not isinstance(c.get("data"), dict):
            continue
        for ex in (c["data"].get("exercises") or []):
            if isinstance(ex, dict) and ex.get("name"):
                yield _day(c), ex


# ---------- 趋势计算 ----------

def strength_trend(checkins: list[dict], exercise: str) -> list[tuple[str, float]]:
    """某动作每次训练的最好 e1RM，按日期升序"""
    by_day: dict[str, float] = {}
    for day, ex in _iter_exercise_rows(checkins):
        if not _same_exercise(exercise, ex.get("name", "")):
            continue
        w = _to_number(ex.get("weight_kg"))
        score = e1rm(w, _to_reps(ex.get("reps")))
        if score is None:
            continue
        by_day[day] = max(score, by_day.get(day, 0))
    return sorted(by_day.items())


def weekly_weight(checkins: list[dict], weeks: int = 4) -> list[tuple[str, float]]:
    """按 ISO 周聚合体重均值，返回最近 N 周"""
    by_week: dict[str, list[float]] = {}
    for c in checkins:
        if c["type"] != "body" or not isinstance(c.get("data"), dict):
            continue
        w = _to_number(c["data"].get("weight_kg"))
        if not w:
            continue
        try:
            iso = _parse(c["at"]).isocalendar()
        except ValueError:
            continue
        key = f"{iso[0]}-W{iso[1]:02d}"
        by_week.setdefault(key, []).append(w)
    result = [(k, round(sum(v) / len(v), 1)) for k, v in by_week.items()]
    return sorted(result)[-weeks:]


def adherence(checkins: list[dict], planned_days: int, window_days: int = 7) -> dict:
    """执行率：最近 window_days 内训练打卡天数 / 计划天数"""
    cutoff = datetime.now() - timedelta(days=window_days)
    trained = {
        _day(c) for c in checkins
        if c["type"] == "training" and _parse(c["at"]) >= cutoff
    }
    return {
        "trained_days": len(trained),
        "planned_days": planned_days,
        "rate": round(len(trained) / planned_days, 2) if planned_days else 0,
    }


def days_since_last(checkins: list[dict]) -> int | None:
    """距上次打卡天数"""
    if not checkins:
        return None
    last = max(_parse(c["at"]) for c in checkins)
    return (datetime.now() - last).days


def rpe_drift(checkins: list[dict], exercise: str, window: int = 6) -> str | None:
    """同一重量下 RPE 持续上升 = 疲劳累积。返回 'rising'/'stable'/None"""
    points = []
    for day, ex in _iter_exercise_rows(checkins):
        if not _same_exercise(exercise, ex.get("name", "")):
            continue
        rpe = _to_number(ex.get("rpe"))
        w = _to_number(ex.get("weight_kg"))
        if rpe and w:
            points.append((day, w, rpe))
    if len(points) < 2:
        return None
    points.sort(key=lambda p: p[0])
    points = points[-window:]
    # 取最近一次使用的重量，只看该重量下的 RPE 序列
    latest_weight = points[-1][1]
    rpes = [r for _, w, r in points if w == latest_weight]
    if len(rpes) < 2:
        return None
    return "rising" if rpes[-1] - rpes[0] >= 1 else "stable"


# ---------- 追踪主项（L3：全部 track_e1rm 动作） ----------

def _tracked_exercises(plan: dict | None) -> list[str]:
    """计划内所有在动作库中 track_e1rm=true 的动作（官方名，按计划顺序）"""
    if not plan:
        return ["深蹲"]
    names = [ex.get("name", "") for day in (plan.get("schedule") or [])
             for ex in (day.get("exercises") or [])]
    tracked = exercise_lib.track_e1rm_names(names)
    if tracked:
        return tracked[:4]
    try:
        return [plan["schedule"][0]["exercises"][0]["name"]]
    except (IndexError, KeyError):
        return ["深蹲"]


# ---------- 汇总与叙事 ----------

def build_summary(db, user_id: str, plan: dict | None) -> dict:
    """聚合所有指标（确定性计算，供 LLM 引用）"""
    checkins = db.list_checkins(user_id, limit=200)
    # 分母用计划实际排的天数（不是用户声称的天数）
    planned = len((plan or {}).get("schedule") or []) \
        or (plan or {}).get("days_per_week", 3)
    tracked = _tracked_exercises(plan)
    trends = {}
    for name in tracked:
        t = strength_trend(checkins, name)
        if t:
            trends[name] = t
    drifts = {}
    for name in tracked:
        d = rpe_drift(checkins, name)
        if d:
            drifts[name] = d
    main_ex = tracked[0] if tracked else None
    return {
        "total_checkins": len(checkins),
        "days_since_last": days_since_last(checkins),
        "adherence": adherence(checkins, planned),
        "weight_trend": weekly_weight(checkins),
        "main_exercise": main_ex,
        "strength_trend": trends.get(main_ex, []),
        "strength_trends": trends,
        "rpe_drift": drifts.get(main_ex),
        "rpe_drifts": drifts,
        "recent": [_brief(c) for c in checkins[:5]],
    }


def _brief(c: dict) -> str:
    """一条打卡的一句话摘要"""
    d, data = _day(c), c["data"]
    if c["type"] == "training":
        exs = data.get("exercises") or []
        parts = []
        for ex in exs[:3]:
            if not isinstance(ex, dict):
                continue
            w = f"{ex['weight_kg']}kg" if ex.get("weight_kg") else ""
            sr = ""
            if ex.get("sets") and ex.get("reps"):
                sr = f" {ex['sets']}×{ex['reps']}"
            parts.append(f"{ex.get('name', '?')}{w}{sr}".strip())
        note = data.get("note") or data.get("raw") or ""
        return f"{d} 训练：{'、'.join(parts)}" + (f"（{note[:20]}）" if note else "")
    if c["type"] == "body":
        return f"{d} 体测：{data.get('weight_kg', '?')}kg"
    return f"{d} 饮食记录"


def login_recap(db, user_id: str, plan: dict | None) -> str:
    """登录复盘 banner（方案 A：零 LLM 成本，启动时展示）"""
    s = build_summary(db, user_id, plan)
    if s["total_checkins"] == 0:
        return ""

    lines = ["📋 快速回顾"]
    if s["days_since_last"] is not None:
        d = s["days_since_last"]
        if d == 0:
            lines.append("· 今天已经打过卡了 👍")
        elif d == 1:
            lines.append("· 昨天刚练过，恢复得怎么样？")
        elif d <= 3:
            lines.append(f"· 距上次打卡 {d} 天")
        else:
            lines.append(f"· ⚠️ 已经 {d} 天没打卡了，是太忙还是遇到问题了？")

    ad = s["adherence"]
    lines.append(
        f"· 本周执行率：{ad['trained_days']}/{ad['planned_days']} 练"
        f"（{int(ad['rate'] * 100)}%）"
    )
    for name, trend in s["strength_trends"].items():
        if len(trend) < 2:
            continue
        first, last = trend[0], trend[-1]
        delta = round(last[1] - first[1], 1)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"· {name} e1RM：{first[1]} → {last[1]}kg（{arrow}{abs(delta)}）")
    if len(s["weight_trend"]) >= 2:
        first, last = s["weight_trend"][0], s["weight_trend"][-1]
        delta = round(last[1] - first[1], 1)
        lines.append(f"· 周均体重：{first[1]} → {last[1]}kg（{delta:+}）")
    for name, drift in s["rpe_drifts"].items():
        if drift == "rising":
            lines.append(f"· ⚠️ {name} 同重量 RPE 持续上升，疲劳在累积，考虑卸载")
    return "\n".join(lines)


def review_context_text(db, user_id: str, plan: dict | None) -> str:
    """注入 system prompt 的"近期动态"段（相关性原则：有数据才给）"""
    s = build_summary(db, user_id, plan)
    if s["total_checkins"] == 0:
        return "（暂无打卡数据）"
    lines = [
        f"累计打卡 {s['total_checkins']} 次，距上次 {s['days_since_last']} 天",
        f"本周执行率 {s['adherence']['trained_days']}/{s['adherence']['planned_days']}",
    ]
    for name, trend in s["strength_trends"].items():
        pts = " → ".join(f"{v}kg" for _, v in trend[-3:])
        lines.append(f"{name} e1RM 趋势：{pts}")
    if s["weight_trend"]:
        pts = " → ".join(f"{v}" for _, v in s["weight_trend"])
        lines.append(f"周均体重趋势：{pts}")
    for name, drift in s["rpe_drifts"].items():
        if drift == "rising":
            lines.append(f"⚠️ {name} RPE 漂移上升（疲劳信号）")
    if s["recent"]:
        lines.append("最近打卡：")
        lines += [f"  - {b}" for b in s["recent"]]
    return "\n".join(lines)
