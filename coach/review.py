"""复盘引擎：从打卡数据算趋势，生成教练视角的数据叙事

职责划分（设计原则）：
- 本模块只做"确定性计算"（e1RM/周均体重/执行率/RPE 漂移）
- 叙事表达留给 LLM（Agent 把本模块的输出注入上下文后生成）
- 登录复盘（login_recap）是纯文本，不调 LLM，零成本
"""
from __future__ import annotations

from datetime import datetime, timedelta


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


# ---------- 趋势计算 ----------

def strength_trend(checkins: list[dict], exercise: str) -> list[tuple[str, float]]:
    """某动作每次训练的最好 e1RM，按日期升序"""
    by_day: dict[str, float] = {}
    for c in checkins:
        if c["type"] != "training":
            continue
        for ex in (c["data"].get("exercises") or []):
            if exercise not in (ex.get("name") or ""):
                continue
            score = e1rm(ex.get("weight_kg"), ex.get("reps"))
            if score is None:
                continue
            day = _day(c)
            by_day[day] = max(score, by_day.get(day, 0))
    return sorted(by_day.items())


def weekly_weight(checkins: list[dict], weeks: int = 4) -> list[tuple[str, float]]:
    """按 ISO 周聚合体重均值，返回最近 N 周"""
    by_week: dict[str, list[float]] = {}
    for c in checkins:
        if c["type"] != "body":
            continue
        w = c["data"].get("weight_kg")
        if not w:
            continue
        iso = _parse(c["at"]).isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        by_week.setdefault(key, []).append(float(w))
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
    for c in checkins:
        if c["type"] != "training":
            continue
        for ex in (c["data"].get("exercises") or []):
            if exercise in (ex.get("name") or "") and ex.get("rpe") and ex.get("weight_kg"):
                points.append((_day(c), ex["weight_kg"], ex["rpe"]))
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


# ---------- 汇总与叙事 ----------

def build_summary(db, user_id: str, plan: dict | None) -> dict:
    """聚合所有指标（确定性计算，供 LLM 引用）"""
    checkins = db.list_checkins(user_id, limit=200)
    # 分母用计划实际排的天数（不是用户声称的天数）
    planned = len((plan or {}).get("schedule") or []) \
        or (plan or {}).get("days_per_week", 3)
    main_ex = _main_exercise(plan)
    return {
        "total_checkins": len(checkins),
        "days_since_last": days_since_last(checkins),
        "adherence": adherence(checkins, planned),
        "weight_trend": weekly_weight(checkins),
        "main_exercise": main_ex,
        "strength_trend": strength_trend(checkins, main_ex) if main_ex else [],
        "rpe_drift": rpe_drift(checkins, main_ex) if main_ex else None,
        "recent": [_brief(c) for c in checkins[:5]],
    }


def _main_exercise(plan: dict | None) -> str:
    """取计划第一个训练日的第一个动作作为追踪主项"""
    if not plan:
        return "深蹲"
    try:
        return plan["schedule"][0]["exercises"][0]["name"]
    except (IndexError, KeyError):
        return "深蹲"


def _brief(c: dict) -> str:
    """一条打卡的一句话摘要"""
    d, data = _day(c), c["data"]
    if c["type"] == "training":
        exs = data.get("exercises") or []
        parts = []
        for ex in exs[:3]:
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
    if len(s["strength_trend"]) >= 2:
        first, last = s["strength_trend"][0], s["strength_trend"][-1]
        delta = round(last[1] - first[1], 1)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(
            f"· {s['main_exercise']} e1RM：{first[1]} → {last[1]}kg（{arrow}{abs(delta)}）"
        )
    if len(s["weight_trend"]) >= 2:
        first, last = s["weight_trend"][0], s["weight_trend"][-1]
        delta = round(last[1] - first[1], 1)
        lines.append(f"· 周均体重：{first[1]} → {last[1]}kg（{delta:+}）")
    if s["rpe_drift"] == "rising":
        lines.append(f"· ⚠️ {s['main_exercise']} 同重量 RPE 持续上升，疲劳在累积，考虑卸载")
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
    if s["strength_trend"]:
        pts = " → ".join(f"{v}kg" for _, v in s["strength_trend"][-4:])
        lines.append(f"{s['main_exercise']} e1RM 趋势：{pts}")
    if s["weight_trend"]:
        pts = " → ".join(f"{v}" for _, v in s["weight_trend"])
        lines.append(f"周均体重趋势：{pts}")
    if s["rpe_drift"] == "rising":
        lines.append(f"⚠️ {s['main_exercise']} RPE 漂移上升（疲劳信号）")
    if s["recent"]:
        lines.append("最近打卡：")
        lines += [f"  - {b}" for b in s["recent"]]
    return "\n".join(lines)

