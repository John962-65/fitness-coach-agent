"""身体测量服务：录入 / 编辑（修订）/ 删除 / 查询 / 导出 / 迁移。"""
from __future__ import annotations

import json
import re
from datetime import datetime

# 指标独立校验表：(字段, 下限, 上限, 名称)
METRIC_RANGES = {
    "weight_kg": (25, 300, "体重"),
    "waist_cm": (40, 200, "腰围"),
    "hip_cm": (50, 200, "臀围"),
    "chest_cm": (60, 200, "胸围"),
    "body_fat_percent": (2, 70, "体脂率"),
    "muscle_mass_kg": (10, 150, "肌肉量"),
}

METHODS = ("home_scale", "gym_scale", "tape", "caliper", "dexa", "bia",
           "other", "import")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validate_measurement(data: dict) -> dict:
    """清洗一条测量（指标全部可选但各自限幅；成分类必须带来源）。"""
    if not isinstance(data, dict):
        raise ValueError("数据必须是对象")
    out: dict = {}
    metrics = 0
    for field, (lo, hi, label) in METRIC_RANGES.items():
        v = data.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            out[field] = None
            continue
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                raise ValueError(f"{label}「{data[field]}」不是有效数字") from None
        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not lo <= v <= hi:
            raise ValueError(f"{label} 必须在 {lo}-{hi} 之间（收到 {v}）")
        out[field] = float(v)
        metrics += 1
    if metrics == 0:
        raise ValueError("至少填写一个测量指标（体重/腰围/臀围/胸围/体脂率/肌肉量）")
    # 成分数据来源纪律：体脂率/肌肉量属于设备估算，必须留方法或来源说明
    if (out.get("body_fat_percent") is not None
            or out.get("muscle_mass_kg") is not None):
        if not str(data.get("measurement_method") or "").strip():
            raise ValueError("体脂率/肌肉量为设备估算值，必须选择测量方法"
                             "（不同设备结果不默认可比）")
    method = str(data.get("measurement_method") or "").strip()
    if method and method not in METHODS:
        raise ValueError(f"measurement_method 须为 {METHODS} 之一")
    out["measurement_method"] = method or None
    out["device_source"] = str(data.get("device_source") or "").strip()[:60] or None
    out["notes"] = str(data.get("notes") or "").strip()[:300] or None

    local_date = str(data.get("local_date") or "").strip()
    if local_date and not _DATE.match(local_date):
        raise ValueError("local_date 需为 YYYY-MM-DD")
    measured_at = str(data.get("measured_at") or "").strip()
    if measured_at:
        try:
            datetime.fromisoformat(measured_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("measured_at 需为 ISO 时间") from None
    else:
        measured_at = _now()
    if not local_date:
        local_date = measured_at[:10]
    out["measured_at"] = measured_at
    out["local_date"] = local_date
    out["timezone"] = str(data.get("timezone") or "")[:64] or None
    return out


def record_measurement(db, user_id: str, data: dict,
                       submission_id: str | None = None,
                       migrated_from: str | None = None) -> dict:
    """新增测量（幂等提交：同 submission_id 返回既有结果）。"""
    if submission_id:
        existing = db.get_record_submission(user_id, submission_id)
        if existing and existing["kind"] == "body":
            return {"measurement_id": existing["record_id"], "existing": True}
    clean = validate_measurement(data)
    clean["migrated_from"] = migrated_from
    mid = db.create_body_measurement(user_id, clean)
    if submission_id:
        db.record_submission(user_id, submission_id, "body", mid)
    _fire_body_recorded(db, user_id)
    return {"measurement_id": mid, "existing": False}


def record_from_checkin(db, user_id: str, data: dict) -> int:
    """旧 checkins body 打卡口径 → 测量记录（record_checkin 转发用）。
    返回测量 id（agent 与 API 的 checkin 返回值继续可用）。"""
    result = record_measurement(db, user_id, {
        "weight_kg": data.get("weight_kg"),
        "waist_cm": data.get("waist_cm"),
        "notes": data.get("note") or data.get("notes") or data.get("raw"),
        "measured_at": data.get("measured_at"),
        "local_date": data.get("local_date"),
        "measurement_method": data.get("measurement_method") or "other",
        "device_source": data.get("device_source"),
    })
    return result["measurement_id"]


def update_measurement(db, user_id: str, mid: int, expected_revision: int,
                       data: dict, reason: str, evidence: str) -> dict:
    """整条编辑 = 修订（快照保留）。"""
    clean = validate_measurement({**data, **{
        k: data.get(k) for k in ("measured_at", "local_date", "timezone")
        if data.get(k)}})
    fresh = db.revise_body_measurement(user_id, mid, expected_revision, clean,
                                       reason, evidence)
    _fire_body_recorded(db, user_id)
    return fresh


def delete_measurement(db, user_id: str, mid: int) -> None:
    if not db.delete_body_measurement(user_id, mid):
        raise ValueError("测量记录不存在")
    _fire_body_recorded(db, user_id)


def _fire_body_recorded(db, user_id: str) -> None:
    """BodyMeasurementRecorded → 订阅的确定性分析（营养×身体等）。

    仅当今天有饮食记录时触发营养日回顾（避免无分析对象的任务噪音）；
    dedup 锚带 body_version——体重修订后当天分析会重跑。
    整体容错：记录主流程已成功，专家链路只留任务日志。
    """
    from ..experts import task_dispatcher
    try:
        from ..nutrition.meal_service import day_version
        today = datetime.now().date().isoformat()
        refs = {"local_date": today, "body_version": body_version(db, user_id)}
        if db.meals_on(user_id, today):
            task_dispatcher.on_event(db, user_id, "BodyMeasurementRecorded", refs)
    except Exception:  # noqa: BLE001
        pass


def body_version(db, user_id: str) -> str:
    """身体数据版本（漂移检测与幂等锚）。"""
    row = db.conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(MAX(updated_at),'') AS last,"
        " COALESCE(SUM((SELECT COUNT(*) FROM body_measurement_revisions r"
        " WHERE r.measurement_id=body_measurements.id)),0) AS revs"
        " FROM body_measurements WHERE user_id=?", (user_id,)).fetchone()
    return f"{row['n']}:{row['last']}:{row['revs']}"


