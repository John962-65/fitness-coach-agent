"""2.0 B3：计划手动编辑操作（DESIGN_2.0 §4.1、M1 计划编辑器的后端部分）

操作作用于计划内容 dict（深拷贝后按序应用，任一失败整体作废——由
统一修改协议 changes.py 保证先校验后提交）。本模块只管形状/存在性/
动作库成员校验；安全校验（隔离/医疗/伤病关节）在协议层，不在这里。

编辑产生的新版本保留未涉及部分原样（处方重量、卸载状态、既有披露备注）。
"""
from __future__ import annotations

import copy

from .exercises import library
from .programming import estimate_minutes

DRAFT_NOTE_PREFIX = "ℹ️ 以下动作的结构化属性"

PLAN_OPS = ("add_exercise", "remove_exercise", "replace_exercise",
            "reorder_exercise", "edit_set_prescription", "rename_day")


def _find_day(plan: dict, day_name: str) -> dict:
    for day in plan.get("schedule", []):
        if day.get("day") == day_name:
            return day
    days = "、".join(d.get("day", "?") for d in plan.get("schedule", []))
    raise ValueError(f"计划里没有训练日「{day_name}」（现有：{days}）")


def _resolve_exercise(name_or_id: str) -> tuple[str, str]:
    """动作名或 id → (id, 官方名)。只接受 id / 官方名 / 精确别名。

    计划编辑是结构化操作，不做子串/模糊归一——"量子波动深蹲"会被
    打卡侧宽松归一成深蹲，但加进计划必须精确对上（库外一律拒绝）。
    """
    text = str(name_or_id or "").strip()
    if not text:
        raise ValueError("动作名不能为空")
    ex = library.get(text)
    if ex:
        return text, ex["name"]
    ex_id, official, via = library.normalize(text)
    if ex_id and via == "exact":
        return ex_id, official
    hint = f"（最接近的官方名：{official}）" if ex_id else ""
    raise ValueError(f"动作「{text}」无法精确对上动作库{hint}；"
                     "请使用官方动作名或别名，库外动作不能加入计划")


def _entry(ex_id: str, official: str, op: dict) -> dict:
    entry = {"exercise_id": ex_id, "name": official,
             "role": op.get("role") or "secondary",
             "sets": op.get("sets"), "reps": op.get("reps")}
    if op.get("weight_kg") is not None:
        entry["weight_kg"] = op["weight_kg"]
    if op.get("note"):
        entry["note"] = op["note"]
    return entry


def _locate(day: dict, op: dict) -> int:
    """按 index 或动作名定位条目，返回下标。"""
    exercises = day["exercises"]
    if op.get("index") is not None:
        idx = op["index"]
        if not isinstance(idx, int) or not 0 <= idx < len(exercises):
            raise ValueError(f"index={idx!r} 超出「{day['day']}」的动作范围（0-{len(exercises) - 1}）")
        return idx
    target = str(op.get("exercise", "")).strip()
    if not target:
        raise ValueError("需要 index 或 exercise 之一来定位动作")
    ex_id, _official = _resolve_exercise(target)
    for i, entry in enumerate(exercises):
        if entry.get("exercise_id") == ex_id or entry.get("name") == target:
            return i
    raise ValueError(f"「{day['day']}」里没有动作「{target}」")


def _refresh_draft_note(plan: dict) -> None:
    """draft 动作披露备注与计划内容保持一致：新增 draft 会出现在披露里，
    移除后披露消失。既有其他 notes 原样保留。"""
    notes = [n for n in plan.get("notes", []) if not str(n).startswith(DRAFT_NOTE_PREFIX)]
    draft_names = []
    for day in plan.get("schedule", []):
        for entry in day.get("exercises", []):
            ex = library.get(entry.get("exercise_id", "")) or {}
            if ex.get("status") != "approved" and ex.get("name") not in draft_names:
                draft_names.append(ex.get("name") or entry.get("name", "?"))
    if draft_names:
        notes.append(
            "ℹ️ 以下动作的结构化属性（关节压力/替代关系）尚未经审核，"
            "伤病筛选未依赖其数据：" + "、".join(draft_names))
    plan["notes"] = notes


