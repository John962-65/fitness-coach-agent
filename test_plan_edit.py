"""2.0 B3 计划手动编辑操作回归（TASKBOOK_2.0 §四：先校验后提交、
未涉及部分原样保留、draft 披露随内容刷新）"""
import pytest

from coach.exercises import library
from coach.plan_edit import apply_plan_operations
from coach.plan import generate_plan
from test_repair_regressions import profile


def make_plan() -> dict:
    return generate_plan(profile())


def first_day(plan) -> dict:
    return plan["schedule"][0]


def names(day) -> list:
    return [e["name"] for e in day["exercises"]]


def test_add_remove_roundtrip(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    new_plan, applied = apply_plan_operations(plan, [
        {"op": "add_exercise", "day": day, "exercise": "plank",
         "sets": 3, "reps": "45秒", "role": "accessory"}])
    assert "平板支撑" in names(first_day(new_plan))
    assert "新增 平板支撑" in applied[0]
    assert plan is not new_plan and "平板支撑" not in names(first_day(plan))  # 原计划不变
    back, _ = apply_plan_operations(new_plan, [
        {"op": "remove_exercise", "day": day, "exercise": "plank"}])
    assert "平板支撑" not in names(first_day(back))


def test_replace_keeps_prescription_of_same_exercise(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    plan, _ = apply_plan_operations(plan, [
        {"op": "edit_set_prescription", "day": day, "index": 0, "weight_kg": 100}])
    replaced, applied = apply_plan_operations(plan, [
        {"op": "replace_exercise", "day": day, "index": 0, "exercise": "goblet_squat"}])
    entry = first_day(replaced)["exercises"][0]
    assert entry["exercise_id"] == "goblet_squat"
    assert "weight_kg" not in entry                     # 换了动作不沿用旧重量


def test_replace_same_exercise_keeps_weight(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    plan, _ = apply_plan_operations(plan, [
        {"op": "edit_set_prescription", "day": day, "index": 0, "weight_kg": 100,
         "note": "测试"}])
    same, _ = apply_plan_operations(plan, [
        {"op": "replace_exercise", "day": day, "index": 0,
         "exercise": plan["schedule"][0]["exercises"][0]["name"],
         "sets": 5}])
    entry = same["schedule"][0]["exercises"][0]
    assert entry["weight_kg"] == 100                    # 同动作替换沿用处方重量
    assert entry["sets"] == 5


def test_reorder_and_rename(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    n = len(first_day(plan)["exercises"])
    if n >= 2:
        new_plan, applied = apply_plan_operations(plan, [
            {"op": "reorder_exercise", "day": day, "from": 0, "to": 1}])
        assert names(first_day(new_plan))[1] == names(first_day(plan))[0]
    new_plan, _ = apply_plan_operations(plan, [
        {"op": "rename_day", "day": day, "new_name": "推日"}])
    assert new_plan["schedule"][0]["day"] == "推日"
    with pytest.raises(ValueError, match="已存在"):
        apply_plan_operations(new_plan, [
            {"op": "rename_day", "day": "推日", "new_name": new_plan["schedule"][1]["day"]}])


def test_edit_set_prescription_partial(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    old_sets = first_day(plan)["exercises"][0]["sets"]
    new_plan, applied = apply_plan_operations(plan, [
        {"op": "edit_set_prescription", "day": day, "index": 0, "reps": "6-8"}])
    entry = first_day(new_plan)["exercises"][0]
    assert entry["sets"] == old_sets and entry["reps"] == "6-8"
    with pytest.raises(ValueError, match="至少"):
        apply_plan_operations(plan, [
            {"op": "edit_set_prescription", "day": day, "index": 0}])


def test_unknown_exercise_and_bad_index_rejected(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    # 子串/模糊命中不能混进结构化编辑："量子波动深蹲"包含"深蹲"但不是库内叫法
    with pytest.raises(ValueError, match="无法精确对上|不在动作库"):
        apply_plan_operations(plan, [
            {"op": "add_exercise", "day": day, "exercise": "量子波动深蹲",
             "sets": 3, "reps": 5}])
    with pytest.raises(ValueError, match="超出"):
        apply_plan_operations(plan, [
            {"op": "remove_exercise", "day": day, "index": 99}])
    with pytest.raises(ValueError, match="没有训练日"):
        apply_plan_operations(plan, [
            {"op": "add_exercise", "day": "不存在的日子", "exercise": "plank",
             "sets": 3, "reps": 5}])
    with pytest.raises(ValueError, match="未知计划操作"):
        apply_plan_operations(plan, [{"op": "explode"}])


def test_untouched_parts_preserved(tmp_path):
    """未涉及的训练日、备注、卸载状态原样保留。"""
    plan = make_plan()
    plan["deload"] = {"until": "2099-01-01", "factor": 0.5}
    plan["notes"].append("用户自定义备注")
    day = first_day(plan)["day"]
    other_day = plan["schedule"][1]
    new_plan, _ = apply_plan_operations(plan, [
        {"op": "edit_set_prescription", "day": day, "index": 0, "sets": 4}])
    assert new_plan["deload"] == plan["deload"]
    assert "用户自定义备注" in new_plan["notes"]
    assert new_plan["schedule"][1] == other_day


def test_draft_disclosure_follows_content(tmp_path):
    draft = next(e for e in library.all() if e.get("status") == "draft")
    approved = next(e for e in library.all() if e.get("status") == "approved"
                    and e.get("pattern") != draft.get("pattern"))
    plan = make_plan()
    day = first_day(plan)["day"]
    with_draft, _ = apply_plan_operations(plan, [
        {"op": "add_exercise", "day": day, "exercise": draft["name"],
         "sets": 3, "reps": 10}])
    assert any(n.startswith("ℹ️ 以下动作的结构化属性") and draft["name"] in n
               for n in with_draft["notes"])
    removed, _ = apply_plan_operations(with_draft, [
        {"op": "remove_exercise", "day": day, "exercise": draft["name"]}])
    assert not any(str(n).startswith("ℹ️ 以下动作的结构化属性")
                   for n in removed["notes"])


def test_estimated_minutes_recomputed(tmp_path):
    plan = make_plan()
    day = first_day(plan)["day"]
    before = first_day(plan)["estimated_minutes"]
    new_plan, _ = apply_plan_operations(plan, [
        {"op": "add_exercise", "day": day, "exercise": "plank",
         "sets": 3, "reps": "60秒"}])
    assert first_day(new_plan)["estimated_minutes"] > before


def test_multi_op_atomic_on_copy(tmp_path):
    """第二个操作失败 → 整体作废（返回前抛错，调用方未提交任何内容）。"""
    plan = make_plan()
    day = first_day(plan)["day"]
    orig_sets = first_day(plan)["exercises"][0]["sets"]
    with pytest.raises(ValueError, match="无法精确对上|不在动作库"):
        apply_plan_operations(plan, [
            {"op": "edit_set_prescription", "day": day, "index": 0,
             "sets": orig_sets + 3},
            {"op": "add_exercise", "day": day, "exercise": "不存在的动作",
             "sets": 3, "reps": 5}])
    assert first_day(plan)["exercises"][0]["sets"] == orig_sets  # 原计划未被碰
