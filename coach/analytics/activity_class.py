"""P5-B3：训练活动类别的唯一分类口径。

类别：
- strength：力量记录；
- steady_cardio：非间歇编排的有氧记录；
- interval：带有效 HIIT 元数据的间歇记录。

新保存/纠错记录在逐组数据中写入类别快照（activity_class + source +
version）。旧记录没有快照时按"有效 HIIT → 动作库 activity → 旧记录默认"
推断，并返回推断来源。统计接口同时暴露推断数量，历史语义变化不会无声发生。
"""
from __future__ import annotations

import copy

CLASS_STRENGTH = "strength"
CLASS_STEADY_CARDIO = "steady_cardio"
CLASS_INTERVAL = "interval"
ACTIVITY_CLASSES = (CLASS_STRENGTH, CLASS_STEADY_CARDIO, CLASS_INTERVAL)
ACTIVITY_CLASS_VERSION = "activity-class-v1"

SOURCE_SAVED_SNAPSHOT = "saved_snapshot"
SOURCE_CORRECTION_SNAPSHOT = "correction_snapshot"
SOURCE_HIIT_METADATA = "hiit_metadata"
SOURCE_EXERCISE_ACTIVITY = "exercise_activity_inferred"
SOURCE_LEGACY_DEFAULT = "legacy_default_inferred"


def valid_hiit_metadata(value) -> bool:
    """有效 HIIT 元数据的最小确定性判据（与保存契约一致）。"""
    if not isinstance(value, dict):
        return False
    blocks = value.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return False
    for block in blocks:
        if not isinstance(block, dict):
            return False
        if not str(block.get("name") or "").strip():
            return False
        work = block.get("work_seconds")
        rounds = block.get("rounds")
        if not isinstance(work, int) or isinstance(work, bool) or work <= 0:
            return False
        if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds <= 0:
            return False
    return True


def _snapshot_category(set_log: dict | None) -> tuple[str | None, str | None]:
    if not isinstance(set_log, dict):
        return None, None
    category = set_log.get("activity_class")
    if category not in ACTIVITY_CLASSES:
        return None, None
    if set_log.get("activity_class_version") != ACTIVITY_CLASS_VERSION:
        return None, None
    source = str(set_log.get("activity_class_source") or "record_snapshot")
    return category, source


def classify_training_record(exercise_doc: dict | None,
                             set_log: dict | None) -> dict:
    """返回 {class, source, version, hiit}。

    优先有效 HIIT 元数据；其次有效类别快照；再次动作库 activity；
    最后保持旧记录默认 strength。`hiit` 表示该组是否携带有效间歇元数据。
    """
    hiit_valid = valid_hiit_metadata((set_log or {}).get("hiit")) \
        if isinstance(set_log, dict) else False
    snapshot, snapshot_source = _snapshot_category(set_log)
    if hiit_valid:
        return {
            "class": CLASS_INTERVAL,
            "source": snapshot_source if snapshot == CLASS_INTERVAL
                      else SOURCE_HIIT_METADATA,
            "version": ACTIVITY_CLASS_VERSION,
            "hiit": True,
        }
    if snapshot:
        return {
            "class": snapshot, "source": snapshot_source,
            "version": ACTIVITY_CLASS_VERSION, "hiit": False,
        }
    if str((exercise_doc or {}).get("activity") or "") == "cardio":
        return {
            "class": CLASS_STEADY_CARDIO,
            "source": SOURCE_EXERCISE_ACTIVITY,
            "version": ACTIVITY_CLASS_VERSION,
            "hiit": False,
        }
    return {
        "class": CLASS_STRENGTH,
        "source": SOURCE_LEGACY_DEFAULT,
        "version": ACTIVITY_CLASS_VERSION,
        "hiit": False,
    }


