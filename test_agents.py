"""M2 多智能体教练回归（DESIGN_2.0 §五/§十三验收）：

- 简单问题只调用必要智能体（确定性路由，零 LLM 参与）；
- 结构化 AgentAdvice（非法输出降级为空建议，不当结构化用）；
- 专家分歧并列保留，不裁决；
- 专业 Agent 不直接写用户数据：修改只经统一协议 pending → 用户确认；
- CoachAgent 对话链路接通（consult/propose/confirm 工具，跨轮强制）。
"""
import json

import pytest

from coach.agents import (ADVICE_FIELDS, SPECIALISTS, parse_advice,
                          route_question)
from coach.agents.orchestrator import combine, consult_specialists
from coach.approach import initialize_approach
from coach.db import Database
from coach.llm import LLMClient
from coach.plan import generate_plan
from test_repair_regressions import chat_tools, make_agent


# ---- 确定性路由 ----

@pytest.mark.parametrize("question,expected", [
    ("你好", []),
    ("谢谢教练", []),
    ("今天练完了", []),                                   # 汇报类不走专家
    ("蛋白粉怎么选", ["nutrition"]),
    ("最近总是睡不好，影响恢复吗", ["recovery"]),
    ("深蹲时膝盖内扣怎么办", ["movement"]),
    ("帮我看看现在的训练计划合理吗", ["training_science"]),
    ("博主们对空腹有氧说法不一", ["nutrition", "knowledge"]),
    ("疲劳堆积的话计划容量和饮食怎么调",
     ["training_science", "nutrition", "recovery"]),
])
def test_route_question(question, expected):
    assert route_question(question) == expected


def test_route_is_ordered_and_covers_all_specialists():
    assert set(SPECIALISTS) == {"training_science", "nutrition", "recovery",
                                "movement", "knowledge"}
    routed = route_question("营养 恢复 动作 计划 知识")
    assert routed == [k for k in SPECIALISTS
                      if k in {"nutrition", "recovery", "movement",
                               "training_science", "knowledge"}]


# ---- 结构化建议 ----

def test_parse_advice_accepts_valid_json():
    raw = json.dumps({
        "problem": "容量安排", "facts": ["每周3练"],
        "knowledge_basis": ["周期化原则"],
        "options": [{"title": "加一组", "detail": "主项 4→5 组"}],
        "conditions": ["无伤病"], "risks": ["恢复不足"],
        "needs_confirmation": ["确认后执行"]}, ensure_ascii=False)
    advice = parse_advice(raw, "training_science")
    assert advice["problem"] == "容量安排"
    assert advice["options"][0]["title"] == "加一组"
    assert all(f in advice for f in ADVICE_FIELDS)


def test_parse_advice_degrades_bad_output():
    assert parse_advice("这不是 JSON", "nutrition")["options"] == []
    assert parse_advice('{"problem": 123}', "nutrition")["problem"] == ""
    assert parse_advice('{"facts": "不是列表"}', "nutrition")["facts"] == []
    assert parse_advice('{"options": [{"no_title": 1}, "x"]}', "nutrition")["options"] == []


# ---- 咨询（FAKE LLM，确定性）----

def make_db(tmp_path, uid="ag"):
    db = Database(tmp_path / "test.db")
    from test_repair_regressions import profile
    db.save_profile(uid, profile())
    db.create_plan(uid, generate_plan(profile()))
    initialize_approach(db, uid)
    return db


def test_consult_specialists_records_and_combines(tmp_path):
    db = make_db(tmp_path)
    llm = LLMClient()  # FAKE（conftest 固定）
    result = consult_specialists(db, llm, "ag", "蛋白粉怎么选，最近还睡不好")
    assert result["consulted"] == ["nutrition", "recovery"]     # 只调必要的
    for key in result["consulted"]:
        advice = next(a for a in result["advices"] if a["specialist"] == key)
        assert advice["options"] and advice["knowledge_basis"]
    assert result["conflicts"]                                  # 双方都有方案 → 并列提示
    assert "不自动裁决" in result["conflicts"][0]
    rows = db.list_consultations("ag")
    assert rows and rows[0]["specialists"] == ["nutrition", "recovery"]


