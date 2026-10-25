"""确定性身体指标：最近测量 / 周期均值 / 变化 / 频率 / 缺口 / 来源可比性。

全部为可计算的观察结果；短期体重波动不解释为脂肪增减（限制在
trend_service 输出中明示）。事实结构与其他领域同构：
fact_id / metric / value / unit / window / source_ids(body:ID:revision:N) /
calculation / status / data_quality。
"""
from __future__ import annotations

from datetime import date, timedelta

METRIC_LABELS = {
    "weight_kg": ("体重", "kg"), "waist_cm": ("腰围", "cm"),
    "hip_cm": ("臀围", "cm"), "chest_cm": ("胸围", "cm"),
    "body_fat_percent": ("体脂率", "%"), "muscle_mass_kg": ("肌肉量", "kg"),
}

COMPARABILITY_NOTES = {
    "home_scale": "家用设备（如体脂秤为生物电阻抗估算，误差随水分状态变化）",
    "gym_scale": "健身房设备（估算口径同家用，需同设备同状态比较）",
    "tape": "皮尺围度（手法差异可带来 ±1-2cm）",
    "caliper": "皮褶钳（依赖测量者手法）",
    "dexa": "DEXA 扫描（参考精度较高，但仍为估算）",
    "bia": "生物电阻抗（估算，受水分/进食/时间影响）",
    "import": "旧记录导入（原始口径以历史记录为准）",
    "other": "其他方式",
}


def _src(m: dict) -> str:
    return f"body:{m['id']}:revision:{m.get('revision') or 0}"


def _fact(fact_id, metric, value, unit, window, source_ids, calculation,
          status="observed", **quality):
    return {"fact_id": fact_id, "metric": metric, "value": value, "unit": unit,
            "measurement_type": "body", "window": window,
            "source_ids": source_ids, "calculation": calculation,
            "data_quality": quality or {}, "status": status}


def _window(days: int | None) -> dict:
    if days is None:
        return {"start": None, "end": None, "days": None, "label": "全部"}
    end = date.today()
    start = end - timedelta(days=days - 1)
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days,
            "label": f"{days} 天"}


def latest_by_metric(measurements: list[dict]) -> dict[str, dict]:
    """每指标最近一次非空测量（列表按新→旧）。"""
    out: dict[str, dict] = {}
    for m in measurements:
        for field in METRIC_LABELS:
            if m.get(field) is not None and field not in out:
                out[field] = {"value": m[field], "measured_at": m["measured_at"],
                              "source_id": _src(m),
                              "method": m.get("measurement_method"),
                              "device_source": m.get("device_source")}
    return out


def metric_series(measurements: list[dict], field: str,
                  start: str | None = None) -> list[dict]:
    """某指标时间序列（旧→新）。"""
    pts = [{"date": m["local_date"], "value": m.get(field),
            "source_id": _src(m), "method": m.get("measurement_method"),
            "device_source": m.get("device_source")}
           for m in measurements if m.get(field) is not None
           and (start is None or m["local_date"] >= start)]
    return list(reversed(pts))


def metric_change(series: list[dict]) -> dict | None:
    """首末点变化（可计算的观察；不解释原因）。"""
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    days = None
    try:
        days = (date.fromisoformat(last["date"])
                - date.fromisoformat(first["date"])).days
    except ValueError:
        pass
    return {"first": first["value"], "last": last["value"],
            "delta": round(last["value"] - first["value"], 2),
            "first_date": first["date"], "last_date": last["date"],
            "span_days": days, "points": len(series)}


