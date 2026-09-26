"""Phase 0 链路测试：安全拦截 → 档案加载 → 知识索引 → 工具调用 → 回复

R0 变更：改用临时库（17.2 T1）；适配新安全 API（三档 + 软化）；
新增上下文截断、输出兜底、异常降级测试（17.2 R1-R3）。
"""
import tempfile
from pathlib import Path

from coach.agent import MAX_CONTEXT_CHARS, CoachAgent, _sanitize_output
from coach.knowledge import KnowledgeBase


def _agent(uid="test"):
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


# ---- 知识库加载（含 17.2 K1） ----

def test_kb_scan_count():
    kb = KnowledgeBase()
    assert len(kb._files) >= 39, f"知识文件数异常：{len(kb._files)}"


def test_kb_video_index_not_skipped():
    """K1：文件名含 index 不应被误跳过"""
    kb = KnowledgeBase()
    assert any("tan_chengyi_video_index" in rel for rel in kb._files)


def test_kb_l1_l2_l3():
    kb = KnowledgeBase()
    assert len(kb.l1_principles) > 500
    assert "slow_cut_protocol" in kb.l2_index
    assert "慢减脂" in kb.load("30_nutrition/slow_cut_protocol.md")
    assert "渐进超负荷" in kb.load("progressive_overload.md")  # 模糊匹配


def test_kb_empty_path_errors():
    """K1：空路径报错而不是返回第一个文件"""
    kb = KnowledgeBase()
    assert "错误" in kb.load("")


# ---- Agent 安全链路 ----

def test_agent_red_flag_block_no_llm():
    agent = _agent()
    r = agent.chat("我训练时胸闷心慌")
    assert "就医" in r and "120" in r


def test_agent_red_flag_structured_record():
    agent = _agent()
    agent.chat("我训练时胸闷心慌")
    flags = agent.profile["conditions"]["pain_flags"]
    assert len(flags) == 1
    f = flags[0]
    assert f["kw"] == "胸闷" and f["tier"] == "emergency"
    assert f["mode"] == "block" and f["status"] == "open" and f["at"]


def test_agent_soft_negation_not_blocked():
    agent = _agent()
    r = agent.chat("我没有胸闷，就是问问")
    assert "请立即停止当前训练" not in r  # 不是硬拦截话术
    # soft 命中也结构化记录（待跟进）
    flags = agent.profile["conditions"]["pain_flags"]
    assert flags and flags[-1]["mode"] == "soft" and flags[-1]["kw"] == "胸闷"


def test_agent_resolve_pain_flag():
    agent = _agent()
    agent.profile["onboarding_done"] = True
    agent.chat("我训练时胸闷心慌")
    result = agent._handle_tool(
        {"name": "resolve_pain_flag", "arguments": '{"note": "去医院检查了没事"}'},
        "normal")
    assert "已关闭" in result
    flags = agent.profile["conditions"]["pain_flags"]
    assert flags[0]["status"] == "resolved" and flags[0]["note"]


def test_agent_normal_flow_uses_knowledge_tool():
    agent = _agent()
    agent.profile["onboarding_done"] = True
    r = agent.chat("我深蹲时臀部没感觉怎么办")
    assert len(r) > 0
    assert any(m.get("role") == "tool" for m in agent.messages)


# ---- R2：上下文截断 ----

def test_trim_messages_budget_and_no_orphan_tool():
    agent = _agent()
    # 塞入超预算的 tool 交换 + 普通消息
    for i in range(30):
        agent.messages.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": f"t{i}", "type": "function",
                            "function": {"name": "load_knowledge", "arguments": "{}"}}]})
        agent.messages.append(
            {"role": "tool", "tool_call_id": f"t{i}", "content": "知" * 2000})
        agent.messages.append({"role": "assistant", "content": "回" * 500})
    agent._trim_messages()
    total = sum(len(m.get("content") or "") for m in agent.messages)
    assert total <= MAX_CONTEXT_CHARS
    assert agent.messages[0]["role"] == "system"
    # 截断后 system 之后不能是孤儿 tool 消息（会导致 API 400）
    assert agent.messages[1].get("role") != "tool"


# ---- R3：输出兜底 ----

def test_sanitize_output_number_promise():
    out = _sanitize_output("坚持练，30天瘦5斤没问题！")
    assert "30天瘦5斤" not in out and "因人而异" in out


def test_sanitize_output_chinese_numeral():
    out = _sanitize_output("一个月能瘦10斤")
    assert "瘦10斤" not in out


def test_sanitize_output_normal_text_unchanged():
    text = "深蹲 80kg 做 5 组，下周加 2.5kg"
    assert _sanitize_output(text) == text


# ---- R1：异常降级 ----

def test_chat_survives_llm_exception(monkeypatch):
    agent = _agent()
    agent.profile["onboarding_done"] = True

    def boom(messages, tools=None, temperature=0.7):
        raise ConnectionError("api down")

    monkeypatch.setattr(agent.llm, "chat", boom)
    r = agent.chat("今天练得怎么样")
    assert "没接住" in r
