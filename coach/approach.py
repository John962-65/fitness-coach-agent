"""2.0 B1：TrainingApproach（我的训练方式）域模型（DESIGN_2.0 §二、§十一）

单一事实来源原则：目标/条件/频率/尝试等已在档案与既有表中存在的信息
不在 approach 里存副本，对外呈现时由 approach_view() 动态拼装引用维度；
approach 文档只拥有"训练方式选择"类维度，各维度独立修改（2.0 §2.1
"更换一个动作不应导致整个方式重新生成"）。

每次修改落一行 approach_revisions（完整快照 + 逐字段 diff + 发起者/原因/
确认状态/关联计划版本）；恢复历史版本以新版本落库，不回滚指针、不删历史。
"""
from __future__ import annotations

import copy
from datetime import datetime

from .exercises import library

STRUCTURES = ("full_body", "upper_lower", "ppl", "circuit", "custom")
STRUCTURE_LABEL = {"full_body": "全身", "upper_lower": "上下肢分化", "ppl": "推拉腿分化",
                   "circuit": "循环训练", "custom": "自定义"}
INTENSITY_STYLES = ("linear", "rpe_based", "periodized", "flexible")
INTENSITY_LABEL = {"linear": "线性进阶", "rpe_based": "RPE 驱动",
                   "periodized": "周期化", "flexible": "灵活进阶"}
# 每个选择的适用状态（2.0 §2.1）：当前采用 / 尝试中 / 已停止 / 待复核
CHOICE_STATUS = ("active", "trialing", "stopped", "to_review")

# 可整段设置的维度（exercise_selection / execution_choices 只能用条目级操作，
# 防止一次误操作整表覆盖）
SETTABLE_DIMENSIONS = ("structure", "intensity_style", "diet_approach",
                       "recovery_approach", "preferences")
LIST_DIMENSIONS = ("exercise_selection", "execution_choices")


def empty_approach() -> dict:
    return {
        "revision": 0,
        "structure": {"value": "custom", "note": "", "status": "active"},
        "intensity_style": {"value": "flexible", "note": "", "status": "active"},
        "exercise_selection": [],
        "execution_choices": [],
        "diet_approach": {"strategy": "", "note": "", "status": "active"},
        "recovery_approach": {"note": "", "deload_policy": ""},
        "preferences": {"liked": [], "disliked": [], "structure_notes": ""},
    }


def _status_value(value: dict, errors: list, field: str) -> None:
    status = value.get("status", "active")
    if status not in CHOICE_STATUS:
        errors.append(f"{field}.status 必须是 {CHOICE_STATUS} 之一")


def validate_dimension_value(dimension: str, value) -> list[str]:
    """整段设置一个维度前的形状校验；返回错误列表（空 = 通过）。"""
    errors: list[str] = []
    if not isinstance(value, dict):
        return [f"{dimension} 必须是对象"]
    if dimension == "structure":
        if value.get("value") not in STRUCTURES:
            errors.append(f"structure.value 必须是 {STRUCTURES} 之一")
        _status_value(value, errors, "structure")
    elif dimension == "intensity_style":
        if value.get("value") not in INTENSITY_STYLES:
            errors.append(f"intensity_style.value 必须是 {INTENSITY_STYLES} 之一")
        _status_value(value, errors, "intensity_style")
    elif dimension == "diet_approach":
        _status_value(value, errors, "diet_approach")
    elif dimension == "recovery_approach":
        pass  # 自由文本策略（note / deload_policy），无枚举
    elif dimension == "preferences":
        for key in ("liked", "disliked"):
            if key in value and not (isinstance(value[key], list)
                                     and all(isinstance(x, str) for x in value[key])):
                errors.append(f"preferences.{key} 必须是字符串列表")
    return errors


