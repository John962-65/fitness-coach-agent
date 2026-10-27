"""P7-A：用户数据导出（JSON 完整备份 + CSV 可读格式）。

原则：
- 导出内容只来自本用户的数据，逐节带来源与版本；
- JSON 备份含 schema_version / export_version / exported_at /
  source_revisions / exercise_mapping / equipment_mapping /
  media_manifest / integrity_manifest（各节 sha256，可校验）；
- 媒体不导出临时 URL：清单列文件引用（导入侧按文件存在性核对）；
- 敏感健康数据导出必须显式 confirm（API 层强制）。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime

from ..equipment import equipment_version

EXPORT_SCHEMA_VERSION = "fcs-export-v1"
EXPORT_VERSION = 1


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _rows(db, sql: str, params: tuple) -> list[dict]:
    return [dict(r) for r in db.conn.execute(sql, params).fetchall()]


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except (ValueError, TypeError):
        return default


def export_user_data(db, user_id: str) -> dict:
    """完整结构化备份（JSON 可序列化 dict）。"""
    profile_row = db.conn.execute(
        "SELECT profile FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not profile_row:
        raise ValueError("用户不存在")
    plans = _rows(db, "SELECT * FROM plans WHERE user_id=? ORDER BY id", (user_id,))
    templates = _rows(db, "SELECT * FROM training_templates WHERE user_id=?", (user_id,))
    checkins = _rows(db, "SELECT * FROM checkins WHERE user_id=? ORDER BY id", (user_id,))
    checkin_revisions = _rows(
        db, "SELECT r.* FROM checkin_revisions r JOIN checkins c"
            " ON c.id=r.checkin_id WHERE c.user_id=?"
            " ORDER BY r.checkin_id, r.revision", (user_id,))
    meals = _rows(db, "SELECT * FROM meal_entries WHERE user_id=? ORDER BY id", (user_id,))
    custom_foods = _rows(db, "SELECT * FROM foods WHERE user_id=? ORDER BY id", (user_id,))
    recipes = _rows(db, "SELECT * FROM nutrition_recipes WHERE user_id=? ORDER BY id",
                    (user_id,))
    body = _rows(db, "SELECT * FROM body_measurements WHERE user_id=? ORDER BY id",
                 (user_id,))
    recovery = _rows(db, "SELECT * FROM recovery_checkins WHERE user_id=?"
                         " ORDER BY id", (user_id,))
    symptoms = _rows(db, "SELECT * FROM symptom_episodes WHERE user_id=?"
                         " ORDER BY id", (user_id,))
    restrictions = _rows(db, "SELECT * FROM training_restrictions"
                             " WHERE user_id=? ORDER BY id", (user_id,))
    trials = _rows(db, "SELECT * FROM personal_trials WHERE user_id=?"
                       " ORDER BY id", (user_id,))
    equipment = _rows(db, "SELECT * FROM user_equipment WHERE user_id=?", (user_id,))
    locations = _rows(db, "SELECT * FROM training_locations WHERE user_id=?", (user_id,))
    insights = _rows(db, "SELECT id, insight_type, title, summary, status,"
                         " confidence, generated_at FROM expert_insights"
                         " WHERE user_id=? ORDER BY id", (user_id,))
    motion = _rows(db, "SELECT id, exercise_id, status, video_path,"
                       " created_at FROM motion_analyses WHERE user_id=?"
                       " ORDER BY id", (user_id,))
    media = _rows(db, "SELECT * FROM media_assets WHERE user_id=? ORDER BY id",
                  (user_id,))
    body_revisions = _rows(
        db, "SELECT * FROM body_measurement_revisions"
            " WHERE user_id=? ORDER BY measurement_id, revision", (user_id,))
    recovery_revisions = _rows(
        db, "SELECT * FROM recovery_revisions"
            " WHERE user_id=? ORDER BY recovery_id, revision", (user_id,))
    symptom_observations = _rows(
        db, "SELECT * FROM symptom_observations WHERE user_id=? ORDER BY id", (user_id,))
    restriction_revisions = _rows(
        db, "SELECT * FROM training_restriction_revisions"
            " WHERE user_id=? ORDER BY restriction_id, revision", (user_id,))
    approach = _rows(db, "SELECT * FROM training_approach WHERE user_id=?",
                     (user_id,))
    approach_revisions = _rows(
        db, "SELECT * FROM approach_revisions WHERE user_id=? ORDER BY revision",
        (user_id,))
    nutrition_targets = _rows(db, "SELECT * FROM nutrition_targets"
                                 " WHERE user_id=?", (user_id,))
    nutrition_days = _rows(db, "SELECT * FROM nutrition_days WHERE user_id=?",
                           (user_id,))
    user_exercise = _rows(db, "SELECT * FROM user_exercise WHERE user_id=?",
                          (user_id,))
    coach_notes = _rows(db, "SELECT * FROM coach_notes WHERE user_id=?"
                            " ORDER BY id", (user_id,))
    discussions = _rows(db, "SELECT * FROM knowledge_discussions"
                             " WHERE user_id=? ORDER BY id", (user_id,))
    care_plans = _rows(db, "SELECT * FROM care_plans WHERE user_id=?"
                           " ORDER BY id", (user_id,))
    care_activities = _rows(db, "SELECT * FROM care_activities"
                                " WHERE user_id=? ORDER BY id", (user_id,))
    care_logs = _rows(db, "SELECT * FROM care_activity_logs"
                          " WHERE user_id=? ORDER BY id", (user_id,))
    device_records = _rows(db, "SELECT * FROM imported_device_records"
                               " WHERE user_id=? ORDER BY id", (user_id,))
    expert_settings = _rows(db, "SELECT * FROM expert_settings"
                                " WHERE user_id=?", (user_id,))
    custom_exercises = _rows(db, "SELECT * FROM custom_exercises"
                                 " WHERE user_id=? ORDER BY id", (user_id,))
    exercise_proposals = _rows(db, "SELECT * FROM exercise_proposals"
                                   " WHERE user_id=? ORDER BY id", (user_id,))
    knowledge_sources = _rows(db, "SELECT * FROM knowledge_sources"
                                  " WHERE user_id=? ORDER BY id", (user_id,))
    knowledge_chunks = _rows(
        db, "SELECT c.* FROM knowledge_chunks c JOIN knowledge_sources s"
            " ON s.id=c.source_id WHERE s.user_id=? ORDER BY c.id", (user_id,))
    knowledge_claims = _rows(db, "SELECT * FROM knowledge_claims"
                                 " WHERE user_id=? ORDER BY id", (user_id,))
    messages = _rows(db, "SELECT * FROM messages WHERE user_id=? ORDER BY id",
                     (user_id,))
    consultations = _rows(db, "SELECT * FROM agent_consultations"
                              " WHERE user_id=? ORDER BY id", (user_id,))
    proposals = _rows(db, "SELECT * FROM change_proposals WHERE user_id=?"
                          " ORDER BY created_at", (user_id,))
    media_links = _rows(db, "SELECT * FROM exercise_media_links"
                             " WHERE user_id=? ORDER BY id", (user_id,))
    motion_full = _rows(db, "SELECT * FROM motion_analyses WHERE user_id=?"
                             " ORDER BY id", (user_id,))
    motion_profiles = _rows(db, "SELECT * FROM motion_tech_profiles"
                                " WHERE user_id=? ORDER BY analysis_id",
                            (user_id,))

    user_data = {
        "profile": json.loads(profile_row["profile"]),
        "plans": [{**p, "content": _j(p["content"], {})} for p in plans],
        "training_templates": [{**t, "doc": _j(t["doc"], {})}
                               for t in templates],
        "checkins": [{**c, "data": _j(c["data"], {})} for c in checkins],
        "checkin_revisions": [
            {**r, "old_data": _j(r["old_data"], None),
             "new_data": _j(r["new_data"], None)} for r in checkin_revisions],
        "meals": [{**m, "items": _j(m["items"], [])} for m in meals],
        "custom_foods": [{**f, "aliases": _j(f["aliases"], []),
                          "serving_units": _j(f["serving_units"], [])}
                         for f in custom_foods],
        "recipes": [{**r, "items": _j(r["items"], [])} for r in recipes],
        "body_measurements": body,
        "recovery_checkins": [
            {**r, "soreness_regions": _j(r["soreness_regions"], [])}
            for r in recovery],
        "symptom_episodes": symptoms,
        "training_restrictions": [
            {**r, "affected_activities": _j(r["affected_activities"], {})}
            for r in restrictions],
        "personal_trials": [
            {**t, "baseline": _j(t["baseline"], None),
             "origin": _j(t["origin"], None),
             "chosen_target": _j(t["chosen_target"], None)}
            for t in trials],
        "user_equipment": [{**e, "aliases": _j(e["aliases"], [])}
                           for e in equipment],
        "training_locations": [
            {**l, "required_equipment": _j(l["required_equipment"], []),
             "optional_equipment": _j(l["optional_equipment"], [])}
            for l in locations],
        "expert_insights_index": insights,
        "motion_analyses_index": motion,
        "body_measurement_revisions": [
            {**r, "old_data": _j(r["old_data"], None),
             "new_data": _j(r["new_data"], None)} for r in body_revisions],
        "recovery_revisions": [
            {**r, "old_data": _j(r["old_data"], None),
             "new_data": _j(r["new_data"], None)} for r in recovery_revisions],
        "symptom_observations": [
            {**o, "functional_limitations": _j(o["functional_limitations"], []),
             "triage_result": _j(o["triage_result"], {})}
            for o in symptom_observations],
        "training_restriction_revisions": [
            {**r, "old_data": _j(r["old_data"], None),
             "new_data": _j(r["new_data"], None)}
            for r in restriction_revisions],
        "training_approach": (
            {"content": _j(approach[0]["content"], {}),
             "updated_at": approach[0]["updated_at"]} if approach else None),
        "approach_revisions": [
            {**r, "content": _j(r["content"], {}), "diff": _j(r["diff"], [])}
            for r in approach_revisions],
        "nutrition_targets": nutrition_targets[0] if nutrition_targets else None,
        "nutrition_days": nutrition_days,
        "user_exercise": user_exercise,
        "coach_notes": coach_notes,
        "knowledge_discussions": discussions,
        "care_plans": care_plans,
        "care_activities": care_activities,
        "care_activity_logs": care_logs,
        "imported_device_records": device_records,
        "expert_settings": expert_settings[0] if expert_settings else None,
        "custom_exercises": [
            {**r, "doc": _j(r["doc"], {})} for r in custom_exercises],
        "exercise_proposals": [
            {**r, "aliases": _j(r["aliases"], [])} for r in exercise_proposals],
        "knowledge_sources": knowledge_sources,
        "knowledge_chunks": knowledge_chunks,
        "knowledge_claims": [
            {**r, "duplicate_of": _j(r["duplicate_of"], None),
             "conflict_with": _j(r["conflict_with"], None)}
            for r in knowledge_claims],
        "messages": messages,
        "agent_consultations": [
            {**r, "specialists": _j(r["specialists"], []),
             "advices": _j(r["advices"], [])} for r in consultations],
        "change_proposals": [
            {**r, "operations": _j(r["operations"], []),
             "base_version": _j(r["base_version"], {}),
             "result": _j(r["result"], None)} for r in proposals],
        "media_assets": [
            {**m, "transcript": _j(m["transcript"], []),
             "candidates": _j(m["candidates"], [])} for m in media],
        "exercise_media_links": media_links,
        "motion_analyses": [
            {**m, "result": _j(m["result"], {})} for m in motion_full],
        "motion_tech_profiles": [
            {**m, "video_quality": _j(m["video_quality"], {}),
             "motion_observations": _j(m["motion_observations"], []),
             "phase_timestamps": _j(m["phase_timestamps"], [])}
            for m in motion_profiles],
    }
    exercise_mapping = {}
    for c in user_data["checkins"]:
        for ex in c["data"].get("exercises") or []:
            eid = ex.get("exercise_id")
            if eid and eid not in exercise_mapping:
                exercise_mapping[eid] = ex.get("name") or eid
    equipment_mapping = {e["equipment_id"]: e["name"]
                         for e in user_data["user_equipment"]}
    media_manifest = []
    for m in media:
        ref = {"id": m["id"], "title": m["title"], "file_ref": m["video_path"],
               "status": m["status"], "created_at": m["created_at"],
               "sha256": None}
        if m["video_path"] and os.path.exists(m["video_path"]):
            h = hashlib.sha256()
            with open(m["video_path"], "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            ref["sha256"] = h.hexdigest()
        media_manifest.append(ref)
    for m in motion:
        if m.get("video_path") and os.path.exists(m["video_path"]):
            h = hashlib.sha256()
            with open(m["video_path"], "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            media_manifest.append({"id": f"motion-{m['id']}",
                                   "title": f"动作视频 {m['exercise_id']}",
                                   "file_ref": m["video_path"],
                                   "status": m["status"],
                                   "created_at": m["created_at"],
                                   "sha256": h.hexdigest()})
    source_revisions = {
        "plans_max_version": max((p["version"] for p in plans), default=0),
        "checkin_ids": [c["id"] for c in checkins],
        "meal_days": sorted({m["local_date"] for m in meals}),
        "restrictions_version": db.restrictions_version(user_id),
        "symptoms_version": db.symptoms_version(user_id),
        "equipment": equipment_version(db, user_id),
    }
    export = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_version": EXPORT_VERSION,
        "exported_at": _now(),
        "exported_for": user_id,
        "user_data": user_data,
        "source_revisions": source_revisions,
        "exercise_mapping": exercise_mapping,
        "equipment_mapping": equipment_mapping,
        "media_manifest": media_manifest,
    }
    export["integrity_manifest"] = _integrity(export)
    return export


_SECTIONS = ("user_data", "source_revisions", "exercise_mapping",
             "equipment_mapping", "media_manifest")


def _canonical_numbers(value):
    """把 75.0 规范成 75，保证 Python/JS JSON roundtrip 后哈希仍一致。

    JSON 不区分 int/float；浏览器下载再上传时 75.0 会变成 75。若直接对
    Python 原始对象做哈希，完整备份会在浏览器 E2E 中被误判为篡改。
    """
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [_canonical_numbers(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canonical_numbers(v) for k, v in value.items()}
    return str(value)


def _integrity(export: dict) -> dict:
    out = {}
    for section in _SECTIONS:
        blob = json.dumps(_canonical_numbers(export.get(section)),
                          ensure_ascii=False, sort_keys=True, default=str)
        out[section] = hashlib.sha256(blob.encode()).hexdigest()
    out["schema_version"] = EXPORT_SCHEMA_VERSION
    return out


def _integrity_legacy(export: dict) -> dict:
    out = {}
    for section in _SECTIONS:
        blob = json.dumps(export.get(section), ensure_ascii=False,
                          sort_keys=True, default=str)
        out[section] = hashlib.sha256(blob.encode()).hexdigest()
    out["schema_version"] = EXPORT_SCHEMA_VERSION
    return out


def verify_integrity(export: dict) -> dict:
    stored = export.get("integrity_manifest") or {}
    fresh = _integrity(export)
    if stored == fresh:
        return {"ok": True, "mismatched": [], "legacy": False}
    legacy = _integrity_legacy(export)
    if stored == legacy:
        return {"ok": True, "mismatched": [], "legacy": True}
    return {"ok": False,
            "mismatched": [k for k in fresh if stored.get(k) != fresh[k]],
            "legacy": False}


def _csv_safe(value):
    """防电子表格公式注入：用户可控文本以 = + - @ 或制表/回车开头时加前缀。"""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def export_csv(export: dict) -> bytes:
    """用户可读的 CSV（zip：每节一个文件，训练逐组展开）。"""
    buf = io.BytesIO()
    user_data = export["user_data"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def write(name: str, rows: list[dict]):
            if not rows:
                return
            text = io.StringIO()
            writer = csv.DictWriter(text, fieldnames=list(rows[0].keys()),
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows([{k: _csv_safe(v) for k, v in row.items()}
                              for row in rows])
            zf.writestr(name, text.getvalue())

        write("profile.csv", [user_data["profile"]])
        write("plans.csv", [{**p, "content": json.dumps(
            p["content"], ensure_ascii=False)} for p in user_data["plans"]])
        set_rows = []
        for c in user_data["checkins"]:
            meta = (c["data"].get("session_meta") or {})
            for ex in c["data"].get("exercises") or []:
                for log in ex.get("set_logs") or []:
                    set_rows.append({
                        "date": meta.get("local_date", ""),
                        "exercise": ex.get("name"),
                        "exercise_id": ex.get("exercise_id") or "",
                        "type": log.get("type") or "weight_reps",
                        "method": log.get("method") or "straight_set",
                        "weight_kg": log.get("weight_kg", ""),
                        "reps": log.get("reps", ""),
                        "duration_seconds": log.get("duration_seconds", ""),
                        "distance_m": log.get("distance_m", ""),
                        "rpe": log.get("rpe", ""),
                        "warmup": bool(log.get("warmup")),
                    })
        write("training_sets.csv", set_rows)
        write("meals.csv", [{**m, "items": json.dumps(m["items"],
                                                      ensure_ascii=False)}
                            for m in user_data["meals"]])
        write("body_measurements.csv", user_data["body_measurements"])
        write("recovery_checkins.csv", user_data["recovery_checkins"])
        write("symptom_episodes.csv", user_data["symptom_episodes"])
        write("training_restrictions.csv",
              [{**r, "affected_activities": json.dumps(
                  r["affected_activities"], ensure_ascii=False)}
               for r in user_data["training_restrictions"]])
        write("personal_trials.csv", user_data["personal_trials"])
        write("media_manifest.csv", export["media_manifest"])
        zf.writestr("integrity_manifest.json", json.dumps(
            export["integrity_manifest"], ensure_ascii=False, indent=1))
    return buf.getvalue()
