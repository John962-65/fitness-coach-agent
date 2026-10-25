"""恢复打卡服务：校验 / 当天一条（修订）/ 删除 / 版本锚。"""
from __future__ import annotations

import re
from datetime import datetime

# 主观量表：方向全局统一（界面同文案展示，禁止相反计分）
SCALE_LABELS = {
    "sleep_quality": ("睡眠质量", {1: "非常差", 2: "较差", 3: "一般",
                                   4: "较好", 5: "非常好"}),
    "fatigue": ("疲劳程度", {1: "几乎不疲劳", 2: "略感疲劳", 3: "中等疲劳",
                             4: "比较疲劳", 5: "非常疲劳"}),
    "muscle_soreness": ("肌肉酸痛", {1: "几乎不酸", 2: "轻微酸痛", 3: "明显酸痛",
                                     4: "比较严重", 5: "非常严重"}),
    "training_readiness": ("训练意愿", {1: "完全不想练", 2: "不太想练", 3: "一般",
                                        4: "比较想练", 5: "状态很好想练"}),
}
SCALES = tuple(SCALE_LABELS)
SORENESS_REGIONS = ("肩", "肘", "腕", "腰背", "髋", "膝", "踝", "颈",
                    "胸", "腹股沟", "其他")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validate_checkin(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("数据必须是对象")
    out: dict = {}
    filled = 0
    for key in ("sleep_hours",):
        v = data.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            out[key] = None
            continue
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                raise ValueError("睡眠时长需为数字（小时）") from None
        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not 0 <= v <= 24:
            raise ValueError("sleep_hours 必须在 0-24 之间")
        out[key] = round(float(v), 2)
        filled += 1
    for key in SCALES:
        v = data.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            out[key] = None
            continue
        if isinstance(v, str):
            try:
                v = int(v)
            except ValueError:
                raise ValueError(f"{SCALE_LABELS[key][0]}需为 1-5 整数") from None
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 5:
            raise ValueError(f"{SCALE_LABELS[key][0]}必须是 1-5 整数"
                             "（1=" + SCALE_LABELS[key][1][1] + "，5="
                             + SCALE_LABELS[key][1][5] + "）")
        out[key] = int(v)
        filled += 1
    if filled == 0 and not (data.get("soreness_regions")
                            or str(data.get("notes") or "").strip()):
        raise ValueError("至少填写一项恢复指标（全部可选但至少要有一项内容）")

    regions = data.get("soreness_regions") or []
    if not isinstance(regions, list):
        raise ValueError("soreness_regions 必须是列表")
    clean_regions = []
    for r in regions[:10]:
        r = str(r).strip()[:12]
        if r and r not in clean_regions:
            clean_regions.append(r)
    out["soreness_regions"] = clean_regions
    out["notes"] = str(data.get("notes") or "").strip()[:500] or None

    local_date = str(data.get("local_date") or "").strip()
    if not _DATE.match(local_date):
        raise ValueError("local_date 需为 YYYY-MM-DD")
    out["local_date"] = local_date
    out["recorded_at"] = str(data.get("recorded_at") or "") or _now()
    out["timezone"] = str(data.get("timezone") or "")[:64] or None
    # 修订说明（编辑既有记录时必填，与训练打卡纪律一致）
    out["reason"] = str(data.get("reason") or "").strip()[:200] or None
    out["evidence"] = str(data.get("evidence") or "").strip()[:300] or None
    return out


def record_checkin(db, user_id: str, data: dict,
                   submission_id: str | None = None) -> dict:
    """记录/更新当天恢复（幂等提交；更新走修订）。"""
    if submission_id:
        existing = db.get_record_submission(user_id, submission_id)
        if existing and existing["kind"] == "recovery":
            row = db.get_recovery_checkin(user_id, existing["record_id"])
            if row:
                return {"recovery_id": row["id"], "revision": row["revision"],
                        "created": False, "existing": True}
    clean = validate_checkin(data)
    # 当天已存在 → 是更新：修订必须说明原因（除非就是当天首录的补全？不——
    # 统一纪律：已有记录再提交一律要求 reason+evidence）
    prior = db.get_recovery_by_date(user_id, clean["local_date"])
    if prior:
        if not clean["reason"] or not clean["evidence"]:
            raise ValueError("当天已有恢复记录，更新必须说明修改原因并附依据"
                             "（reason/evidence）")
    rid, created = db.upsert_recovery_checkin(user_id, clean)
    if submission_id:
        db.record_submission(user_id, submission_id, "recovery", rid)
    _fire_recovery_recorded(db, user_id, clean["local_date"])
    fresh = db.get_recovery_checkin(user_id, rid)
    return {"recovery_id": rid, "revision": fresh["revision"],
            "created": created, "recovery": fresh}


def delete_checkin(db, user_id: str, rid: int) -> None:
    row = db.get_recovery_checkin(user_id, rid)
    if not row:
        raise ValueError("恢复记录不存在")
    if not db.delete_recovery_checkin(user_id, rid):
        raise ValueError("恢复记录不存在")
    _fire_recovery_recorded(db, user_id, row["local_date"])


def version(db, user_id: str, local_date: str) -> str:
    """某日恢复数据版本（漂移检测与幂等锚）。"""
    row = db.get_recovery_by_date(user_id, local_date)
    if not row:
        return "0"
    return f"{row['id']}:{row['revision']}:{row['updated_at']}"


def range_version(db, user_id: str, days: int = 30) -> str:
    """窗口内恢复数据整体版本（训练×恢复分析锚）。"""
    rows = db.list_recovery_checkins(user_id, days)
    return f"{len(rows)}:{max((r['updated_at'] for r in rows), default='')}"


def _fire_recovery_recorded(db, user_id: str, local_date: str) -> None:
    from ..experts import task_dispatcher
    try:
        task_dispatcher.on_event(db, user_id, "RecoveryRecorded", {
            "local_date": local_date,
            "recovery_version": version(db, user_id, local_date),
            "range_version": range_version(db, user_id),
        })
    except Exception:  # noqa: BLE001 记录主流程优先
        pass
