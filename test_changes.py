"""2.0 B2 统一修改协议回归（TASKBOOK_2.0 §三验收：手动直通 / AI 确认门 /
安全拒绝 / 版本冲突 / 事务回滚）"""
import pytest

from coach.approach import initialize_approach
from coach.changes import (ProposalRejected, confirm_proposal, stage_ai,
                           submit_manual, validate_change)
from coach.db import Database
from coach.plan import generate_plan
from test_repair_regressions import profile


def make_db(tmp_path, uid="chg") -> Database:
    db = Database(tmp_path / "test.db")
    p = profile()
    db.save_profile(uid, p)
    db.create_plan(uid, generate_plan(p))
    initialize_approach(db, uid)
    return db


def plan_base(db, uid="chg") -> dict:
    rec = db.get_active_plan_record(uid)
    return {"plan_id": rec["id"], "plan_version": rec["version"]}


def approach_base(db, uid="chg") -> dict:
    return {"approach_revision": db.get_approach(uid)["revision"]}


# ---- 手动路径：校验通过即生效 ----

def test_manual_approach_change_creates_revision(tmp_path):
    db = make_db(tmp_path)
    result = submit_manual(db, "chg", "approach",
                           [{"op": "set_dimension", "dimension": "structure",
                             "value": {"value": "upper_lower", "note": "时间紧"}}],
                           "想改成上下肢", approach_base(db))
    assert result["status"] == "applied" and result["approach_revision"] == 2
    assert db.get_approach("chg")["structure"]["value"] == "upper_lower"
    rev = db.get_approach_revision("chg", 2)
    assert rev["initiator"] == "user" and rev["confirmed"] == 1
    assert rev["diff"][0]["field"] == "structure"
    proposal = db.list_proposals("chg")[0]
    assert proposal["source"] == "user_manual" and proposal["status"] == "applied"


def test_manual_plan_edit_creates_new_version(tmp_path):
    db = make_db(tmp_path)
    day = db.get_active_plan("chg")["schedule"][0]["day"]
    old = db.get_active_plan_record("chg")
    result = submit_manual(db, "chg", "plan",
                           [{"op": "add_exercise", "day": day, "exercise": "plank",
                             "sets": 3, "reps": "30秒"}],
                           "加核心", plan_base(db))
    assert result["plan_version"] == old["version"] + 1
    new = db.get_active_plan_record("chg")
    assert new["id"] != old["id"]
    assert new["content"]["adjust_action"] == "manual_edit"
    assert any(e["exercise_id"] == "plank"
               for e in new["content"]["schedule"][0]["exercises"])
    # 计划版本与训练方式版本关联（2.0 §十一 约束 2）
    assert new["content"]["approach_revision"] == 1


def test_manual_edit_clears_stale_pending_adjustments(tmp_path):
    db = make_db(tmp_path)
    p = db.get_existing_profile("chg")
    p["pending_adjustments"] = [{"id": "adj-x", "action": "increase_weight"}]
    db.save_profile("chg", p)
    day = db.get_active_plan("chg")["schedule"][0]["day"]
    submit_manual(db, "chg", "plan",
                  [{"op": "edit_set_prescription", "day": day, "index": 0,
                    "sets": 4}], "改组数", plan_base(db))
    assert db.get_existing_profile("chg")["pending_adjustments"] == []


# ---- 校验拒绝：结构 / 版本 / 安全 ----

def test_stale_base_version_rejected(tmp_path):
    db = make_db(tmp_path)
    with pytest.raises(ProposalRejected, match="不一致"):
        submit_manual(db, "chg", "approach",
                      [{"op": "set_dimension", "dimension": "diet_approach",
                        "value": {"strategy": "灵活饮食"}}],
                      "x", {"approach_revision": 99})
    with pytest.raises(ProposalRejected, match="不一致"):
        submit_manual(db, "chg", "plan",
                      [{"op": "rename_day", "day": "周一", "new_name": "推日"}],
                      "x", {"plan_id": 999, "plan_version": 1})