def test_consult_simple_question_calls_no_one(tmp_path):
    db = make_db(tmp_path)
    result = consult_specialists(db, LLMClient(), "ag", "你好")
    assert result["consulted"] == [] and result["advices"] == []
    assert db.list_consultations("ag") == []                    # 零咨询零留痕


def test_combine_keeps_conflicts_side_by_side():
    advices = [
        {"specialist": "training_science", "label": "训练科学",
         "options": [{"title": "a"}]},
        {"specialist": "nutrition", "label": "营养",
         "options": [{"title": "b"}]},
    ]
    out = combine(advices)
    assert len(out["advices"]) == 2 and out["conflicts"]
    single = combine([advices[0]])
    assert single["conflicts"] == []


# ---- CoachAgent 链路（FAKE + 固定工具脚本）----

def test_chat_consults_specialists_for_professional_question(tmp_path):
    a = make_agent(tmp_path, uid="ag")
    reply = a.chat("蛋白粉怎么选")          # FAKE：关键词命中 → consult 工具
    rows = a.db.list_consultations("ag")
    assert rows and rows[0]["specialists"] == ["nutrition"]
    assert "已咨询专家" in reply and "营养" in reply


def test_chat_propose_and_confirm_flow(tmp_path):
    """审查点名断链的补通：对话提案 → pending → 下一轮确认 → 生效。"""
    a = make_agent(tmp_path, uid="ag")
    initialize_approach(a.db, "ag")
    a._refresh_system_prompt()
    reply = a.chat("帮我改成上下肢分化")
    pending = [p for p in a.db.list_proposals("ag", status="pending")]
    assert pending and pending[0]["target"] == "approach"
    assert a.db.get_approach("ag")["revision"] == 1            # 未生效
    # 同轮没有确认工具调用；下一轮用户明确同意 → confirm 工具执行
    pid = pending[0]["id"]
    chat_tools(a, "同意，就改成上下肢",
               ("confirm_proposal", {"proposal_id": pid}))
    assert a.db.get_approach("ag")["revision"] == 2
    assert a.db.get_approach("ag")["structure"]["value"] == "upper_lower"
    assert a.db.get_proposal("ag", pid)["status"] == "applied"


def test_same_turn_propose_and_confirm_rejected(tmp_path):
    a = make_agent(tmp_path, uid="ag")
    initialize_approach(a.db, "ag")
    a._refresh_system_prompt()
    chat_tools(a, "改成上下肢",
               ("propose_change", {"target": "approach",
                                   "operations": [{"op": "set_dimension",
                                                   "dimension": "structure",
                                                   "value": {"value": "upper_lower"}}],
                                   "reason": "测试"}),
               ("confirm_proposal", lambda a: {
                   "proposal_id": a.db.list_proposals("ag", status="pending")[0]["id"]}))
    pid = a.db.list_proposals("ag", status="pending")[0]["id"]
    assert a.db.get_proposal("ag", pid)["status"] == "pending"  # 同轮自批被跨轮检查拒绝


def test_confirm_with_unclear_reply_stays_pending(tmp_path):
    a = make_agent(tmp_path, uid="ag")
    initialize_approach(a.db, "ag")
    a._refresh_system_prompt()
    chat_tools(a, "改成上下肢",
               ("propose_change", {"target": "approach",
                                   "operations": [{"op": "set_dimension",
                                                   "dimension": "structure",
                                                   "value": {"value": "ppl"}}],
                                   "reason": "测试"}))
    pid = a.db.list_proposals("ag", status="pending")[0]["id"]
    chat_tools(a, "我再想想", ("confirm_proposal", {"proposal_id": pid}))
    assert a.db.get_proposal("ag", pid)["status"] == "pending"
    assert a.db.get_approach("ag")["revision"] == 1


def test_propose_invalid_operations_reports_error(tmp_path):
    a = make_agent(tmp_path, uid="ag")
    initialize_approach(a.db, "ag")
    a._refresh_system_prompt()
    chat_tools(a, "随便改点啥",
               ("propose_change", {"target": "approach",
                                   "operations": [{"op": "set_dimension",
                                                   "dimension": "structure",
                                                   "value": {"value": "乱来"}}],
                                   "reason": "x"}))
    assert any("提案未创建" in r for r in a._turn_tool_results)
    assert a.db.list_proposals("ag") == []