def classify_entry_log(db, user_id: str, exercise_entry: dict,
                       set_log: dict) -> dict:
    """按动作记录解析身份后分类（供统计模块统一复用）。"""
    from .. import exercise_service
    from .exercise_metrics import entry_identity
    ex_id = entry_identity(db, user_id, exercise_entry)
    doc = exercise_service.get_exercise(db, user_id, ex_id) if ex_id else None
    return classify_training_record(doc, set_log)


def stamp_training_data(db, user_id: str, data: dict,
                        source: str = SOURCE_SAVED_SNAPSHOT,
                        preserve_snapshot: bool = False) -> dict:
    """为训练数据的逐组记录写活动类别快照，返回分类计数。

    preserve_snapshot=True 用于历史纠错：已有有效快照保持原类别；否则按
    当前动作库与 HIIT 元数据推断并写纠错快照。原始历史行不被改写。
    """
    from .. import exercise_service
    counts = {category: 0 for category in ACTIVITY_CLASSES}
    sources: dict[str, int] = {}
    for ex in data.get("exercises") or []:
        if not isinstance(ex, dict):
            continue
        ex_id = ex.get("exercise_id")
        doc = exercise_service.get_exercise(db, user_id, ex_id) \
            if isinstance(ex_id, str) and ex_id else None
        for log in ex.get("set_logs") or []:
            if not isinstance(log, dict):
                continue
            snapshot, snapshot_source = _snapshot_category(log)
            inferred = classify_training_record(doc, clone_without_snapshot(log))
            if preserve_snapshot and snapshot and snapshot == inferred["class"]:
                # 只有重新推断与旧快照一致时才继承；HIIT 元数据/动作语义/
                # 记录类型的实质变化会使旧快照失效。
                category = snapshot
                used_source = snapshot_source or SOURCE_CORRECTION_SNAPSHOT
            else:
                category = inferred["class"]
                used_source = source
            log["activity_class"] = category
            log["activity_class_source"] = used_source
            log["activity_class_version"] = ACTIVITY_CLASS_VERSION
            counts[category] += 1
            sources[used_source] = sources.get(used_source, 0) + 1
    return {"version": ACTIVITY_CLASS_VERSION, "counts": counts,
            "sources": sources}


def classified_rows(db, user_id: str, data: dict):
    """产出 (exercise_entry, doc, set_log, classification)，不含热身。"""
    from .. import exercise_service
    from .exercise_metrics import entry_identity
    for ex in data.get("exercises") or []:
        if not isinstance(ex, dict):
            continue
        ex_id = entry_identity(db, user_id, ex)
        doc = exercise_service.get_exercise(db, user_id, ex_id) if ex_id else None
        logs = ex.get("set_logs") if isinstance(ex.get("set_logs"), list) else []
        for log in logs:
            if not isinstance(log, dict) or log.get("warmup"):
                continue
            yield ex, doc, log, classify_training_record(doc, log)


def classification_quality(rows) -> dict:
    """从分类结果生成一致的数据质量说明（来源计数/推断条数）。"""
    sources: dict[str, int] = {}
    classes: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict) and "class" in row:
            cls = row
        elif isinstance(row, dict) and "activity_class" in row:
            cls = {"class": row["activity_class"],
                   "source": row.get("activity_class_source")
                             or SOURCE_LEGACY_DEFAULT}
        else:
            cls = row[-1]
        sources[cls["source"]] = sources.get(cls["source"], 0) + 1
        classes[cls["class"]] = classes.get(cls["class"], 0) + 1
    inferred = sum(n for source, n in sources.items() if source.endswith("_inferred"))
    return {
        "version": ACTIVITY_CLASS_VERSION,
        "sources": dict(sorted(sources.items())),
        "classes": dict(sorted(classes.items())),
        "inferred_records": inferred,
    }


def clone_without_snapshot(set_log: dict) -> dict:
    """测试/审计辅助：查看旧记录解析结果，不改写原记录。"""
    out = copy.deepcopy(set_log)
    for key in ("activity_class", "activity_class_source",
                "activity_class_version"):
        out.pop(key, None)
    return out
