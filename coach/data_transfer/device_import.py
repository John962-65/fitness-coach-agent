"""P7-C：设备数据接入——第一阶段只读通用文件导入。

边界（总任务书 3.3）：
- 真实平台连接（HealthKit / Health Connect）需要原生桥接层，浏览器 PWA
  无法直接访问手机健康数据——可行性审计见 docs/p7c-device-feasibility.md；
  在确定可行之前不伪造设备集成。
- 本模块只接受用户显式导出的通用文件（CSV/JSON），只读入库：
  独立存储 imported_device_records，绝不与手动记录混算（防重复统计）；
- 不同设备的估算结果不可默认可比（保留 source_device/method）；
- 支持授权（显式导入）、撤销（删除记录）、重复识别（平台记录 ID 去重）、
  单位换算（仅白名单内确定性换算）、来源冲突保留（不合并）。
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime

# 指标白名单：canonical 单位 + 允许的输入单位换算
METRICS: dict[str, dict] = {
    "weight": {"unit": "kg", "conversions": {"lb": 0.45359237,
                                             "斤": 0.5}},
    "sleep_hours": {"unit": "h", "conversions": {"min": 1 / 60,
                                                 "s": 1 / 3600}},
    "heart_rate": {"unit": "bpm", "conversions": {}},
    "exercise_minutes": {"unit": "min", "conversions": {"h": 60,
                                                        "s": 1 / 60}},
    "steps": {"unit": "count", "conversions": {}},
    "distance": {"unit": "m", "conversions": {"km": 1000, "mi": 1609.344}},
}

_REQUIRED = ("metric", "value", "unit", "measured_at", "source_platform",
             "source_record_id")


def _normalize_row(row: dict, idx: int) -> dict:
    problems = []
    for f in _REQUIRED:
        if row.get(f) in (None, ""):
            problems.append(f"行 {idx} 缺少 {f}")
    if problems:
        raise ValueError("；".join(problems))
    metric = str(row["metric"]).strip()
    if metric not in METRICS:
        raise ValueError(f"行 {idx}：指标 {metric!r} 不在白名单"
                         f"（{sorted(METRICS)}）")
    spec = METRICS[metric]
    try:
        value = float(row["value"])
    except (TypeError, ValueError):
        raise ValueError(f"行 {idx}：value 不是数值") from None
    unit = str(row["unit"]).strip()
    if unit != spec["unit"]:
        factor = spec["conversions"].get(unit)
        if not factor:
            raise ValueError(f"行 {idx}：单位 {unit!r} 不支持"
                             f"（canonical {spec['unit']}）")
        value = round(value * factor, 4)
        unit = spec["unit"]
    measured_at = str(row["measured_at"]).strip()
    try:
        datetime.fromisoformat(measured_at)
    except ValueError:
        raise ValueError(f"行 {idx}：measured_at 不是 ISO 时间") from None
    return {
        "metric": metric, "value": value, "unit": unit,
        "measured_at": measured_at,
        "source_platform": str(row["source_platform"]).strip()[:40],
        "source_device": (str(row.get("source_device")).strip()[:60]
                          if row.get("source_device") else None),
        "source_record_id": str(row["source_record_id"]).strip()[:120],
        "measurement_method": (str(row.get("measurement_method")).strip()[:40]
                               if row.get("measurement_method") else None),
    }


def parse_import(content, fmt: str) -> list[dict]:
    """CSV/JSON → 规范化行列表（不写库）。"""
    if fmt == "json":
        try:
            rows = json.loads(content) if isinstance(content, str) else content
        except (ValueError, TypeError):
            raise ValueError("JSON 解析失败") from None
        if not isinstance(rows, list):
            raise ValueError("JSON 必须是行数组")
    elif fmt == "csv":
        try:
            reader = csv.DictReader(io.StringIO(str(content)))
            rows = list(reader)
        except csv.Error as e:
            raise ValueError(f"CSV 解析失败：{e}") from None
    else:
        raise ValueError("format 必须是 csv 或 json")
    if not rows:
        raise ValueError("没有可导入的行")
    if len(rows) > 5000:
        raise ValueError("单次导入最多 5000 行")
    return [_normalize_row(r, i + 1) for i, r in enumerate(rows)]


def preview_device_import(db, user_id: str, content, fmt: str) -> dict:
    rows = parse_import(content, fmt)
    existing = {
        (r["source_platform"], r["source_record_id"])
        for r in db.list_imported_device_records(user_id, limit=100000)}
    new_rows, duplicates = [], []
    for r in rows:
        key = (r["source_platform"], r["source_record_id"])
        if key in existing:
            duplicates.append(r)
        else:
            new_rows.append(r)
            existing.add(key)
    return {
        "kind": "device_import_preview_v1",
        "rows_total": len(rows),
        "rows_to_insert": len(new_rows),
        "duplicates": len(duplicates),
        "metrics": sorted({r["metric"] for r in rows}),
        "sources": sorted({r["source_platform"] for r in rows}),
        "note": "设备数据只读入库（独立表），不与手动训练/身体记录相加统计；"
                "不同设备估算值不可默认可比",
        "requires_confirmation": True,
        "_rows": new_rows,
    }


def apply_device_import(db, user_id: str, content, fmt: str) -> dict:
    preview = preview_device_import(db, user_id, content, fmt)
    inserted = 0
    for r in preview["_rows"]:
        if db.upsert_imported_device_record(user_id, r):
            inserted += 1
    return {"kind": "device_import_applied_v1",
            "inserted": inserted,
            "duplicates": preview["duplicates"],
            "note": "导入完成；可在报告与导出中查看，随时可按来源删除"}
