"""卡片运行时接入测试：20 张已批卡进入教练工具链（任务书 §12 第四层）。"""
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))

from coach.agent import CoachAgent
from coach.cards import (CardError, USE_PRESCRIBE, approval_valid, card_for_exercise,
                         card_for_topic, check_use_permission, load_cards, serve_card)


def test_card_for_exercise_returns_approved():
    c = card_for_exercise("barbell_back_squat")
    assert c and c["card_id"] == "card-action-barbell_back_squat"
    assert approval_valid(c, c["review"])
    # 无卡动作返回 None（面拉有 claims 但没建卡）
    assert card_for_exercise("face_pull") is None


def test_card_for_topic_routing():
    assert card_for_topic("蛋白质吃多少才对")["card_id"] == "card-nutrition-protein-basics"
    assert card_for_topic("最近睡眠不好")["card_id"] == "card-nutrition-sleep-recovery"
    assert card_for_topic("重量怎么加重卡住了")["card_id"] == "card-training-progression"
    assert card_for_topic("今天天气不错") is None


def test_serve_card_contains_provenance_and_limits():
    c = card_for_exercise("barbell_back_squat")
    out = serve_card(c)
    assert "【已审核教练卡 card-action-barbell_back_squat v1】" in out
    assert "骨盆" in out            # 正文片段
    assert "（限制：" in out
    assert "https://www.bilibili.com/video/" in out  # 出处可回溯


def test_reference_only_card_cannot_serve_prescription():
    c = dict(load_cards()["card-nutrition-energy-basics"])
    ref = dict(c, purpose="reference_only")
    check_use_permission(ref, "explain")  # 解释用途放行
    try:
        check_use_permission(ref, USE_PRESCRIBE)
        raise AssertionError("reference_only 卡不应能用于处方/健康判断")
    except CardError:
        pass


def test_agent_serves_card_first_for_squat():
    agent = CoachAgent(user_id="card_rt_t", db_path=Path(tempfile.mkdtemp()) / "t.db")
    result = agent._handle_tool(
        {"name": "get_exercise_coaching",
         "arguments": json.dumps({"exercise": "深蹲"})}, "normal")
    assert "【已审核教练卡 card-action-barbell_back_squat v1】" in result
    assert "骨盆" in result
    assert "https://www.bilibili.com/video/BV1iQ4y1e7YL" in result  # 出处留痕


def test_agent_falls_back_without_card():
    agent = CoachAgent(user_id="card_rt_f", db_path=Path(tempfile.mkdtemp()) / "t.db")
    result = agent._handle_tool(
        {"name": "get_exercise_coaching",
         "arguments": json.dumps({"exercise": "面拉"})}, "normal")
    assert "已审核教练卡" not in result  # 无卡动作保持原行为


def test_agent_topic_card_tool():
    agent = CoachAgent(user_id="card_rt_p", db_path=Path(tempfile.mkdtemp()) / "t.db")
    result = agent._handle_tool(
        {"name": "get_coaching_card",
         "arguments": json.dumps({"topic": "蛋白质吃多少"})}, "normal")
    assert "card-nutrition-protein-basics v3" in result
    assert "新手vs老手" in result and "ISSN" in result  # 分歧并列呈现（含裁决口径）
    miss = agent._handle_tool(
        {"name": "get_coaching_card",
         "arguments": json.dumps({"topic": "今天天气"})}, "normal")
    assert "暂无覆盖该主题的已审核教练卡" in miss