def summarize(measurements: list[dict], window_days: int | None = 30) -> dict:
    """身体概览：最近测量 / 窗口均值 / 变化 / 频率 / 缺口 / 来源说明。"""
    window = _window(window_days)
    win_rows = [m for m in measurements
                if window_days is None
                or (m["local_date"] >= (window["start"] or ""))]
    latest = latest_by_metric(measurements)
    facts, observations, limitations = [], [], []
    srcs_all = [_src(m) for m in win_rows[:50]]

    freq = len({m["local_date"] for m in win_rows})
    facts.append(_fact(
        f"measurement-days-{window['label']}", "measurement-days", freq, "天",
        window, srcs_all, "distinct_local_dates_with_any_metric",
        note="窗口内有测量记录的天数（同天多次按一天计）"))
    if window_days:
        facts.append(_fact(
            f"measurement-frequency-{window['label']}", "measurement-frequency",
            round(freq * 7 / max(window_days, 1), 1), "次/周", window, srcs_all,
            "measurement_days_x7_over_window_days"))

    # 记录缺口
    if win_rows:
        dates = sorted({m["local_date"] for m in win_rows})
        gaps = []
        ds = [date.fromisoformat(d) for d in dates]
        for a, b in zip(ds, ds[1:]):
            gap = (b - a).days
            if gap > 14:
                gaps.append(gap)
        if gaps:
            facts.append(_fact(
                f"max-gap-{window['label']}", "max-record-gap", max(gaps), "天",
                window, srcs_all, "max_consecutive_days_without_measurements",
                note="窗口内相邻两次测量的最大间隔"))
            observations.append(f"最长记录间隔 {max(gaps)} 天（>14 天）——"
                                "缺口期间的变化无法从数据判断")

    # 各指标：最近值 + 窗口均值 + 首末变化
    for field, (label, unit) in METRIC_LABELS.items():
        series_all = metric_series(measurements, field)
        if not series_all:
            continue
        latest_info = latest[field]
        facts.append(_fact(
            f"{field}-latest", f"{field}-latest", latest_info["value"], unit,
            {"start": None, "end": latest_info["measured_at"][:10], "days": None,
             "label": "最近"},
            [latest_info["source_id"]], "latest_non_null_measurement",
            method=latest_info["method"], device_source=latest_info["device_source"]))
        series_win = [p for p in metric_series(measurements, field,
                                               window["start"])] \
            if window_days else series_all
        if len(series_win) >= 2:
            avg = round(sum(p["value"] for p in series_win) / len(series_win), 2)
            facts.append(_fact(
                f"{field}-avg-{window['label']}", f"{field}-avg", avg, unit,
                window, [p["source_id"] for p in series_win[:50]],
                "mean_of_recorded_measurements"))
            change = metric_change(series_win)
            if change:
                facts.append(_fact(
                    f"{field}-change-{window['label']}", f"{field}-change",
                    change["delta"], unit, window,
                    [p["source_id"] for p in series_win[:50]],
                    "last_minus_first_recorded_value",
                    first=change["first"], last=change["last"],
                    span_days=change["span_days"]))
                observations.append(
                    f"{label}：{change['first']:g}{unit}（{change['first_date'][5:]}）→ "
                    f"{change['last']:g}{unit}（{change['last_date'][5:]}），"
                    f"变化 {change['delta']:+g}{unit}")
                if field in ("weight_kg",):
                    limitations.append(
                        "体重短期波动受水分/食物残渣/称量时间影响，"
                        "数日内的变化不宜直接解读为脂肪或肌肉变化")
        elif len(series_win) == 1:
            limitations.append(f"{label}窗口内仅 1 次测量，不构成趋势")

    # 来源可比性
    methods = sorted({m.get("measurement_method") for m in measurements
                      if m.get("measurement_method")})
    if len({(m.get("measurement_method"), m.get("device_source"))
            for m in measurements}) > 1:
        notes = [f"{m}：{COMPARABILITY_NOTES.get(m, '未知方式')}" for m in methods]
        limitations.append("存在多种测量方式/来源：" + "；".join(notes)
                           + "。不同来源的估算值不默认可比，跨来源比较仅供参考")
    if not measurements:
        limitations.append("还没有任何身体测量记录")

    return {"window": window, "measurement_days": freq,
            "latest": latest, "facts": facts,
            "observations": observations, "limitations": limitations,
            "total_records": len(measurements)}
