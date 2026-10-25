"""趋势服务：多时间范围窗口选择 + 序列输出（前端图表直接可用）。

记录很少时只返回实际数据点（不拟合、不外推）。
"""
from __future__ import annotations

from .body_metrics import METRIC_LABELS, metric_series, metric_change


def trend_for(db, user_id: str, field: str, days: int | None) -> dict:
    """某指标在某窗口的趋势（days=None 表示全部）。"""
    if field not in METRIC_LABELS:
        raise ValueError(f"不支持的指标 {field!r}")
    measurements = db.list_body_measurements(user_id)
    start = None
    if days:
        from datetime import date, timedelta
        start = (date.today() - timedelta(days=days - 1)).isoformat()
    series = metric_series(measurements, field, start)
    label, unit = METRIC_LABELS[field]
    return {
        "metric": field, "label": label, "unit": unit,
        "days_window": days,
        "points": [{"date": p["date"], "value": p["value"]} for p in series],
        "change": metric_change(series),
        "note": ("记录不足两点，仅显示实际数据点" if len(series) < 2
                 else "首末记录比较（可计算的观察；短期波动不解释为脂肪/肌肉变化）"),
    }