def test_fenced_plan_rejects_edits(tmp_path):
    db = make_db(tmp_path)
    p = db.get_existing_profile("chg")
    p["plan_fence"] = {"reason": "新增伤病：膝盖", "safety_flag_ids": []}
    db.save_profile("chg", p)
    with pytest.raises(ProposalRejected, match="隔离"):
        submit_manual(db, "chg", "plan",
                      [{"op": "rename_day", "day": "周一", "new_name": "推日"}],
                      "x", plan_base(db))


def test_medical_pause_rejects_plan_edits(tmp_path):
    db = make_db(tmp_path)
    p = db.get_existing_profile("chg")
    p["conditions"]["health_screen"]["clearance"] = "医生说不许运动"
    db.save_profile("chg", p)
    with pytest.raises(ProposalRejected, match="医疗许可"):
        submit_manual(db, "chg", "plan",
                      [{"op": "rename_day", "day": "周一", "new_name": "推日"}],
                      "x", plan_base(db))


def test_injured_joint_high_stress_rejected(tmp_path):
    """手动编辑也不可绕过安全约束（2.0 §1.4）：膝伤 + 深蹲(knee:3) 拒绝。"""
    db = make_db(tmp_path)
    p = db.get_existing_profile("chg")
    p["conditions"]["injuries"] = ["膝盖旧伤"]
    p["conditions"]["injuries_evidence"] = "膝盖旧伤"
    db.save_profile("chg", p)
    day = db.get_active_plan("chg")["schedule"][0]["day"]
    with pytest.raises(ProposalRejected, match="膝盖|knee"):
        submit_manual(db, "chg", "plan",
                      [{"op": "add_exercise", "day": day, "exercise": "杠铃深蹲",
                        "sets": 3, "reps": 5}],
                      "想练深蹲", plan_base(db))
    # approach 维度不受伤病限制（不是处方）
    submit_manual(db, "chg", "approach",
                  [{"op": "upsert_exercise_choice", "exercise_id": "barbell_back_squat",
                    "set": {"status": "to_review", "note": "膝伤期间不练"}}],
                  "标记待复核", approach_base(db))


def test_avoid_status_warns_but_allows(tmp_path):
    """avoid 是用户偏好，本人手动加回允许但要有警告。"""
    db = make_db(tmp_path)
    db.record_exercise_feedback("chg", "plank", status="avoid", evidence="不想练")
    day = db.get_active_plan("chg")["schedule"][0]["day"]
    result = submit_manual(db, "chg", "plan",
                           [{"op": "add_exercise", "day": day, "exercise": "plank",
                             "sets": 2, "reps": "40秒"}],
                           "再试试", plan_base(db))
    assert any("先不练" in w for w in result["warnings"])


def test_empty_and_malformed_operations_rejected(tmp_path):
    db = make_db(tmp_path)
    with pytest.raises(ProposalRejected, match="非空"):
        submit_manual(db, "chg", "approach", [], "x", approach_base(db))
    with pytest.raises(ProposalRejected, match="对象"):
        submit_manual(db, "chg", "approach", ["not-a-dict"], "x", approach_base(db))
    with pytest.raises(ProposalRejected, match="target"):
        submit_manual(db, "chg", "diet", [], "x", {})


def test_unknown_user_rejected(tmp_path):
    db = make_db(tmp_path)
    with pytest.raises(ProposalRejected, match="不存在"):
        validate_change(db, "ghost", "approach",
                        [{"op": "set_dimension", "dimension": "structure",
                          "value": {"value": "ppl"}}], {"approach_revision": 1})


# ---- AI 路径：先 pending，语义门确认 ----