def _validated_choice(exercise_id: str, payload: dict) -> tuple[dict, list[str]]:
    """exercise_selection 条目的形状校验。"""
    errors: list[str] = []
    entry = {"exercise_id": exercise_id, "role": payload.get("role"),
             "alternatives": list(payload.get("alternatives") or []),
             "status": payload.get("status", "active"), "note": payload.get("note", "")}
    if not library.get(exercise_id):
        errors.append(f"动作 {exercise_id!r} 不在库内")
    if entry["status"] not in CHOICE_STATUS:
        errors.append(f"status 必须是 {CHOICE_STATUS} 之一")
    if entry["role"] is not None and entry["role"] not in (
            "main", "secondary", "accessory", "cardio"):
        errors.append("role 必须是 main/secondary/accessory/cardio 或空")
    for alt in entry["alternatives"]:
        if not library.get(alt):
            errors.append(f"替代动作 {alt!r} 不在库内")
    return entry, errors


def apply_approach_operation(doc: dict, op: dict) -> dict:
    """把一个类型化操作应用到 approach 文档（就地修改），返回 diff 条目。
    形状/枚举不合法时抛 ValueError——由统一协议在校验阶段先行调用，
    提交阶段不会遇到。"""
    kind = op.get("op")
    if kind == "set_dimension":
        dim = op.get("dimension", "")
        if dim not in SETTABLE_DIMENSIONS:
            raise ValueError(f"dimension {dim!r} 只能通过条目级操作修改"
                             f"（upsert/remove_exercise_choice），不能整段设置")
        errors = validate_dimension_value(dim, op.get("value"))
        if errors:
            raise ValueError("；".join(errors))
        old = copy.deepcopy(doc.get(dim))
        merged = {**(doc.get(dim) or {}), **copy.deepcopy(op["value"])}
        doc[dim] = merged
        return {"field": dim, "old": old, "new": copy.deepcopy(merged)}

    if kind == "upsert_exercise_choice":
        exercise_id, payload = op.get("exercise_id", ""), op.get("set", {})
        if not exercise_id or not isinstance(payload, dict):
            raise ValueError("upsert_exercise_choice 需要 exercise_id 与 set 对象")
        eid, _official, _via = library.normalize(exercise_id)
        eid = eid or exercise_id
        entry, errors = _validated_choice(eid, {**(payload or {})})
        if errors:
            raise ValueError("；".join(errors))
        items = doc["exercise_selection"]
        old = copy.deepcopy([i for i in items if i.get("exercise_id") == eid] or None)
        if old:
            # 局部更新：只覆盖 payload 显式给出的字段，未提及的保留旧值
            base = dict(old[0])
            for field in ("role", "status", "note", "alternatives"):
                if field in payload:
                    base[field] = entry[field]
            entry = base
        kept = [i for i in items if i.get("exercise_id") != eid]
        kept.append(entry)
        doc["exercise_selection"] = kept
        return {"field": "exercise_selection", "old": old, "new": copy.deepcopy(entry)}

    if kind == "remove_exercise_choice":
        exercise_id = op.get("exercise_id", "")
        eid, _o, _v = library.normalize(exercise_id)
        eid = eid or exercise_id
        old = copy.deepcopy([i for i in doc["exercise_selection"]
                             if i.get("exercise_id") == eid] or None)
        if not old:
            raise ValueError(f"训练方式里没有动作 {exercise_id!r}")
        doc["exercise_selection"] = [i for i in doc["exercise_selection"]
                                     if i.get("exercise_id") != eid]
        return {"field": "exercise_selection", "old": old, "new": None}

    if kind == "upsert_execution_choice":
        exercise_id, choices, note = (op.get("exercise_id", ""),
                                      op.get("choices") or {}, op.get("note", ""))
        if not exercise_id or not isinstance(choices, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in choices.items()):
            raise ValueError("upsert_execution_choice 需要 exercise_id 与字符串键值的 choices")
        eid, _o, _v = library.normalize(exercise_id)
        eid = eid or exercise_id
        if not library.get(eid):
            raise ValueError(f"动作 {eid!r} 不在库内")
        items = doc["execution_choices"]
        old = copy.deepcopy([i for i in items if i.get("exercise_id") == eid] or None)
        entry = {"exercise_id": eid, "choices": dict(choices), "note": note}
        if old:
            base = dict(old[0])
            base["choices"] = {**base.get("choices", {}), **choices}
            base["note"] = note or base.get("note", "")
            entry = base
        doc["execution_choices"] = [i for i in items if i.get("exercise_id") != eid] + [entry]
        return {"field": "execution_choices", "old": old, "new": copy.deepcopy(entry)}

    raise ValueError(f"未知训练方式操作 {kind!r}")


