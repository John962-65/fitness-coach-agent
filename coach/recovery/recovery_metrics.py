"""确定性恢复指标：只计算可观察结果，不发明综合评分、不过度推断。

- 训练负荷上下文复用 fact_service（不重复实现公式）；
- 主观量表均值/计数是"记录汇总"，不是医学指标；
- 缺失维度进入 data_quality，绝不反推。
"""
from __future__ import annotations

from datetime import date, timedelta

from ..analytics.fact_service import get_training_facts
from .checkin_service import SCALE_LABELS, SCALES

WINDOW_DAYS = 14


def _src(r: dict) -> str:
    return f"recovery:{r['id']}:revision:{r.get('revision') or 0}"


def _fact(fact_id, metric, value, unit, window, source_ids, calculation,
          status="observed", **quality):
    return {"fact_id": fact_id, "metric": metric, "value": value, "unit": unit,
            "measurement_type": "recovery", "window": window,
            "source_ids": source_ids, "calculation": calculation,
            "data_quality": quality or {}, "status": status}


def _window(days: int) -> dict:
    end = date.today()
    start = end - timedelta(days=days - 1)
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days}


def _scale_facts(records: list[dict], key: str, window: dict) -> dict | None:
    """某主观量表的窗口汇总（均值 + 高分计数）。缺失时返回 None。"""
    values = [r[key] for r in records if r.get(key) is not None]
    if not values:
        return None
    label = SCALE_LABELS[key][0]
    dq = {"reported": len(values), "missing": len(records) - len(values)}
    result = _fact(
        f"{key}-avg-{window['days']}d", f"{key}-avg",
        round(sum(values) / len(values), 2), "分(1-5)", window,
        [_src(r) for r in records if r.get(key) is not None],
        "mean_of_self_reported_scale", note=f"{label}为用户主观自报（1-5）",
        **dq)
    high = sum(1 for v in values if v >= 4)
    if key in ("fatigue", "muscle_soreness") and high:
        result["data_quality"]["high_reports"] = high
    return result


def recovery_snapshot(db, user_id: str, window_days: int = WINDOW_DAYS) -> dict:
    """恢复概览：窗口记录 + 各维度汇总 + 训练负荷上下文 + 数据质量。"""
    window = _window(window_days)
    records = db.list_recovery_checkins(user_id, window_days)  # 新→旧
    facts, observations, data_quality, limitations = [], [], {}, []

    for key in ("sleep_hours",) + SCALES:
        f = (_sleep_fact(records, window) if key == "sleep_hours"
             else _scale_facts(records, key, window))
        if f is None:
            data_quality[key] = "窗口内未记录"
            continue
        facts.append(f)
        label = SCALE_LABELS.get(key, (key,))[0] if key != "sleep_hours" else "睡眠时长"
        observations.append(f"{label}：均值 {f['value']}{f['unit']}"
                            f"（{f['data_quality'].get('reported', 0)}"
                            f"/{len(records)} 天有记录）")
        if f["data_quality"].get("high_reports"):
            label_hi = {"fatigue": "比较疲劳及以上", "muscle_soreness": "比较严重及以上"}.get(key)
            if label_hi:
                observations.append(
                    f"最近 {len(records)} 次恢复记录中有 {f['data_quality']['high_reports']} 次"
                    f"{label_hi}（{key}≥4 分，自报）")

    if not records:
        data_quality["records"] = 0
        limitations.append(f"最近 {window_days} 天没有任何恢复记录——"
                           "无法从训练量反推主观疲劳，请先记录")

    # 训练负荷上下文（复用训练事实，不重复实现）
    tf = get_training_facts(db, user_id, window_days)
    for f in tf["facts"]:
        if f["metric"] in ("sessions", "working_sets", "volume", "rpe-average") \
                and f["value"] is not None:
            facts.append(f)
    load_facts = [f for f in tf["facts"]
                  if f["metric"] in ("sessions", "working_sets", "volume",
                                     "rpe-average") and f["value"] is not None]
    if load_facts:
        parts = "；".join(
            f"{'训练' if f['metric'] == 'sessions' else '正式组' if f['metric'] == 'working_sets' else '容量' if f['metric'] == 'volume' else 'RPE 均值'}"
            f" {f['value']}{f['unit']}" for f in load_facts)
        observations.append(f"近 {window_days} 天训练负荷：{parts}")
    else:
        limitations.append(f"近 {window_days} 天没有训练记录——恢复上下文缺少负荷参照")

    # 酸痛区域汇总
    regions: dict[str, int] = {}
    for r in records:
        for region in r.get("soreness_regions") or []:
            regions[region] = regions.get(region, 0) + 1
    if regions:
        top = "、".join(f"{k}×{v}" for k, v in sorted(
            regions.items(), key=lambda x: -x[1])[:4])
        observations.append(f"自报酸痛区域（窗口内出现次数）：{top}")

    return {
        "window": window,
        "records_count": len(records),
        "records": [{"id": r["id"], "local_date": r["local_date"],
                     "revision": r.get("revision") or 0,
                     **{k: r.get(k) for k in ("sleep_hours",) + SCALES},
                     "soreness_regions": r.get("soreness_regions") or [],
                     "notes": r.get("notes")} for r in records[:14]],
        "facts": facts,
        "observations": observations,
        "data_quality": data_quality,
        "limitations": limitations,
    }


def _sleep_fact(records: list[dict], window: dict) -> dict | None:
    values = [r["sleep_hours"] for r in records if r.get("sleep_hours") is not None]
    if not values:
        return None
    return _fact(
        f"sleep-hours-avg-{window['days']}d", "sleep-hours-avg",
        round(sum(values) / len(values), 2), "小时", window,
        [_src(r) for r in records if r.get("sleep_hours") is not None],
        "mean_of_self_reported_sleep_hours",
        reported=len(values), missing=len(records) - len(values),
        note="睡眠时长为用户自报")
