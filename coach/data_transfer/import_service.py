"""RC-FIX-A：完整备份导入（预览 → 用户确认 → 单事务执行）。

设计（在 P7-A 基础上扩展）：
- 覆盖用户创建的健康/训练/营养/康复/知识/媒体元数据；派生分析索引不导入
  （专家洞察/任务可由事实重新生成）；
- 关系保留：旧 id → 新 id 映射，修订链/尝试/恢复/症状关联一并改写；
- 幂等：同内容指纹/自然键跳过，版本冲突显式报告，不覆盖当前记录；
- 安全状态：professional 限制在缺少可信解除依据时保持生效/待复核；
  医疗筛查、专业评估字段默认不当作可信许可（accept_safety_import 才按声明）；
- 计划：默认仅归档（inactive）；显式 activate_plan 且通过医疗/限制/隔离门
  才恢复为可执行；已有生效计划需 replace_active_plan；
- 事务：任何写入异常整体回滚；文件不随 JSON 导入，媒体清单只做存在/哈希核对。
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from .export_service import EXPORT_SCHEMA_VERSION, verify_integrity

MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_JSON_DEPTH = 40
MAX_JSON_NODES = 200_000
MAX_MEDIA_HASH_BYTES = 2 * 1024 * 1024 * 1024  # 单个引用最多 2GB

_ALLOWED_TOP = ("schema_version", "export_version", "exported_at",
                "exported_for", "user_data", "source_revisions",
                "exercise_mapping", "equipment_mapping", "media_manifest",
                "integrity_manifest")

# 导入时显式跳过/需要说明的派生节
_DERIVED_SKIPPED = ("expert_insights_index", "motion_analyses_index",
                    "expert_tasks", "expert_task_events",
                    "change_proposals（审计记录，不重建）",
                    "media_assets/exercise_media_links/motion_analyses "
                    "元数据（媒体文件本体不随 JSON；按清单另行恢复）")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _j(text, default):
    try:
        return json.loads(text) if text else default
    except (ValueError, TypeError):
        return default


def _check_json_complexity(value, depth: int = 0,
                           counter: list[int] | None = None) -> None:
    """限制恶意深嵌套/超宽 JSON，避免解析后递归/内存滥用。"""
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_JSON_NODES:
        raise ValueError("备份 JSON 节点过多（拒绝写入）")
    if depth > MAX_JSON_DEPTH:
        raise ValueError("备份 JSON 嵌套过深（拒绝写入）")
    if isinstance(value, dict):
        for k, v in value.items():
            _check_json_complexity(k, depth + 1, counter)
            _check_json_complexity(v, depth + 1, counter)
    elif isinstance(value, list):
        for v in value:
            _check_json_complexity(v, depth + 1, counter)


def _validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("备份必须是 JSON 对象")
    try:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise ValueError(f"备份不是可序列化 JSON：{e}") from None
    if len(encoded) > MAX_IMPORT_BYTES:
        raise ValueError(f"备份超过导入上限（{MAX_IMPORT_BYTES // (1024*1024)}MB）")
    _check_json_complexity(payload)
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


# ---- 指纹 / 去重 ---------------------------------------------------------

def _stable(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      default=str, separators=(",", ":"))


def _fp(value) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()[:32]


def _checkin_fingerprint(data: dict) -> str:
    return _fp(data)


def _body_fp(row: dict) -> str:
    keys = ("measured_at", "local_date", "weight_kg", "waist_cm", "hip_cm",
            "chest_cm", "body_fat_percent", "muscle_mass_kg",
            "measurement_method", "device_source")
    return _fp({k: row.get(k) for k in keys})


def _symptom_fp(row: dict) -> str:
    return _fp({k: row.get(k) for k in
                ("body_region", "side", "onset_at", "description")})


def _restriction_fp(row: dict) -> str:
    affected = row.get("affected_activities")
    if isinstance(affected, str):
        affected = _j(affected, {})
    return _fp({k: row.get(k) for k in
                ("source_type", "restriction_description",
                 "effective_at")} | {"affected_activities": affected})


def _trial_fp(row: dict) -> str:
    return _fp({k: row.get(k) for k in ("change_desc", "created_at")})


def _table_cols(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _insert_row(conn, table: str, row: dict, user_id: str,
                omit: tuple[str, ...] = ("id",),
                overrides: dict | None = None,
                ignore: bool = False) -> int | None:
    """按实际列插入一行；JSON 自动编码，bool→int。返回 lastrowid。"""
    cols = _table_cols(conn, table)
    data = {}
    for k, v in row.items():
        if k in omit or k not in cols:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            v = int(v)
        data[k] = v
    if "user_id" in cols:
        data["user_id"] = user_id
    if overrides:
        data.update(overrides)
    if not data:
        return None
    names = list(data)
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    sql = (f"{verb} INTO {table} ({','.join(names)})"
           f" VALUES ({','.join('?' for _ in names)})")
    cur = conn.execute(sql, [data[k] for k in names])
    return cur.lastrowid if cur.rowcount else None


def _existing_ids(db, user_id: str) -> dict:
    q = lambda sql: {r[0] for r in db.conn.execute(sql, (user_id,)).fetchall()}
    return {
        "checkin_ids": q("SELECT id FROM checkins WHERE user_id=?"),
        "meal_ids": q("SELECT id FROM meal_entries WHERE user_id=?"),
        "body_ids": q("SELECT id FROM body_measurements WHERE user_id=?"),
        "recovery_ids": q("SELECT id FROM recovery_checkins WHERE user_id=?"),
        "symptom_ids": q("SELECT id FROM symptom_episodes WHERE user_id=?"),
        "restriction_ids": q("SELECT id FROM training_restrictions WHERE user_id=?"),
        "trial_ids": q("SELECT id FROM personal_trials WHERE user_id=?"),
        "template_names": q("SELECT name FROM training_templates WHERE user_id=?"),
        "recipe_names": q("SELECT name FROM nutrition_recipes WHERE user_id=?"),
        "food_names": q("SELECT name FROM foods WHERE user_id=?"),
        "equipment_ids": q("SELECT equipment_id FROM user_equipment WHERE user_id=?"),
        "location_names": q("SELECT name FROM training_locations WHERE user_id=?"),
        "source_hashes": q("SELECT content_hash FROM knowledge_sources WHERE user_id=?"),
    }


def _media_report(db, target_user: str, payload: dict) -> dict:
    """核对媒体清单：存在性 + sha256 + 路径边界；不做文件复制。"""
    manifest = payload.get("media_manifest") or []
    source_user = str(payload.get("exported_for") or target_user)
    base = (db.path.parent / "media" / source_user).resolve()
    report = {"checked": 0, "ok": [], "missing": [], "corrupt": [],
              "unverified": [], "unsafe_path": [], "note": ""}
    for item in manifest:
        if not isinstance(item, dict):
            continue
        report["checked"] += 1
        ref = item.get("file_ref")
        if not ref:
            report["missing"].append({"id": item.get("id"), "file_ref": None})
            continue
        try:
            path = Path(str(ref)).resolve()
        except (OSError, ValueError):
            report["unsafe_path"].append({"id": item.get("id"), "file_ref": ref})
            continue
        # 只允许源用户的 media/<uid> 下文件；防止导入文件读取任意本机路径。
        if path != base and base not in path.parents:
            report["unsafe_path"].append({"id": item.get("id"), "file_ref": ref})
            continue
        if not path.is_file():
            report["missing"].append({"id": item.get("id"), "file_ref": ref})
            continue
        expected = item.get("sha256")
        if not expected:
            report["unverified"].append({"id": item.get("id"), "file_ref": ref})
            continue
        if path.stat().st_size > MAX_MEDIA_HASH_BYTES:
            report["unverified"].append({"id": item.get("id"),
                                         "file_ref": ref,
                                         "reason": "文件过大，未计算哈希"})
            continue
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            report["corrupt"].append({"id": item.get("id"), "file_ref": ref})
        else:
            report["ok"].append({"id": item.get("id"), "file_ref": ref})
    if report["missing"] or report["corrupt"] or report["unsafe_path"]:
        report["note"] = ("媒体不完整：结构化数据可导入，但相关文件需单独恢复；"
                          "未通过校验的文件不会被视为可用")
    elif report["unverified"]:
        report["note"] = "部分媒体缺少 sha256，无法证明内容完整性"
    else:
        report["note"] = "媒体清单全部通过存在性与哈希校验（文件未复制）"
    return report


def _safety_review(payload: dict, target_profile: dict) -> dict:
    ud = payload.get("user_data") or {}
    src = ud.get("profile") or {}
    hs = (src.get("conditions") or {}).get("health_screen") or {}
    items = []
    if hs:
        items.append({"kind": "profile_health_screen",
                      "detail": "导入档案含健康筛查/训练许可字段，"
                                "系统不会把它自动当作可信医疗许可"})
    if (src.get("conditions") or {}).get("injuries"):
        items.append({"kind": "profile_injuries",
                      "detail": "导入档案含伤病史，将用于限制动作"})
    for ep in ud.get("symptom_episodes") or []:
        if ep.get("professional_evaluated"):
            items.append({"kind": "symptom_professional_evaluated",
                          "detail": f"症状事件 {ep.get('id')} 声称已专业评估"})
    for r in ud.get("training_restrictions") or []:
        if r.get("source_type") == "professional":
            items.append({"kind": "professional_restriction",
                          "detail": f"限制 {r.get('id')} 声称来自专业人员"})
    target_onboarded = bool(target_profile.get("onboarding_done"))
    return {"items": items, "target_profile_onboarded": target_onboarded,
            "requires_accept_safety_import": bool(items)}


def _restriction_import_state(row: dict, accept_safety: bool) -> tuple[str, str | None]:
    """返回 (status, review_note)。professional 解除缺依据→保持 active。"""
    src_status = str(row.get("status") or "active")
    source_type = str(row.get("source_type") or "")
    evidence = str(row.get("lift_evidence") or "").strip()
    if src_status == "lifted":
        if source_type == "professional" and len(evidence) < 10:
            return "active", ("源备份声称已解除，但缺少可信专业人员说明；"
                              "导入后保持生效，需在康复工作台复核")
        if not evidence:
            return "active", "源备份缺少解除依据；导入后保持生效待复核"
        return "lifted", None
    if src_status not in ("active", "expired"):
        return "active", f"未知限制状态 {src_status!r}，导入后置为 active 待复核"
    return src_status, None


def _activation_blockers(db, user_id: str, profile: dict,
                         plan_content: dict) -> list[str]:
    from coach.medical import training_permission
    from coach.rehab import restriction_service
    from coach import exercise_service
    blockers = []
    fence = profile.get("plan_fence")
    if fence:
        blockers.append(f"计划已隔离：{fence.get('reason', '未知原因')}")
    if not training_permission(profile).allows_prescription:
        blockers.append("当前医疗许可不允许训练处方")
    for day in plan_content.get("schedule") or []:
        for entry in (day.get("exercises") if isinstance(day, dict) else []) or []:
            if not isinstance(entry, dict):
                continue
            ex_id = entry.get("exercise_id")
            if not ex_id:
                continue
            doc = exercise_service.get_exercise(db, user_id, ex_id)
            if not doc:
                continue
            hit = restriction_service.restriction_blocks(db, user_id, doc)
            if hit:
                blockers.append(f"动作「{doc.get('name')}」与当前限制冲突："
                                f"{hit['reason']}")
    return blockers


def preview_import(db, user_id: str, payload: dict) -> dict:
    """预览：不写库。返回计数/重复/冲突/安全与媒体报告/激活选项。"""
    _validate_payload(payload)
    ud = payload["user_data"]
    target_profile = db.get_existing_profile(user_id) or {}
    counts: dict[str, dict] = {}
    duplicates, conflicts = [], []
    actions: list[str] = []

    existing_checkins = {
        _checkin_fingerprint(_j(d, {}))
        for (d,) in db.conn.execute(
            "SELECT data FROM checkins WHERE user_id=?", (user_id,)).fetchall()}
    new_checkins = 0
    for c in ud.get("checkins") or []:
        if _checkin_fingerprint(c.get("data") or {}) in existing_checkins:
            duplicates.append({"section": "checkins",
                               "reason": "同内容训练记录"})
        else:
            new_checkins += 1
    counts["checkins"] = {"total": len(ud.get("checkins") or []),
                          "to_insert": new_checkins,
                          "duplicates": len(ud.get("checkins") or []) - new_checkins}
    actions.append(f"训练打卡：新增 {new_checkins} 条，跳过重复 "
                   f"{counts['checkins']['duplicates']} 条")

    # plans：版本相同且内容一致=重复；同版本不同内容=冲突
    existing_plans = {r["version"]: _fp(_j(r["content"], {}))
                      for r in db.conn.execute(
                          "SELECT version,content FROM plans WHERE user_id=?",
                          (user_id,)).fetchall()}
    new_plans, plan_conflicts = [], []
    for p in ud.get("plans") or []:
        v = p.get("version")
        h = _fp(p.get("content") or {})
        if v in existing_plans:
            if existing_plans[v] == h:
                duplicates.append({"section": "plans", "reason": f"计划 v{v} 已存在且内容一致"})
            else:
                plan_conflicts.append({"section": "plans", "version": v,
                                       "reason": "同版本不同内容"})
                conflicts.append(plan_conflicts[-1])
        else:
            new_plans.append(p)
    counts["plans"] = {"total": len(ud.get("plans") or []),
                       "to_insert": len(new_plans),
                       "duplicates": len(ud.get("plans") or []) - len(new_plans)}
    actions.append(f"计划：新增 {len(new_plans)} 个版本（默认归档不激活）；"
                   f"冲突 {len(plan_conflicts)} 个")

    def _dupe_count(section, rows, existing: set, fp):
        n = sum(1 for r in rows if fp(r) in existing)
        counts[section] = {"total": len(rows), "to_insert": len(rows) - n,
                           "duplicates": n}
        if n:
            duplicates.append({"section": section, "reason": f"同内容 {n} 条"})
        return len(rows) - n

    _dupe_count("body_measurements", ud.get("body_measurements") or [],
                {_body_fp(dict(r)) for r in db.conn.execute(
                    "SELECT * FROM body_measurements WHERE user_id=?",
                    (user_id,)).fetchall()}, _body_fp)
    existing_recovery_dates = {r["local_date"] for r in db.conn.execute(
        "SELECT local_date FROM recovery_checkins WHERE user_id=?",
        (user_id,)).fetchall()}
    rec_new = sum(1 for r in ud.get("recovery_checkins") or []
                  if r.get("local_date") not in existing_recovery_dates)
    counts["recovery_checkins"] = {
        "total": len(ud.get("recovery_checkins") or []),
        "to_insert": rec_new,
        "duplicates": len(ud.get("recovery_checkins") or []) - rec_new}
    _dupe_count("symptom_episodes", ud.get("symptom_episodes") or [],
                {_symptom_fp(dict(r)) for r in db.conn.execute(
                    "SELECT * FROM symptom_episodes WHERE user_id=?",
                    (user_id,)).fetchall()}, _symptom_fp)
    _dupe_count("training_restrictions",
                ud.get("training_restrictions") or [],
                {_restriction_fp(dict(r)) for r in db.conn.execute(
                    "SELECT * FROM training_restrictions WHERE user_id=?",
                    (user_id,)).fetchall()}, _restriction_fp)
    _dupe_count("personal_trials", ud.get("personal_trials") or [],
                {_trial_fp(dict(r)) for r in db.conn.execute(
                    "SELECT * FROM personal_trials WHERE user_id=?",
                    (user_id,)).fetchall()}, _trial_fp)

    # 命名/键去重
    existing_names = {
        "training_templates": {r["name"] for r in db.conn.execute(
            "SELECT name FROM training_templates WHERE user_id=?", (user_id,))},
        "recipes": {r["name"] for r in db.conn.execute(
            "SELECT name FROM nutrition_recipes WHERE user_id=?", (user_id,))},
        "custom_foods": {r["name"] for r in db.conn.execute(
            "SELECT name FROM foods WHERE user_id=?", (user_id,))},
        "training_locations": {r["name"] for r in db.conn.execute(
            "SELECT name FROM training_locations WHERE user_id=?", (user_id,))},
    }
    for section, key in (("training_templates", "name"),
                         ("recipes", "name"),
                         ("custom_foods", "name"),
                         ("training_locations", "name")):
        rows = ud.get(section) or []
        dup = sum(1 for r in rows if r.get(key) in existing_names[section])
        counts[section] = {"total": len(rows), "to_insert": len(rows) - dup,
                           "duplicates": dup}
    existing_equipment = {r["equipment_id"] for r in db.conn.execute(
        "SELECT equipment_id FROM user_equipment WHERE user_id=?",
        (user_id,)).fetchall()}
    eq_rows = ud.get("user_equipment") or []
    dup_eq = sum(1 for r in eq_rows if r.get("equipment_id") in existing_equipment)
    counts["user_equipment"] = {"total": len(eq_rows),
                                "to_insert": len(eq_rows) - dup_eq,
                                "duplicates": dup_eq}
    counts["meals"] = {"total": len(ud.get("meals") or []),
                       "to_insert": len(ud.get("meals") or []),
                       "note": "同日同餐同内容跳过"}
    for section in ("checkin_revisions", "body_measurement_revisions",
                    "recovery_revisions", "symptom_observations",
                    "training_restriction_revisions", "approach_revisions"):
        counts[section] = {"total": len(ud.get(section) or []),
                           "to_insert": len(ud.get(section) or [])}
    counts["personal_trials"] = counts.get("personal_trials", {"total": 0,
                                                              "to_insert": 0})
    counts["user_exercise"] = {"total": len(ud.get("user_exercise") or []),
                                "to_insert": len(ud.get("user_exercise") or [])}
    counts["knowledge_sources"] = {
        "total": len(ud.get("knowledge_sources") or []),
        "to_insert": len(ud.get("knowledge_sources") or [])}
    counts["nutrition_recipes"] = dict(counts["recipes"])  # 兼容旧字段名

    # 安全状态 / 媒体 / 计划激活
    safety = _safety_review(payload, target_profile)
    media = _media_report(db, user_id, payload)
    plans = ud.get("plans") or []
    source_active_version = next(
        (p.get("version") for p in plans if p.get("active")), None)
    if source_active_version is None and plans:
        source_active_version = max(p.get("version") for p in plans)
    active_record = db.get_active_plan_record(user_id)
    source_profile = ud.get("profile") or target_profile
    active_plan = next((p for p in plans
                        if p.get("version") == source_active_version), None)
    blockers = _activation_blockers(
        db, user_id, source_profile, (active_plan or {}).get("content") or {}) \
        if active_plan else ["备份没有可激活的计划"]
    if active_record:
        blockers.append(f"目标用户已有生效计划 v{active_record['version']}；"
                        "激活需 replace_active_plan=true")
    profile_conflict = bool(target_profile.get("onboarding_done")) and \
        _stable(ud.get("profile") or {}) != _stable(target_profile)
    return {
        "kind": "import_preview_v2",
        "schema_version": payload.get("schema_version"),
        "exported_at": payload.get("exported_at"),
        "exported_for": payload.get("exported_for"),
        "target_user": user_id,
        "counts": counts,
        "duplicates": duplicates[:30],
        "conflicts": conflicts,
        "actions": actions,
        "profile_conflict": profile_conflict,
        "profile_restore_default": not bool(target_profile.get("onboarding_done")),
        "safety_review": safety,
        "media_report": media,
        "source_active_plan_version": source_active_version,
        "can_activate_plan": not blockers,
        "activation_blockers": blockers,
        "requires_confirmation": True,
        "options": {
            "restore_profile": "目标未建档时默认恢复；已建档需显式 true",
            "activate_plan": "默认 false：仅归档；true 且无阻断时恢复为可执行",
            "replace_active_plan": "目标已有生效计划时必须显式 true",
            "accept_safety_import": "医疗筛查/专业评估按备份声明导入的显式确认",
            "require_media_integrity": "为 true 时媒体缺失/哈希不符将拒绝导入",
        },
        "derived_skipped": list(_DERIVED_SKIPPED),
        "skipped_sections": list(_DERIVED_SKIPPED),
    }


def _validate_rows(ud: dict) -> None:
    problems = []
    for section, fields in {
        "checkins": ("type", "data"),
        "plans": ("version", "content"),
        "meals": ("local_date", "meal_type", "items"),
        "body_measurements": ("measured_at", "local_date"),
        "recovery_checkins": ("local_date", "recorded_at"),
        "symptom_episodes": ("body_region", "onset_at", "description"),
        "training_restrictions": ("restriction_description",),
    }.items():
        for i, row in enumerate(ud.get(section) or []):
            if not isinstance(row, dict):
                problems.append(f"{section}[{i}] 不是对象")
                continue
            missing = [f for f in fields
                       if row.get(f) in (None, "") and f != "data"]
            if missing:
                problems.append(f"{section}[{i}] 缺少必填字段：{missing}")
    for i, row in enumerate(ud.get("training_restrictions") or []):
        if not isinstance(row, dict):
            continue
        if row.get("source_type") not in ("user_reported", "professional",
                                          "triage_recommended"):
            problems.append(f"training_restrictions[{i}] source_type 非法："
                            f"{row.get('source_type')!r}")
        status = row.get("status")
        if status not in (None, "active", "lifted", "expired"):
            problems.append(f"training_restrictions[{i}] status 非法：{status!r}")
    if problems:
        raise ValueError("备份行校验未通过（未写入任何数据）："
                         + "；".join(problems[:8]))


def _rewrite_food_ids(items: list, food_map: dict) -> list:
    out = []
    for item in items or []:
        if isinstance(item, dict):
            item = dict(item)
            if item.get("food_id") in food_map:
                item["food_id"] = food_map[item["food_id"]]
        out.append(item)
    return out


def _map_baseline_revisions(raw, id_maps: dict):
    if not raw:
        return raw
    data = _j(raw, None) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        return raw
    data = json.loads(json.dumps(data, ensure_ascii=False))
    checkins = data.get("checkins")
    if isinstance(checkins, dict):
        data["checkins"] = {
            str(id_maps["checkins"].get(int(k), k)): v
            for k, v in checkins.items()
        }
    plan = data.get("plan")
    if isinstance(plan, dict) and "plan_id" in plan:
        plan["plan_id"] = id_maps["plans"].get(plan["plan_id"], plan["plan_id"])
    return json.dumps(data, ensure_ascii=False)


def apply_import(db, user_id: str, payload: dict, *,
                 restore_profile: bool = False,
                 activate_plan: bool = False,
                 replace_active_plan: bool = False,
                 accept_safety_import: bool = False,
                 require_media_integrity: bool = False) -> dict:
    """应用导入：单事务；任何异常整体回滚；不覆盖既有记录。"""
    _validate_payload(payload)
    _validate_rows(payload["user_data"])
    preview = preview_import(db, user_id, payload)
    media = preview["media_report"]
    if require_media_integrity and (media["missing"] or media["corrupt"]
                                    or media["unsafe_path"]):
        raise ValueError("媒体完整性校验未通过：缺少 "
                         f"{len(media['missing'])}、损坏 {len(media['corrupt'])}、"
                         f"越界路径 {len(media['unsafe_path'])}；未写入任何数据")
    ud = payload["user_data"]
    target_profile = db.get_existing_profile(user_id) or {}
    id_maps = {k: {} for k in ("plans", "checkins", "meals", "foods",
                               "body", "recovery", "symptoms", "restrictions",
                               "care_plans", "activities", "sources",
                               "chunks", "media", "motion")}
    inserted = {k: 0 for k in (
        "profile", "plans", "checkins", "checkin_revisions", "meals",
        "custom_foods", "recipes", "body", "body_revisions", "recovery",
        "recovery_revisions", "symptoms", "observations", "restrictions",
        "restriction_revisions", "trials", "templates", "equipment",
        "locations", "approach", "approach_revisions", "nutrition_targets",
        "user_exercise", "coach_notes", "discussions", "care_plans",
        "care_activities", "care_logs", "device_records", "knowledge_sources",
        "knowledge_chunks", "knowledge_claims", "messages", "consultations",
        "custom_exercises", "exercise_proposals", "expert_settings")}
    warnings, skipped, needs_review = [], [], []

    # ---- profile ----
    src_profile = ud.get("profile") or {}
    should_profile = restore_profile or not bool(
        target_profile.get("onboarding_done"))
    if should_profile and src_profile:
        profile = json.loads(json.dumps(src_profile, ensure_ascii=False))
        if not accept_safety_import:
            conditions = profile.setdefault("conditions", {})
            hs = conditions.setdefault("health_screen", {})
            hs["clearance"] = "未核验：从备份导入，需本人确认训练许可"
            conditions["health_screen_evidence"] = (
                "从备份导入（未经独立核验）；如为本人真实记录，请在档案中确认")
            profile["imported_safety_review"] = True
            warnings.append("医疗筛查/训练许可未按备份声明直接信任；"
                            "已置为待本人确认")
        profile_to_write = profile
        profile_should_write = _stable(profile_to_write) != _stable(target_profile)
        inserted["profile"] = 1 if profile_should_write else 0
    elif src_profile and _stable(src_profile) != _stable(target_profile):
        skipped.append("profile：目标已建档，未覆盖；如需恢复请 restore_profile=true")

    try:
        with db.conn:
            # ---- profile（与后续写入同一事务） ----
            if should_profile and src_profile and profile_should_write:
                if target_profile:
                    db.conn.execute(
                        "UPDATE users SET profile=?, updated_at=? WHERE user_id=?",
                        (json.dumps(profile_to_write, ensure_ascii=False),
                         _now(), user_id))
                else:
                    db.conn.execute(
                        "INSERT INTO users(user_id, profile, created_at, updated_at)"
                        " VALUES(?,?,?,?)",
                        (user_id, json.dumps(profile_to_write, ensure_ascii=False),
                         _now(), _now()))

            # ---- plans（全部归档；激活在事务尾部） ----
            existing_plans = {r["version"]: (r["id"], _fp(_j(r["content"], {})))
                              for r in db.conn.execute(
                                  "SELECT id,version,content FROM plans"
                                  " WHERE user_id=?", (user_id,)).fetchall()}
            for p in ud.get("plans") or []:
                v = p.get("version")
                h = _fp(p.get("content") or {})
                if v in existing_plans:
                    existing_id, existing_h = existing_plans[v]
                    if existing_h == h:
                        id_maps["plans"][p.get("id")] = existing_id
                    else:
                        warnings.append(f"计划 v{v} 与目标同版本不同内容，"
                                        "保留目标版本且不建立引用")
                    continue
                new_id = _insert_row(db.conn, "plans", p, user_id,
                                     overrides={"active": 0})
                if new_id:
                    id_maps["plans"][p.get("id")] = new_id
                    existing_plans[v] = (new_id, h)
                    inserted["plans"] += 1

            # ---- checkins + revisions ----
            existing_checkin_fp = {
                _checkin_fingerprint(_j(r["data"], {})): r["id"]
                for r in db.conn.execute(
                    "SELECT id,data FROM checkins WHERE user_id=?",
                    (user_id,)).fetchall()}
            for c in ud.get("checkins") or []:
                fp = _checkin_fingerprint(c.get("data") or {})
                if fp in existing_checkin_fp:
                    id_maps["checkins"][c.get("id")] = existing_checkin_fp[fp]
                    continue
                new_id = _insert_row(db.conn, "checkins", c, user_id)
                if new_id:
                    id_maps["checkins"][c.get("id")] = new_id
                    existing_checkin_fp[fp] = new_id
                    inserted["checkins"] += 1
            for r in ud.get("checkin_revisions") or []:
                old_cid = r.get("checkin_id")
                new_cid = id_maps["checkins"].get(old_cid)
                if not new_cid:
                    skipped.append(f"checkin_revision：源打卡 {old_cid} 未导入")
                    continue
                if _insert_row(db.conn, "checkin_revisions", r, user_id,
                               overrides={"checkin_id": new_cid}, ignore=True):
                    inserted["checkin_revisions"] += 1

            # ---- custom foods + recipes + meals ----
            existing_food_ids = {r["id"] for r in db.conn.execute(
                "SELECT id FROM foods").fetchall()}
            for f in ud.get("custom_foods") or []:
                old_id = f.get("id")
                name = f.get("name")
                row = next((r for r in db.conn.execute(
                    "SELECT id FROM foods WHERE user_id=? AND name=?",
                    (user_id, name)).fetchall()), None)
                if row:
                    id_maps["foods"][old_id] = row["id"]
                    continue
                new_id = old_id if old_id not in existing_food_ids else \
                    "imp-" + uuid.uuid4().hex[:12]
                inserted_id = _insert_row(db.conn, "foods", f, user_id,
                                          omit=("id",),
                                          overrides={"id": new_id,
                                                     "verified_status": "user_created"})
                if inserted_id:
                    id_maps["foods"][old_id] = new_id
                    inserted["custom_foods"] += 1
            existing_recipe_names = {r["name"] for r in db.conn.execute(
                "SELECT name FROM nutrition_recipes WHERE user_id=?",
                (user_id,)).fetchall()}
            for r in ud.get("recipes") or []:
                if r.get("name") in existing_recipe_names:
                    continue
                row = dict(r)
                row["items"] = _rewrite_food_ids(row.get("items") or [],
                                                 id_maps["foods"])
                if _insert_row(db.conn, "nutrition_recipes", row, user_id):
                    existing_recipe_names.add(r.get("name"))
                    inserted["recipes"] += 1
            existing_meal_keys = {
                (r["local_date"], r["meal_type"], _stable(_j(r["items"], [])))
                for r in db.conn.execute(
                    "SELECT local_date,meal_type,items FROM meal_entries"
                    " WHERE user_id=?", (user_id,)).fetchall()}
            for m in ud.get("meals") or []:
                row = dict(m)
                row["items"] = _rewrite_food_ids(row.get("items") or [],
                                                 id_maps["foods"])
                key = (row.get("local_date"), row.get("meal_type"),
                       _stable(row.get("items") or []))
                if key in existing_meal_keys:
                    continue
                if _insert_row(db.conn, "meal_entries", row, user_id):
                    existing_meal_keys.add(key)
                    inserted["meals"] += 1

            # ---- body + revisions ----
            existing_body = {_body_fp(dict(r)): r["id"] for r in db.conn.execute(
                "SELECT * FROM body_measurements WHERE user_id=?",
                (user_id,)).fetchall()}
            for b in ud.get("body_measurements") or []:
                fp = _body_fp(b)
                if fp in existing_body:
                    id_maps["body"][b.get("id")] = existing_body[fp]
                    continue
                new_id = _insert_row(db.conn, "body_measurements", b, user_id)
                if new_id:
                    id_maps["body"][b.get("id")] = new_id
                    existing_body[fp] = new_id
                    inserted["body"] += 1
            for r in ud.get("body_measurement_revisions") or []:
                new_mid = id_maps["body"].get(r.get("measurement_id"))
                if new_mid and _insert_row(
                        db.conn, "body_measurement_revisions", r, user_id,
                        overrides={"measurement_id": new_mid}, ignore=True):
                    inserted["body_revisions"] += 1

            # ---- recovery + revisions ----
            existing_recovery = {r["local_date"]: r["id"] for r in db.conn.execute(
                "SELECT id,local_date FROM recovery_checkins WHERE user_id=?",
                (user_id,)).fetchall()}
            for r in ud.get("recovery_checkins") or []:
                ld = r.get("local_date")
                if ld in existing_recovery:
                    id_maps["recovery"][r.get("id")] = existing_recovery[ld]
                    continue
                new_id = _insert_row(db.conn, "recovery_checkins", r, user_id)
                if new_id:
                    id_maps["recovery"][r.get("id")] = new_id
                    existing_recovery[ld] = new_id
                    inserted["recovery"] += 1
            for r in ud.get("recovery_revisions") or []:
                new_rid = id_maps["recovery"].get(r.get("recovery_id"))
                if new_rid and _insert_row(
                        db.conn, "recovery_revisions", r, user_id,
                        overrides={"recovery_id": new_rid}, ignore=True):
                    inserted["recovery_revisions"] += 1

            # ---- symptoms + observations + restrictions ----
            existing_symptoms = {_symptom_fp(dict(r)): r["id"] for r in db.conn.execute(
                "SELECT * FROM symptom_episodes WHERE user_id=?",
                (user_id,)).fetchall()}
            for ep in ud.get("symptom_episodes") or []:
                fp = _symptom_fp(ep)
                if fp in existing_symptoms:
                    id_maps["symptoms"][ep.get("id")] = existing_symptoms[fp]
                    continue
                row = dict(ep)
                row["related_checkin_id"] = id_maps["checkins"].get(
                    row.get("related_checkin_id"), row.get("related_checkin_id"))
                if not accept_safety_import:
                    if row.get("professional_evaluated"):
                        row["professional_evaluated"] = 0
                        needs_review.append(
                            f"症状 {ep.get('id')} 的专业评估声明未按可信导入")
                new_id = _insert_row(db.conn, "symptom_episodes", row, user_id)
                if new_id:
                    id_maps["symptoms"][ep.get("id")] = new_id
                    existing_symptoms[fp] = new_id
                    inserted["symptoms"] += 1
            existing_obs = set()
            for r in db.conn.execute(
                    "SELECT * FROM symptom_observations WHERE user_id=?",
                    (user_id,)).fetchall():
                r = dict(r)
                existing_obs.add((r.get("episode_id"), r.get("recorded_at"),
                                  r.get("severity"), r.get("symptom_description"),
                                  r.get("user_notes"),
                                  _stable(_j(r.get("functional_limitations"), [])),
                                  _stable(_j(r.get("triage_result"), {}))))
            for obs in ud.get("symptom_observations") or []:
                new_ep = id_maps["symptoms"].get(obs.get("episode_id"))
                if not new_ep:
                    continue
                key = (new_ep, obs.get("recorded_at"), obs.get("severity"),
                       obs.get("symptom_description"), obs.get("user_notes"),
                       _stable(obs.get("functional_limitations") or []),
                       _stable(obs.get("triage_result") or {}))
                if key in existing_obs:
                    continue
                if _insert_row(
                        db.conn, "symptom_observations", obs, user_id,
                        overrides={"episode_id": new_ep}):
                    existing_obs.add(key)
                    inserted["observations"] += 1

            existing_restrictions = {
                _restriction_fp(dict(r)): r for r in db.conn.execute(
                    "SELECT * FROM training_restrictions WHERE user_id=?",
                    (user_id,)).fetchall()}
            for r in ud.get("training_restrictions") or []:
                fp = _restriction_fp(r)
                if fp in existing_restrictions:
                    id_maps["restrictions"][r.get("id")] = \
                        existing_restrictions[fp]["id"]
                    continue
                status, review_note = _restriction_import_state(
                    r, accept_safety_import)
                row = dict(r)
                row["status"] = status
                row["related_episode_id"] = id_maps["symptoms"].get(
                    row.get("related_episode_id"),
                    row.get("related_episode_id"))
                if review_note:
                    row["source_evidence"] = (
                        str(row.get("source_evidence") or "") +
                        "｜导入复核：" + review_note)[:900]
                    needs_review.append(review_note)
                new_id = _insert_row(db.conn, "training_restrictions", row,
                                     user_id)
                if new_id:
                    id_maps["restrictions"][r.get("id")] = new_id
                    existing_restrictions[fp] = {**row, "id": new_id}
                    inserted["restrictions"] += 1
            for r in ud.get("training_restriction_revisions") or []:
                new_rid = id_maps["restrictions"].get(r.get("restriction_id"))
                if new_rid and _insert_row(
                        db.conn, "training_restriction_revisions", r, user_id,
                        overrides={"restriction_id": new_rid}, ignore=True):
                    inserted["restriction_revisions"] += 1

            # ---- trials（计划/打卡引用映射） ----
            existing_trial_fp = {_trial_fp(dict(r)) for r in db.conn.execute(
                "SELECT * FROM personal_trials WHERE user_id=?",
                (user_id,)).fetchall()}
            for t in ud.get("personal_trials") or []:
                if _trial_fp(t) in existing_trial_fp:
                    continue
                row = dict(t)
                old_plan = row.get("plan_id")
                if old_plan is not None:
                    try:
                        old_plan_int = int(old_plan)
                        row["plan_id"] = str(id_maps["plans"].get(
                            old_plan_int, old_plan))
                    except (TypeError, ValueError):
                        pass
                row["baseline_source_revisions"] = _map_baseline_revisions(
                    row.get("baseline_source_revisions"), id_maps)
                if _insert_row(db.conn, "personal_trials", row, user_id):
                    inserted["trials"] += 1

            # ---- templates / equipment / locations ----
            existing_templates = {r["name"] for r in db.conn.execute(
                "SELECT name FROM training_templates WHERE user_id=?",
                (user_id,)).fetchall()}
            for t in ud.get("training_templates") or []:
                if t.get("name") in existing_templates:
                    continue
                if _insert_row(db.conn, "training_templates", t, user_id):
                    existing_templates.add(t.get("name"))
                    inserted["templates"] += 1
            existing_equipment = {r["equipment_id"] for r in db.conn.execute(
                "SELECT equipment_id FROM user_equipment WHERE user_id=?",
                (user_id,)).fetchall()}
            for e in ud.get("user_equipment") or []:
                if e.get("equipment_id") in existing_equipment:
                    continue
                if _insert_row(db.conn, "user_equipment", e, user_id, ignore=True):
                    existing_equipment.add(e.get("equipment_id"))
                    inserted["equipment"] += 1
            existing_locations = {r["name"]: r for r in db.conn.execute(
                "SELECT * FROM training_locations WHERE user_id=?",
                (user_id,)).fetchall()}
            has_current = any(r["is_current"] for r in existing_locations.values())
            for l in ud.get("training_locations") or []:
                if l.get("name") in existing_locations:
                    id_maps["locations"] = id_maps.get("locations", {})
                    continue
                row = dict(l)
                if has_current:
                    row["is_current"] = 0
                elif row.get("is_current"):
                    has_current = True
                if _insert_row(db.conn, "training_locations", row, user_id):
                    existing_locations[l.get("name")] = row
                    inserted["locations"] += 1

            # ---- 自定义动作 / 动作提案 / 专家设置 ----
            existing_custom_ex = {r["ex_id"] for r in db.conn.execute(
                "SELECT ex_id FROM custom_exercises WHERE user_id=?",
                (user_id,)).fetchall()}
            for r in ud.get("custom_exercises") or []:
                if r.get("ex_id") in existing_custom_ex:
                    continue
                if _insert_row(db.conn, "custom_exercises", r, user_id,
                               ignore=True):
                    existing_custom_ex.add(r.get("ex_id"))
                    inserted["custom_exercises"] += 1
            existing_props = {_fp({k: r.get(k) for k in
                                   ("name", "created_at", "sentence")})
                              for r in db.conn.execute(
                                  "SELECT * FROM exercise_proposals WHERE user_id=?",
                                  (user_id,)).fetchall()}
            for r in ud.get("exercise_proposals") or []:
                fp = _fp({k: r.get(k) for k in ("name", "created_at", "sentence")})
                if fp in existing_props:
                    continue
                if _insert_row(db.conn, "exercise_proposals", r, user_id):
                    existing_props.add(fp)
                    inserted["exercise_proposals"] += 1
            settings = ud.get("expert_settings")
            existing_settings = db.conn.execute(
                "SELECT 1 FROM expert_settings WHERE user_id=?", (user_id,)).fetchone()
            if settings and not existing_settings:
                if _insert_row(db.conn, "expert_settings", settings, user_id,
                               ignore=True):
                    inserted["expert_settings"] = 1

            # ---- approach / nutrition targets / user exercise ----
            approach = ud.get("training_approach")
            existing_approach = db.conn.execute(
                "SELECT 1 FROM training_approach WHERE user_id=?",
                (user_id,)).fetchone()
            if approach and not existing_approach:
                if _insert_row(db.conn, "training_approach", approach, user_id):
                    inserted["approach"] = 1
            elif approach and existing_approach:
                warnings.append("训练方式已存在：保留当前版本，备份版本仅作为归档")
            existing_approach_revs = {r["revision"] for r in db.conn.execute(
                "SELECT revision FROM approach_revisions WHERE user_id=?",
                (user_id,)).fetchall()}
            for r in ud.get("approach_revisions") or []:
                if r.get("revision") in existing_approach_revs:
                    continue
                if _insert_row(db.conn, "approach_revisions", r, user_id,
                               ignore=True):
                    inserted["approach_revisions"] += 1
            targets = ud.get("nutrition_targets")
            existing_targets = db.conn.execute(
                "SELECT 1 FROM nutrition_targets WHERE user_id=?",
                (user_id,)).fetchone()
            if targets and not existing_targets:
                if _insert_row(db.conn, "nutrition_targets", targets, user_id):
                    inserted["nutrition_targets"] = 1
            elif targets and existing_targets:
                warnings.append("营养目标已存在：保留当前设置，未覆盖")
            for d in ud.get("nutrition_days") or []:
                if _insert_row(db.conn, "nutrition_days", d, user_id, ignore=True):
                    pass
            existing_ex = {r["exercise_id"] for r in db.conn.execute(
                "SELECT exercise_id FROM user_exercise WHERE user_id=?",
                (user_id,)).fetchall()}
            for r in ud.get("user_exercise") or []:
                if r.get("exercise_id") in existing_ex:
                    continue
                if _insert_row(db.conn, "user_exercise", r, user_id):
                    existing_ex.add(r.get("exercise_id"))
                    inserted["user_exercise"] += 1

            # ---- notes / discussions / care plans / device records ----
            for section, table, key in (
                    ("coach_notes", "coach_notes", "note"),
                    ("knowledge_discussions", "knowledge_discussions", "topic")):
                existing = {str(r[0]) for r in db.conn.execute(
                    f"SELECT {key} FROM {table} WHERE user_id=?",
                    (user_id,)).fetchall()}
                for r in ud.get(section) or []:
                    if str(r.get(key)) in existing:
                        continue
                    if _insert_row(db.conn, table, r, user_id):
                        existing.add(str(r.get(key)))
                        inserted[section] += 1
            existing_care = {r["title"] for r in db.conn.execute(
                "SELECT title FROM care_plans WHERE user_id=?", (user_id,)).fetchall()}
            for p in ud.get("care_plans") or []:
                if p.get("title") in existing_care:
                    continue
                row = dict(p)
                row["related_episode_id"] = id_maps["symptoms"].get(
                    row.get("related_episode_id"),
                    row.get("related_episode_id"))
                new_id = _insert_row(db.conn, "care_plans", row, user_id)
                if new_id:
                    id_maps["care_plans"][p.get("id")] = new_id
                    existing_care.add(p.get("title"))
                    inserted["care_plans"] += 1
            for a in ud.get("care_activities") or []:
                new_plan = id_maps["care_plans"].get(a.get("plan_id"))
                if not new_plan:
                    continue
                new_id = _insert_row(db.conn, "care_activities", a, user_id,
                                     overrides={"plan_id": new_plan})
                if new_id:
                    id_maps["activities"][a.get("id")] = new_id
                    inserted["care_activities"] += 1
            for log in ud.get("care_activity_logs") or []:
                new_aid = id_maps["activities"].get(log.get("activity_id"))
                if new_aid and _insert_row(
                        db.conn, "care_activity_logs", log, user_id,
                        overrides={"activity_id": new_aid}, ignore=True):
                    inserted["care_logs"] += 1
            for r in ud.get("imported_device_records") or []:
                if _insert_row(db.conn, "imported_device_records", r, user_id, ignore=True):
                    inserted["device_records"] += 1

            # ---- knowledge sources / chunks / claims（状态原样保留） ----
            existing_sources = {r["content_hash"]: r["id"] for r in db.conn.execute(
                "SELECT id,content_hash FROM knowledge_sources WHERE user_id=?",
                (user_id,)).fetchall()}
            for s in ud.get("knowledge_sources") or []:
                ch = s.get("content_hash")
                if ch in existing_sources:
                    id_maps["sources"][s.get("id")] = existing_sources[ch]
                    continue
                new_id = _insert_row(db.conn, "knowledge_sources", s, user_id)
                if new_id:
                    id_maps["sources"][s.get("id")] = new_id
                    existing_sources[ch] = new_id
                    inserted["knowledge_sources"] += 1
            existing_chunks = {
                (r["source_id"], r["seq"], r["content"])
                for r in db.conn.execute(
                    "SELECT source_id,seq,content FROM knowledge_chunks").fetchall()}
            for c in ud.get("knowledge_chunks") or []:
                new_src = id_maps["sources"].get(c.get("source_id"))
                if not new_src:
                    continue
                key = (new_src, c.get("seq"), c.get("content"))
                if key in existing_chunks:
                    continue
                new_id = _insert_row(db.conn, "knowledge_chunks", c, user_id,
                                     overrides={"source_id": new_src})
                if new_id:
                    id_maps["chunks"][c.get("id")] = new_id
                    existing_chunks.add(key)
                    inserted["knowledge_chunks"] += 1
            existing_claims = {
                (r["source_id"], r["content"])
                for r in db.conn.execute(
                    "SELECT source_id,content FROM knowledge_claims WHERE user_id=?",
                    (user_id,)).fetchall()}
            for cl in ud.get("knowledge_claims") or []:
                new_src = id_maps["sources"].get(cl.get("source_id"))
                if not new_src:
                    continue
                key = (new_src, cl.get("content"))
                if key in existing_claims:
                    continue
                row = dict(cl)
                row["source_id"] = new_src
                if row.get("chunk_id"):
                    row["chunk_id"] = id_maps["chunks"].get(
                        row["chunk_id"], row["chunk_id"])
                if _insert_row(db.conn, "knowledge_claims", row, user_id):
                    existing_claims.add(key)
                    inserted["knowledge_claims"] += 1

            # ---- messages / consultations（可追溯对话；不做派生重建） ----
            existing_msg = {_fp(r) for r in db.conn.execute(
                "SELECT role,content,created_at FROM messages WHERE user_id=?",
                (user_id,)).fetchall()}
            for m in ud.get("messages") or []:
                fp = _fp({k: m.get(k) for k in ("role", "content", "created_at")})
                if fp in existing_msg:
                    continue
                if _insert_row(db.conn, "messages", m, user_id):
                    existing_msg.add(fp)
                    inserted["messages"] += 1
            existing_consult = {_fp({k: r.get(k) for k in
                                     ("question", "specialists", "advices",
                                      "created_at")})
                                for r in db.conn.execute(
                                    "SELECT * FROM agent_consultations"
                                    " WHERE user_id=?", (user_id,)).fetchall()
                                for r in [dict(r)]}
            for c in ud.get("agent_consultations") or []:
                fp = _fp({k: c.get(k) for k in
                          ("question", "specialists", "advices", "created_at")})
                if fp in existing_consult:
                    continue
                if _insert_row(db.conn, "agent_consultations", c, user_id):
                    existing_consult.add(fp)
                    inserted["consultations"] += 1

            # ---- plan activation（事务尾部，先校验安全） ----
            activated = None
            activation_blocked = []
            source_active_version = preview["source_active_plan_version"]
            active_src = next((p for p in ud.get("plans") or []
                               if p.get("version") == source_active_version), None)
            if activate_plan and active_src:
                current = db.conn.execute(
                    "SELECT id,version FROM plans WHERE user_id=? AND active=1",
                    (user_id,)).fetchone()
                if current and not replace_active_plan:
                    activation_blocked.append(
                        f"已有生效计划 v{current['version']}；需 replace_active_plan")
                else:
                    profile_now = db.get_existing_profile(user_id) or {}
                    blockers = _activation_blockers(
                        db, user_id, profile_now, active_src.get("content") or {})
                    if blockers:
                        activation_blocked.extend(blockers)
                    else:
                        db.conn.execute(
                            "UPDATE plans SET active=0 WHERE user_id=?", (user_id,))
                        target_id = id_maps["plans"].get(active_src.get("id"))
                        if target_id:
                            db.conn.execute(
                                "UPDATE plans SET active=1 WHERE user_id=? AND id=?",
                                (user_id, target_id))
                            activated = {"plan_id": target_id,
                                         "version": source_active_version,
                                         "mode": "executable"}
            if not activated:
                # 归档模式：不改变目标现有 active；导入计划全部保持 inactive
                pass
    except Exception:
        raise

    return {
        "kind": "import_applied_v2",
        "inserted": inserted,
        "skipped": skipped[:20],
        "warnings": warnings,
        "needs_review": needs_review,
        "preview_summary": {"counts": preview["counts"],
                            "conflicts": preview["conflicts"]},
        "safety_review": preview["safety_review"],
        "media_report": media,
        "activated_plan": activated,
        "activation_blocked": activation_blocked,
        "mode": "executable" if activated else "archive",
        "skipped_sections": list(_DERIVED_SKIPPED),
        "note": ("导入为单事务；默认归档计划，不自动激活；未覆盖既有目标/训练方式；"
                 "媒体文件不随 JSON 复制；派生专家分析未导入。"),
    }