def apply_operations(doc: dict, operations: list[dict]) -> list[dict]:
    """按序应用操作列表，返回 diff。任一失败抛 ValueError（调用方保证先校验）。"""
    diffs = []
    for op in operations or []:
        diffs.append(apply_approach_operation(doc, op))
    return diffs


# ---- 受测迁移（2.0 §十二：不从零开始，现有数据经推导进入新模型）----

def _infer_structure(plan: dict | None) -> str:
    template = (plan or {}).get("template", "")
    if "推拉" in template or "三分化" in template:
        return "ppl"
    if "全身 A/B" in template or "全身" in template:
        return "full_body"
    if "上下肢" in template:
        return "upper_lower"
    return "custom"


def _infer_intensity(plan: dict | None) -> str:
    template = (plan or {}).get("template", "")
    if "线性进阶" in template:
        return "linear"
    if "周期" in template:
        return "periodized"
    if "RPE" in template:
        return "rpe_based"
    return "flexible"


def initialize_approach(db, user_id: str) -> tuple[dict, bool]:
    """从现有档案 + 当前生效计划推导 v1。幂等：已有 approach 原样返回。

    推导规则确定性：结构/强度风格从计划模板字符串判断，动作选择从
    schedule 提取（按动作 id 去重，保留首个角色）。医疗暂停（无 schedule）
    时动作选择为空、结构记 custom，如实反映"当前没有可执行的训练安排"。
    """
    existing = db.get_approach(user_id)
    if existing:
        return existing, False
    plan_record = db.get_active_plan_record(user_id)
    plan = plan_record["content"] if plan_record else None
    doc = empty_approach()
    doc["revision"] = 1
    doc["structure"] = {"value": _infer_structure(plan),
                        "note": "初始化自当前计划模板" if plan else "尚无计划",
                        "status": "active"}
    doc["intensity_style"] = {"value": _infer_intensity(plan),
                              "note": "初始化自当前计划模板" if plan else "",
                              "status": "active"}
    seen: set[str] = set()
    for day in (plan or {}).get("schedule", []):
        for entry in day.get("exercises", []):
            eid = entry.get("exercise_id")
            if not eid or eid in seen or not library.get(eid):
                continue
            seen.add(eid)
            doc["exercise_selection"].append({
                "exercise_id": eid, "role": entry.get("role"),
                "alternatives": [], "status": "active",
                "note": "初始化自当前计划",
            })
    db.save_approach(user_id, doc)
    db.add_approach_revision(
        user_id, 1, doc,
        diff=[{"field": "*",
               "old": None,
               "new": {"structure": doc["structure"]["value"],
                       "intensity_style": doc["intensity_style"]["value"],
                       "exercise_count": len(doc["exercise_selection"])}}],
        initiator="system_migration", reason="从现有档案与生效计划初始化（2.0 B1 受测迁移）",
        affected_plan_version=plan_record["version"] if plan_record else None)
    return doc, True