def apply_plan_operations(plan: dict, operations: list[dict]) -> tuple[dict, list[str]]:
    """按序应用操作，返回 (新计划, 逐操作说明)。调用方传入的 plan 不被修改。"""
    new_plan = copy.deepcopy(plan)
    applied: list[str] = []
    touched_days: set[str] = set()

    for op in operations or []:
        kind = op.get("op")
        if kind not in PLAN_OPS:
            raise ValueError(f"未知计划操作 {kind!r}，须为 {PLAN_OPS} 之一")

        if kind == "rename_day":
            day = _find_day(new_plan, op.get("day", ""))
            new_name = str(op.get("new_name", "")).strip()
            if not new_name:
                raise ValueError("new_name 不能为空")
            if any(d.get("day") == new_name for d in new_plan["schedule"]):
                raise ValueError(f"训练日「{new_name}」已存在")
            applied.append(f"{day['day']} 改名为 {new_name}")
            day["day"] = new_name
            continue

        day = _find_day(new_plan, op.get("day", ""))
        touched_days.add(day["day"])

        if kind == "add_exercise":
            if op.get("sets") is None or op.get("reps") is None:
                raise ValueError("add_exercise 需要 sets 与 reps")
            ex_id, official = _resolve_exercise(op.get("exercise", ""))
            entry = _entry(ex_id, official, op)
            index = op.get("index")
            if index is None or not 0 <= index <= len(day["exercises"]):
                day["exercises"].append(entry)
            else:
                day["exercises"].insert(index, entry)
            applied.append(f"{day['day']} 新增 {official}")

        elif kind == "remove_exercise":
            idx = _locate(day, op)
            removed = day["exercises"].pop(idx)
            applied.append(f"{day['day']} 移除 {removed.get('name')}")

        elif kind == "replace_exercise":
            idx = _locate(day, op)
            old = day["exercises"][idx]
            ex_id, official = _resolve_exercise(op.get("exercise", ""))
            entry = _entry(ex_id, official, {**op, "role": op.get("role") or old.get("role"),
                                             "sets": op.get("sets", old.get("sets")),
                                             "reps": op.get("reps", old.get("reps"))})
            if old.get("weight_kg") is not None and op.get("weight_kg") is None \
                    and ex_id == old.get("exercise_id"):
                entry["weight_kg"] = old["weight_kg"]
            day["exercises"][idx] = entry
            applied.append(f"{day['day']}：{old.get('name')} 替换为 {official}")

        elif kind == "reorder_exercise":
            src, dst = op.get("from"), op.get("to")
            n = len(day["exercises"])
            if not (isinstance(src, int) and isinstance(dst, int)
                    and 0 <= src < n and 0 <= dst < n):
                raise ValueError(f"from/to 必须是 0-{n - 1} 的下标")
            entry = day["exercises"].pop(src)
            day["exercises"].insert(dst, entry)
            applied.append(f"{day['day']}：{entry.get('name')} 从第 {src + 1} 位移到第 {dst + 1} 位")

        elif kind == "edit_set_prescription":
            idx = _locate(day, op)
            entry = day["exercises"][idx]
            changes = []
            for field in ("sets", "reps", "weight_kg", "note"):
                if field in op and op[field] is not None:
                    old = entry.get(field)
                    entry[field] = op[field]
                    changes.append(f"{field} {old}→{op[field]}")
            if not changes:
                raise ValueError("edit_set_prescription 至少要改一个字段（sets/reps/weight_kg/note）")
            applied.append(f"{day['day']} {entry.get('name')}：{'，'.join(changes)}")

    for day_name in touched_days:
        day = _find_day(new_plan, day_name)
        day["estimated_minutes"] = estimate_minutes(day["exercises"])
    _refresh_draft_note(new_plan)
    return new_plan, applied
