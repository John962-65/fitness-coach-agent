"""2.0 B1 TrainingApproach 域模型回归（TASKBOOK_2.0 §二验收）"""
import pytest

from coach.approach import (CHOICE_STATUS, STRUCTURES, approach_to_text,
                            approach_view, apply_approach_operation,
                            empty_approach, initialize_approach, restore_revision)
from coach.db import Database
from coach.plan import generate_plan
from test_repair_regressions import profile


def make_db(tmp_path, uid="ap", with_plan=True) -> Database:
    db = Database(tmp_path / "test.db")
    p = profile()
    db.save_profile(uid, p)
    if with_plan:
        db.create_plan(uid, generate_plan(p))
    return db


def test_initialize_from_existing_plan_is_deterministic(tmp_path):
    db = make_db(tmp_path)
    doc, created = initialize_approach(db, "ap")
    assert created and doc["revision"] == 1
    # profile()：4 年训练年限无三大项 → advanced → 周期化三分化模板
    assert doc["structure"]["value"] == "ppl"
    assert doc["intensity_style"]["value"] == "periodized"
    ids = [i["exercise_id"] for i in doc["exercise_selection"]]
    assert ids and len(ids) == len(set(ids))          # 去重
    assert all(i["status"] == "active" for i in doc["exercise_selection"])
    rev = db.get_approach_revision("ap", 1)
    assert rev["initiator"] == "system_migration"
    assert rev["affected_plan_version"] == 1


def test_initialize_is_idempotent(tmp_path):
    db = make_db(tmp_path)
    initialize_approach(db, "ap")
    doc2, created2 = initialize_approach(db, "ap")
    assert not created2 and doc2["revision"] == 1
    assert db.list_approach_revisions("ap") and len(db.list_approach_revisions("ap")) == 1


def test_initialize_without_plan_yields_empty_selection(tmp_path):
    db = make_db(tmp_path, with_plan=False)
    doc, created = initialize_approach(db, "ap")
    assert created
    assert doc["exercise_selection"] == []
    assert doc["structure"]["value"] == "custom"


def test_dimension_edits_are_independent(tmp_path):
    """改一个动作选择不动结构等其他维度（2.0 §2.1）。"""
    db = make_db(tmp_path)
    doc, _ = initialize_approach(db, "ap")
    apply_approach_operation(doc, {
        "op": "upsert_exercise_choice", "exercise_id": "plank", "set": {
            "role": "accessory", "note": "核心稳定"}})
    assert any(i["exercise_id"] == "plank" for i in doc["exercise_selection"])
    assert doc["structure"]["value"] == "ppl"          # 其他维度未动
    apply_approach_operation(doc, {"op": "set_dimension", "dimension": "structure",
                                   "value": {"value": "upper_lower", "note": "时间紧"}})
    assert doc["structure"]["value"] == "upper_lower"
    assert any(i["exercise_id"] == "plank" for i in doc["exercise_selection"])


def test_remove_and_upsert_update_existing_entry(tmp_path):
    db = make_db(tmp_path)
    doc, _ = initialize_approach(db, "ap")
    first_id = doc["exercise_selection"][0]["exercise_id"]
    apply_approach_operation(doc, {"op": "upsert_exercise_choice",
                                   "exercise_id": first_id,
                                   "set": {"status": "trialing"}})
    entry = next(i for i in doc["exercise_selection"] if i["exercise_id"] == first_id)
    assert entry["status"] == "trialing" and entry["role"]            # 旧字段保留
    diff = apply_approach_operation(doc, {"op": "remove_exercise_choice",
                                          "exercise_id": first_id})
    assert diff["old"] and diff["new"] is None
    assert all(i["exercise_id"] != first_id for i in doc["exercise_selection"])


def test_execution_choices_upsert_merges(tmp_path):
    doc = empty_approach()
    apply_approach_operation(doc, {"op": "upsert_execution_choice",
                                   "exercise_id": "barbell_back_squat",
                                   "choices": {"tempo": "3-1-1"}, "note": "控制离心"})
    apply_approach_operation(doc, {"op": "upsert_execution_choice",
                                   "exercise_id": "深蹲",
                                   "choices": {"stance": "与肩同宽"}})
    entry = next(i for i in doc["execution_choices"]
                 if i["exercise_id"] == "barbell_back_squat")
    assert entry["choices"] == {"tempo": "3-1-1", "stance": "与肩同宽"}   # 归一并合并
    assert entry["note"] == "控制离心"


@pytest.mark.parametrize("op,error_kw", [
    ({"op": "set_dimension", "dimension": "exercise_selection", "value": {}}, "条目级"),
    ({"op": "set_dimension", "dimension": "structure", "value": {"value": "hiit"}}, "structure.value"),
    ({"op": "upsert_exercise_choice", "exercise_id": "不存在的动作", "set": {}}, "不在库内"),
    ({"op": "upsert_exercise_choice", "exercise_id": "plank", "set": {"status": "x"}}, "status"),
    ({"op": "remove_exercise_choice", "exercise_id": "plank"}, "没有动作"),
    ({"op": "noop"}, "未知训练方式操作"),
])
def test_invalid_operations_rejected(op, error_kw):
    doc = empty_approach()
    with pytest.raises(ValueError, match=error_kw):
        apply_approach_operation(doc, op)


def test_restore_revision_keeps_history(tmp_path):
    db = make_db(tmp_path)
    doc, _ = initialize_approach(db, "ap")
    doc2 = dict(doc)
    apply_approach_operation(doc2, {"op": "set_dimension", "dimension": "structure",
                                    "value": {"value": "full_body"}})
    doc2["revision"] = 2
    db.save_approach("ap", doc2)
    db.add_approach_revision("ap", 2, doc2, diff=[{"field": "structure"}],
                             initiator="user", reason="改全身")
    restored = restore_revision(db, "ap", 1)
    assert restored["revision"] == 3
    assert restored["structure"]["value"] == "ppl"     # v1 内容
    revs = [r["revision"] for r in db.list_approach_revisions("ap")]
    assert revs == [3, 2, 1]                           # 历史全保留
    with pytest.raises(ValueError, match="一致"):
        restore_revision(db, "ap", 3)                  # 与当前一致 → 拒绝


def test_view_assembles_referenced_dimensions(tmp_path):
    """引用维度（目标/条件/尝试/计划）从现有数据拼装，不落 approach 表。"""
    db = make_db(tmp_path)
    initialize_approach(db, "ap")
    db.start_personal_trial("ap", "改上下肢分化", "想试", "恢复情况", "疼痛即停", review_days=7)
    view = approach_view(db, "ap")
    assert view["initialized"]
    assert view["referenced"]["goal"]["primary"] == "muscle_gain"
    assert view["referenced"]["active_plan"]["version"] == 1
    assert view["referenced"]["active_trial"]["change_desc"] == "改上下肢分化"
    assert not any("goal" in k for k in view["approach"])   # approach 文档无目标副本
    empty_view = approach_view(db, "nobody")
    assert empty_view == {"initialized": False}


def test_text_rendering_smoke(tmp_path):
    db = make_db(tmp_path)
    doc, _ = initialize_approach(db, "ap")
    text = approach_to_text(doc)
    assert "推拉腿分化" in text and "周期化" in text
    assert approach_to_text(None) == "（尚未初始化训练方式）"


def test_enums_stable():
    assert STRUCTURES == ("full_body", "upper_lower", "ppl", "circuit", "custom")
    assert CHOICE_STATUS == ("active", "trialing", "stopped", "to_review")