def approach_view(db, user_id: str) -> dict:
    """对外呈现 = 自有维度（落库文档）+ 引用维度（从现有数据动态拼装，不存副本）。"""
    doc = db.get_approach(user_id)
    if not doc:
        return {"initialized": False}
    profile = db.get_existing_profile(user_id) or {}
    conditions = profile.get("conditions", {}) or {}
    plan_record = db.get_active_plan_record(user_id)
    active_trial = next((t for t in db.personal_trials(user_id, limit=10)
                         if t.get("status") == "active"), None)
    open_flags = [f for f in (conditions.get("pain_flags") or [])
                  if isinstance(f, dict) and f.get("status") == "open"]
    goal = dict(profile.get("goal") or {})
    return {
        "initialized": True,
        "approach": doc,
        "referenced": {
            "goal": {k: goal.get(k) for k in
                     ("primary", "phase", "secondary", "timeline", "version", "confirmed_at")},
            "resources": dict(profile.get("resources") or {}),
            "conditions": {
                "injuries": list(conditions.get("injuries") or []),
                "plan_fence": bool(profile.get("plan_fence")),
                "open_pain_flags": len(open_flags),
            },
            "active_trial": ({k: active_trial.get(k) for k in
                              ("id", "change_desc", "observe", "review_at", "due_review")}
                             if active_trial else None),
            "active_plan": ({"id": plan_record["id"], "version": plan_record["version"],
                             "template": plan_record["content"].get("template"),
                             "approach_revision": plan_record["content"].get("approach_revision")}
                            if plan_record else None),
        },
    }


def restore_revision(db, user_id: str, revision: int, initiator: str = "user",
                     reason: str = "") -> dict:
    """恢复历史版本：以新版本落库快照内容（不删历史、不回滚指针）。"""
    snapshot = db.get_approach_revision(user_id, revision)
    if not snapshot:
        raise ValueError(f"没有版本 v{revision}")
    current = db.get_approach(user_id)
    if not current:
        raise ValueError("尚无训练方式，先初始化")
    new_doc = copy.deepcopy(snapshot["content"])
    new_rev = int(current["revision"]) + 1
    new_doc["revision"] = new_rev
    diff = []
    for key in (*SETTABLE_DIMENSIONS, *LIST_DIMENSIONS):
        if current.get(key) != new_doc.get(key):
            diff.append({"field": key, "old": copy.deepcopy(current.get(key)),
                         "new": copy.deepcopy(new_doc.get(key))})
    if not diff:
        raise ValueError(f"v{revision} 与当前版本内容一致，无需恢复")
    plan_record = db.get_active_plan_record(user_id)
    db.save_approach(user_id, new_doc)
    db.add_approach_revision(
        user_id, new_rev, new_doc, diff=diff, initiator=initiator,
        reason=reason or f"恢复 v{revision} 的训练方式",
        affected_plan_version=plan_record["version"] if plan_record else None)
    return new_doc


def approach_to_text(doc: dict) -> str:
    """训练方式的简短文本呈现（CLI 调试 / 测试可读性用）。"""
    if not doc:
        return "（尚未初始化训练方式）"
    lines = [
        f"版本：v{doc.get('revision', 0)}",
        f"结构：{STRUCTURE_LABEL.get(doc['structure']['value'], doc['structure']['value'])}"
        + (f"（{doc['structure'].get('note')}）" if doc["structure"].get("note") else ""),
        f"强度风格：{INTENSITY_LABEL.get(doc['intensity_style']['value'], '')}",
    ]
    selection = doc.get("exercise_selection") or []
    if selection:
        names = []
        for item in selection[:12]:
            ex = library.get(item["exercise_id"]) or {}
            mark = {"active": "", "trialing": "·尝试中", "stopped": "·已停止",
                    "to_review": "·待复核"}.get(item.get("status"), "")
            names.append(f"{ex.get('name', item['exercise_id'])}{mark}")
        lines.append("动作选择：" + "、".join(names)
                     + (f" 等 {len(selection)} 项" if len(selection) > 12 else ""))
    else:
        lines.append("动作选择：（空）")
    for key, label in (("diet_approach", "饮食方式"), ("recovery_approach", "恢复方式")):
        d = doc.get(key) or {}
        text = d.get("strategy") or d.get("note") or d.get("deload_policy") or ""
        if text:
            lines.append(f"{label}：{text}")
    lines.append(f"初始化时间由版本历史可查（当前 v{doc.get('revision', 0)}，"
                 f"{datetime.now().isoformat(timespec='seconds')} 呈现）")
    return "\n".join(lines)