def test_ai_proposal_requires_explicit_consent(tmp_path):
    db = make_db(tmp_path)
    staged = stage_ai(db, "chg", "approach",
                      [{"op": "set_dimension", "dimension": "structure",
                        "value": {"value": "full_body"}}],
                      "建议改全身", approach_base(db))
    pid = staged["proposal_id"]
    assert db.get_proposal("chg", pid)["status"] == "pending"

    unclear = confirm_proposal(db, "chg", pid, "我再想想")
    assert unclear["status"] == "pending" and unclear["decision"] == "unclear"

    rejected = confirm_proposal(db, "chg", pid, "先不改了")
    assert rejected["status"] == "rejected"
    assert db.get_approach("chg")["revision"] == 1      # 数据未动

    staged2 = stage_ai(db, "chg", "approach",
                       [{"op": "set_dimension", "dimension": "structure",
                         "value": {"value": "full_body"}}],
                       "再建议一次", approach_base(db))
    ok = confirm_proposal(db, "chg", staged2["proposal_id"], "同意，改成全身")
    assert ok["status"] == "applied" and ok["approach_revision"] == 2
    assert db.get_approach("chg")["structure"]["value"] == "full_body"
    rev = db.get_approach_revision("chg", 2)
    assert rev["initiator"] == "ai"


def test_multiple_pending_requires_id_in_message(tmp_path):
    db = make_db(tmp_path)
    p1 = stage_ai(db, "chg", "approach",
                  [{"op": "set_dimension", "dimension": "structure",
                    "value": {"value": "full_body"}}], "建议A", approach_base(db))
    p2 = stage_ai(db, "chg", "approach",
                  [{"op": "set_dimension", "dimension": "diet_approach",
                    "value": {"strategy": "灵活饮食"}}], "建议B", approach_base(db))
    with pytest.raises(ProposalRejected, match="注明"):
        confirm_proposal(db, "chg", p1["proposal_id"], "同意第一个")
    ok = confirm_proposal(db, "chg", p1["proposal_id"],
                          f"同意 {p1['proposal_id']} 这个")
    assert ok["status"] == "applied"
    # p2 的 base 已漂移（revision 1→2），确认时应判 expired
    with pytest.raises(ProposalRejected, match="不一致"):
        confirm_proposal(db, "chg", p2["proposal_id"],
                         f"同意 {p2['proposal_id']}")


def test_ai_proposal_base_drift_marks_expired(tmp_path):
    db = make_db(tmp_path)
    staged = stage_ai(db, "chg", "plan",
                      [{"op": "rename_day", "day": "周一", "new_name": "推日"}],
                      "建议", plan_base(db))
    # 计划被别人（手动）改了
    submit_manual(db, "chg", "plan",
                  [{"op": "rename_day", "day": "周一", "new_name": "推A日"}],
                  "手动先改", plan_base(db))
    with pytest.raises(ProposalRejected, match="不一致"):
        confirm_proposal(db, "chg", staged["proposal_id"],
                         f"同意 {staged['proposal_id']}")
    assert db.get_proposal("chg", staged["proposal_id"])["status"] == "expired"


# ---- 事务：应用失败不部分生效 ----

def test_apply_failure_rolls_back_and_marks_rejected(tmp_path, monkeypatch):
    db = make_db(tmp_path)
    before = db.get_approach("chg")

    def boom(*a, **k):
        raise RuntimeError("synthetic write failure")
    monkeypatch.setattr(db, "get_active_plan_record", boom)
    with pytest.raises(RuntimeError):
        submit_manual(db, "chg", "approach",
                      [{"op": "set_dimension", "dimension": "structure",
                        "value": {"value": "ppl"}}],
                      "x", approach_base(db))
    assert db.get_approach("chg") == before                      # 文档未变
    assert db.get_approach_revision("chg", 2) is None            # 无新版本
    assert db.list_proposals("chg")[0]["status"] == "rejected"   # 提案留痕


def test_plan_apply_failure_keeps_active_plan(tmp_path, monkeypatch):
    db = make_db(tmp_path)
    old = db.get_active_plan_record("chg")
    before_profile = db.get_existing_profile("chg")

    def boom(*a, **k):
        raise RuntimeError("synthetic write failure")
    monkeypatch.setattr(db, "get_approach", boom)   # 事务内写入路径上失败
    with pytest.raises(RuntimeError):
        submit_manual(db, "chg", "plan",
                      [{"op": "rename_day", "day": "周一", "new_name": "推日"}],
                      "x", plan_base(db))
    assert db.get_active_plan_record("chg") == old
    assert db.get_existing_profile("chg") == before_profile
