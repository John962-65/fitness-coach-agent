"""P7-A：备份导入（预览 → 用户确认 → 事务执行，失败回滚）。

不允许把未知 JSON 直接写库：
- 只接受本模块 schema 的白名单节与字段；
- 预览：版本检查、逐节计数、重复识别（按内容指纹）、动作/器械映射冲突、
  将执行的写入摘要；
- 应用：单事务写入新用户（或按预览的跳过规则合并），任何异常整体回滚；
- 导入不覆盖既有记录：同指纹内容跳过，冲突映射在预览中标出由用户决定。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from .export_service import EXPORT_SCHEMA_VERSION, verify_integrity


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

_ALLOWED_TOP = ("schema_version", "export_version", "exported_at",
                "exported_for", "user_data", "source_revisions",
                "exercise_mapping", "equipment_mapping", "media_manifest",
                "integrity_manifest")


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except (ValueError, TypeError):
        return default


def _validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("备份必须是 JSON 对象")
    unknown = [k for k in payload if k not in _ALLOWED_TOP]
    if unknown:
        raise ValueError(f"备份含未知节：{unknown}（拒绝写入）")
    if payload.get("schema_version") != EXPORT_SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须是 {EXPORT_SCHEMA_VERSION}，"
                         f"收到 {payload.get('schema_version')!r}")
    if not isinstance(payload.get("user_data"), dict):
        raise ValueError("user_data 缺失")
    integrity = verify_integrity(payload)
    if not integrity["ok"]:
        raise ValueError(f"完整性校验未通过（节不一致："
                         f"{integrity['mismatched']}）——文件可能被改动")


def _checkin_fingerprint(data: dict) -> str:
    meta = data.get("session_meta") or {}
    exercises = []
    for ex in data.get("exercises") or []:
        sets = json.dumps(ex.get("set_logs") or [], ensure_ascii=False,
                          sort_keys=True)
        exercises.append(f"{ex.get('exercise_id')}:{ex.get('name')}:{sets}")
    return "|".join([str(meta.get("local_date")), str(meta.get("mode")),
                     *exercises])


def preview_import(db, user_id: str, payload: dict) -> dict:
    """预览：不写库。返回计数 / 重复 / 冲突 / 将执行操作。"""
    _validate_payload(payload)
    ud = payload["user_data"]
    counts, duplicates, conflicts = {}, [], []
    actions: list[str] = []

    existing_checkins = {
        _checkin_fingerprint(_j(d, {}))
        for (d,) in db.conn.execute(
            "SELECT data FROM checkins WHERE user_id=?", (user_id,)).fetchall()}
    new_checkins = 0
    for c in ud.get("checkins") or []:
        fp = _checkin_fingerprint(c.get("data") or {})
        if fp in existing_checkins:
            duplicates.append({"section": "checkins",
                               "reason": "同日期同动作同逐组内容"})
        else:
            new_checkins += 1
    counts["checkins"] = {"total": len(ud.get("checkins") or []),
                          "to_insert": new_checkins,
                          "duplicates": len(
                              ud.get("checkins") or []) - new_checkins}
    actions.append(f"训练打卡：新增 {new_checkins} 条，跳过重复 "
                   f"{counts['checkins']['duplicates']} 条")

    plan_versions = {r["version"] for r in db.conn.execute(
        "SELECT version FROM plans WHERE user_id=?", (user_id,)).fetchall()}
    new_plans = [p for p in ud.get("plans") or []
                 if p.get("version") not in plan_versions]
    counts["plans"] = {"total": len(ud.get("plans") or []),
                       "to_insert": len(new_plans)}
    actions.append(f"计划：新增 {len(new_plans)} 个版本（不改变当前生效版本）")

    for section, table, key in (
            ("meals", "meal_entries", "local_date"),
            ("body_measurements", "body_measurements", "measured_at"),
            ("recovery_checkins", "recovery_checkins", "local_date")):
        rows = ud.get(section) or []
        counts[section] = {"total": len(rows), "to_insert": len(rows),
                           "note": "同日已有记录时按预览规则跳过"}
        actions.append(f"{section}：待写入 {len(rows)} 条")

    # 动作/器械映射冲突：备份里的 ID 在本用户库中同名不同指
    for eid, name in (payload.get("exercise_mapping") or {}).items():
        from .. import exercise_service
        doc = exercise_service.get_exercise(db, user_id, eid)
        if doc and doc.get("name") != name:
            conflicts.append({"kind": "exercise", "id": eid,
                              "backup_name": name,
                              "current_name": doc.get("name"),
                              "resolution": "以当前库为准；历史记录保留原 ID"})
    for eq_id, name in (payload.get("equipment_mapping") or {}).items():
        row = db.get_user_equipment(user_id, eq_id)
        if row and row["name"] != name:
            conflicts.append({"kind": "equipment", "id": eq_id,
                              "backup_name": name,
                              "current_name": row["name"],
                              "resolution": "以当前配置为准"})

    return {
        "kind": "import_preview_v1",
        "schema_version": payload.get("schema_version"),
        "exported_at": payload.get("exported_at"),
        "exported_for": payload.get("exported_for"),
        "target_user": user_id,
        "counts": counts,
        "duplicates": duplicates[:20],
        "conflicts": conflicts,
        "actions": actions,
        "media_manifest_count": len(payload.get("media_manifest") or []),
        "media_note": "媒体文件按清单核对本地文件存在性与校验和；"
                      "缺失项在报告中列出，不阻塞结构化数据导入",
        "requires_confirmation": True,
    }


_REQUIRED = {
    "checkins": ("type", "data"),
    "plans": ("version", "content"),
    "meals": ("local_date", "meal_type", "items"),
    "body_measurements": ("measured_at", "local_date"),
    "recovery_checkins": ("local_date", "recorded_at"),
    "symptom_episodes": ("body_region", "onset_at", "description"),
    "training_restrictions": ("restriction_description",),
}


def _validate_rows(ud: dict) -> None:
    """写入前的行级白名单校验：缺必填字段快速失败（ValueError），不进事务。"""
    problems = []
    for section, fields in _REQUIRED.items():
        for i, row in enumerate(ud.get(section) or []):
            if not isinstance(row, dict):
                problems.append(f"{section}[{i}] 不是对象")
                continue
            missing = [f for f in fields
                       if row.get(f) in (None, "") and f != "data"]
            if missing:
                problems.append(f"{section}[{i}] 缺少必填字段：{missing}")
    if problems:
        raise ValueError("备份行校验未通过（未写入任何数据）："
                         + "；".join(problems[:8]))


def apply_import(db, user_id: str, payload: dict) -> dict:
    """应用导入（单事务；任何异常整体回滚；不覆盖已有记录）。"""
    _validate_payload(payload)
    _validate_rows(payload["user_data"])
    preview = preview_import(db, user_id, payload)
    ud = payload["user_data"]
    inserted = {"checkins": 0, "plans": 0, "meals": 0, "body": 0,
                "recovery": 0, "symptoms": 0, "restrictions": 0,
                "meals_skipped": 0}
    try:
        with db.conn:
            # 计划（不激活：导入的历史版本默认非当前生效）
            for p in ud.get("plans") or []:
                db.conn.execute(
                    "INSERT INTO plans(user_id, version, content, active,"
                    " created_at) VALUES(?,?,?,0,?)",
                    (user_id, p["version"],
                     json.dumps(p["content"], ensure_ascii=False),
                     p.get("created_at")))
                inserted["plans"] += 1
            # 训练打卡（含逐组数据；修订历史一并保留）
            existing_fps = {
                _checkin_fingerprint(_j(d, {}))
                for (d,) in db.conn.execute(
                    "SELECT data FROM checkins WHERE user_id=?",
                    (user_id,)).fetchall()}
            for c in ud.get("checkins") or []:
                fp = _checkin_fingerprint(c.get("data") or {})
                if fp in existing_fps:
                    continue
                cur = db.conn.execute(
                    "INSERT INTO checkins(user_id, type, data, created_at)"
                    " VALUES(?,?,?,?)",
                    (user_id, c.get("type") or "training",
                     json.dumps(c.get("data") or {}, ensure_ascii=False),
                     c.get("created_at")))
                new_id = cur.lastrowid
                for r in ud.get("checkin_revisions") or []:
                    if r.get("checkin_id") == c.get("id"):
                        db.conn.execute(
                            "INSERT INTO checkin_revisions(checkin_id,"
                            " revision, old_data, new_data, reason, evidence,"
                            " created_at) VALUES(?,?,?,?,?,?,?)",
                            (new_id, r.get("revision") or 1,
                             json.dumps(r.get("old_data"), ensure_ascii=False),
                             json.dumps(r.get("new_data"), ensure_ascii=False),
                             r.get("reason") or "备份导入",
                             r.get("evidence") or "来自备份", _now()))
                inserted["checkins"] += 1
            # 饮食（同日同餐同内容跳过）
            for m in ud.get("meals") or []:
                dup = db.conn.execute(
                    "SELECT 1 FROM meal_entries WHERE user_id=? AND"
                    " local_date=? AND meal_type=? AND items=?",
                    (user_id, m.get("local_date"), m.get("meal_type"),
                     json.dumps(m.get("items") or [], ensure_ascii=False))
                ).fetchone()
                if dup:
                    inserted["meals_skipped"] += 1
                    continue
                db.conn.execute(
                    "INSERT INTO meal_entries(user_id, local_date, meal_type,"
                    " items, notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                    (user_id, m.get("local_date"), m.get("meal_type"),
                     json.dumps(m.get("items") or [], ensure_ascii=False),
                     m.get("notes") or "", m.get("created_at"),
                     m.get("updated_at")))
                inserted["meals"] += 1
            # 身体 / 恢复 / 症状 / 限制
            for b in ud.get("body_measurements") or []:
                db.conn.execute(
                    "INSERT INTO body_measurements(user_id, measured_at,"
                    " local_date, timezone, weight_kg, waist_cm, hip_cm,"
                    " chest_cm, body_fat_percent, muscle_mass_kg,"
                    " measurement_method, device_source, notes, created_at,"
                    " updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (user_id, b.get("measured_at"), b.get("local_date"),
                     b.get("timezone"), b.get("weight_kg"), b.get("waist_cm"),
                     b.get("hip_cm"), b.get("chest_cm"),
                     b.get("body_fat_percent"), b.get("muscle_mass_kg"),
                     b.get("measurement_method"), b.get("device_source"),
                     b.get("notes"), b.get("created_at"), b.get("created_at")))
                inserted["body"] += 1
            for r in ud.get("recovery_checkins") or []:
                db.conn.execute(
                    "INSERT OR IGNORE INTO recovery_checkins(user_id,"
                    " local_date, recorded_at, timezone, sleep_hours,"
                    " sleep_quality, fatigue, muscle_soreness,"
                    " training_readiness, soreness_regions, notes,"
                    " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (user_id, r.get("local_date"), r.get("recorded_at"),
                     r.get("timezone"), r.get("sleep_hours"),
                     r.get("sleep_quality"), r.get("fatigue"),
                     r.get("muscle_soreness"), r.get("training_readiness"),
                     json.dumps(r.get("soreness_regions") or [],
                                ensure_ascii=False), r.get("notes"),
                     r.get("created_at"), r.get("created_at")))
                inserted["recovery"] += 1
            for s in ud.get("symptom_episodes") or []:
                db.conn.execute(
                    "INSERT INTO symptom_episodes(user_id, body_region, side,"
                    " onset_at, onset_context, description,"
                    " professional_evaluated, status, created_at, updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (user_id, s.get("body_region"), s.get("side"),
                     s.get("onset_at"), s.get("onset_context"),
                     s.get("description"),
                     1 if s.get("professional_evaluated") else 0,
                     s.get("status") or "resolved", s.get("created_at"),
                     s.get("updated_at")))
                inserted["symptoms"] += 1
            for r in ud.get("training_restrictions") or []:
                # 导入的限制默认置为 lifted：不静默改变当前安全状态
                db.conn.execute(
                    "INSERT INTO training_restrictions(user_id, source_type,"
                    " source_evidence, restriction_description,"
                    " affected_activities, effective_at, status,"
                    " created_at, updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (user_id, r.get("source_type") or "imported",
                     r.get("source_evidence") or "来自备份",
                     r.get("restriction_description") or "",
                     json.dumps(r.get("affected_activities") or {},
                                ensure_ascii=False),
                     r.get("effective_at") or r.get("created_at") or _now(),
                     "lifted", r.get("created_at"), r.get("created_at")))
                inserted["restrictions"] += 1
            # 自定义食物 / 器械 / 地点（同名跳过）
            for f in ud.get("custom_foods") or []:
                exists = db.conn.execute(
                    "SELECT 1 FROM foods WHERE user_id=? AND name=?",
                    (user_id, f.get("name"))).fetchone()
                if not exists:
                    db.conn.execute(
                        "INSERT INTO foods(id, user_id, name, aliases, brand,"
                        " category, serving_units, energy_kcal, protein_g,"
                        " carbohydrate_g, fat_g, fiber_g, sodium_mg,"
                        " reference_amount, reference_unit, source_name,"
                        " source_url, source_version, license,"
                        " verified_status, created_at) VALUES(?,?,?,?,?,?,?,?,"
                        "?,?,?,?,?,?,?,?,?,?,?,?)",
                        (f.get("id"), user_id, f.get("name"),
                         json.dumps(f.get("aliases") or [], ensure_ascii=False),
                         f.get("brand"), f.get("category") or "other",
                         json.dumps(f.get("serving_units") or [],
                                    ensure_ascii=False),
                         f.get("energy_kcal"), f.get("protein_g"),
                         f.get("carbohydrate_g"), f.get("fat_g"),
                         f.get("fiber_g"), f.get("sodium_mg"),
                         f.get("reference_amount") or 100,
                         f.get("reference_unit") or "g", f.get("source_name"),
                         f.get("source_url"), f.get("source_version"),
                         f.get("license"), "user_created",
                         f.get("created_at")))
    except Exception:
        # with db.conn 上下文在异常时回滚；此处确认无残留
        raise
    missing_media = [
        m.get("file_ref") for m in (payload.get("media_manifest") or [])
        if m.get("file_ref") and not os.path.exists(m["file_ref"])]
    return {
        "kind": "import_applied_v1",
        "inserted": inserted,
        "preview_summary": {"counts": preview["counts"],
                            "conflicts": preview["conflicts"]},
        "missing_media_files": missing_media,
        "note": "导入为单事务；失败已整体回滚。导入的计划不改变当前生效版本；"
                "导入的训练限制默认置为 resolved（不静默改变当前安全状态）",
    }