def migrate_legacy_body_checkins(db) -> int:
    """一次性迁移：type='body' 的旧打卡 → body_measurements。

    幂等：已迁移的打卡数据带 _migrated 标记，跳过；原行保留（历史不丢），
    History 页照常显示，但分析只读测量表——单一权威存储，无两套矛盾历史。
    """
    rows = db.conn.execute(
        "SELECT id, user_id, data, created_at FROM checkins"
        " WHERE type='body' ORDER BY id").fetchall()
    migrated = 0
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict) or data.get("_migrated"):
            continue
        note = str(data.get("note") or data.get("raw") or "")[:300] or None
        try:
            result = record_measurement(
                db, row["user_id"], {
                    "weight_kg": data.get("weight_kg"),
                    "waist_cm": data.get("waist_cm"),
                    "notes": note,
                    "measured_at": row["created_at"],
                    "local_date": (data.get("local_date")
                                   or str(row["created_at"])[:10]),
                    "measurement_method": "import",
                    "device_source": "旧身体打卡迁移",
                },
                migrated_from=f"checkin:{row['id']}")
        except ValueError:
            continue  # 无法解析的历史行保留原状（不丢数据也不硬造测量）
        data["_migrated"] = {"measurement_id": result["measurement_id"]}
        db.conn.execute("UPDATE checkins SET data=? WHERE id=?",
                        (json.dumps(data, ensure_ascii=False), row["id"]))
        db.conn.commit()
        migrated += 1
    return migrated
