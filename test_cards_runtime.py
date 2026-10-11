"""卡片运行时接入测试：已批卡进入教练工具链（任务书 §12 第四层；2026-10-11 起 39 张）。"""
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))

from coach.agent import CoachAgent
from coach.cards import (CardError, USE_PRESCRIBE, approval_valid, approve_card,
                         card_for_exercise, card_for_topic,
                         check_use_permission, load_cards, serve_card)


def test_card_for_exercise_returns_approved():
    c = card_for_exercise("barbell_back_squat")
    assert c and c["card_id"] == "card-action-barbell_back_squat"
    assert approval_valid(c, c["review"])
    # 面拉卡 2026-10-09 经发起人批准，动作卡通道现在服务它
    c = card_for_exercise("face_pull")
    assert c and c["card_id"] == "card-action-face_pull"
    assert approval_valid(c, c["review"])
    # 杠铃弯举卡 2026-10-10 经发起人批准，动作卡通道现在服务它
    c = card_for_exercise("barbell_curl")
    assert c and c["card_id"] == "card-action-barbell_curl"
    assert approval_valid(c, c["review"])
    # 哑铃划船卡 2026-10-11 经发起人批准（Q16），动作卡通道现在服务它
    c = card_for_exercise("dumbbell_row")
    assert c and c["card_id"] == "card-action-dumbbell_row"
    assert approval_valid(c, c["review"])
    # 哑铃夹胸卡 2026-10-11 经发起人批准（Q20），动作卡通道现在服务它
    c = card_for_exercise("dumbbell_fly")
    assert c and c["card_id"] == "card-action-dumbbell_fly"
    assert approval_valid(c, c["review"])
    # 反飞鸟卡 2026-10-11 经发起人批准（Q22），动作卡通道现在服务它
    c = card_for_exercise("rear_delt_fly")
    assert c and c["card_id"] == "card-action-rear_delt_fly"
    assert approval_valid(c, c["review"])
    # 反向山羊挺身卡 2026-10-12 经发起人批准（Q23），动作卡通道现在服务它
    c = card_for_exercise("reverse_back_extension")
    assert c and c["card_id"] == "card-action-reverse_back_extension"
    assert approval_valid(c, c["review"])
    # 颈前深蹲卡 2026-10-12 经发起人批准（Q24），动作卡通道现在服务它
    c = card_for_exercise("front_squat")
    assert c and c["card_id"] == "card-action-front_squat"
    assert approval_valid(c, c["review"])
    # 山羊挺身（正向）卡 2026-10-12 经发起人批准（Q28）——拆分裁定的收尾，动作卡通道现在服务它
    c = card_for_exercise("back_extension")
    assert c and c["card_id"] == "card-action-back_extension"
    assert approval_valid(c, c["review"])
    # 无卡动作返回 None（平板支撑暂无卡）
    # plank 卡 2026-10-11 经发起人整批授权批准（Q30 approved_v1），动作卡通道现在服务它
    c = card_for_exercise("plank")
    assert c and c["card_id"] == "card-action-plank" and approval_valid(c, c["review"])


def test_card_for_topic_routing():
    assert card_for_topic("蛋白质吃多少才对")["card_id"] == "card-nutrition-protein-basics"
    assert card_for_topic("最近睡眠不好")["card_id"] == "card-nutrition-sleep-recovery"
    assert card_for_topic("重量怎么加重卡住了")["card_id"] == "card-training-progression"
    # 方向②主题卡 2026-10-11 经发起人批准（Q18），三卡路由生效
    assert card_for_topic("有氧强度怎么定")["card_id"] == "card-training-cardio-basics"
    assert card_for_topic("今晚要应酬喝酒")["card_id"] == "card-nutrition-alcohol"
    assert card_for_topic("肌酸怎么吃")["card_id"] == "card-nutrition-supplements"
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
             "arguments": json.dumps({"exercise": "窄距卧推"})}, "normal")
    assert "已审核教练卡" not in result  # close_grip_bench_press 尚无已审核卡（2026-10-11），保持回退原行为


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


def _reapprove(card: dict, purpose: str) -> dict:
    """合成审批：改变用途后旧指纹审批必然失效，需重新签发（仅测试用）。"""
    changed = dict(card, purpose=purpose)
    changed["review"] = approve_card(changed, by="合成审核者", note="测试夹具",
                                     at="2026-10-08T00:00:00+08:00")
    return changed


def test_exercise_channel_blocks_reference_only(monkeypatch):
    """动作卡通道会被处方上下文使用，reference_only 即使审批有效也不得进入（§12.3）。"""
    import coach.cards as cards_mod
    real = cards_mod.load_cards()
    blocked = _reapprove(real["card-action-barbell_back_squat"], "reference_only")
    monkeypatch.setattr(cards_mod, "load_cards",
                        lambda: {**real, "card-action-barbell_back_squat": blocked})
    assert approval_valid(blocked, blocked["review"])  # 审批本身有效
    assert cards_mod.card_for_exercise("barbell_back_squat") is None
    agent = CoachAgent(user_id="card_rt_ro", db_path=Path(tempfile.mkdtemp()) / "t.db")
    result = agent._handle_tool(
        {"name": "get_exercise_coaching",
         "arguments": json.dumps({"exercise": "深蹲"})}, "normal")
    assert "已审核教练卡" not in result


def test_topic_channel_still_serves_reference_only_for_explanation(monkeypatch):
    """主题通道只作解释用途，reference_only 可用（§12.3 低风险参考的独立通道）。"""
    import coach.cards as cards_mod
    real = cards_mod.load_cards()
    ref = _reapprove(real["card-nutrition-protein-basics"], "reference_only")
    monkeypatch.setattr(cards_mod, "load_cards",
                        lambda: {**real, "card-nutrition-protein-basics": ref})
    served = cards_mod.card_for_topic("蛋白质吃多少")
    assert served and served["purpose"] == "reference_only"
    assert "已审核教练卡" in serve_card(served)


def test_topic_routing_direction2_cards(monkeypatch):
    """方向②与 Q19 缺口主题卡的路由映射：用合成审批验证关键词命中，不依赖签核状态。

    关键词经排查不与既有路由碰撞（“练几次”归 goal-time、“平台期”归 progression——
    减脂停滞卡用“不掉秤/减不下去”等词，避开 progression 的“平台期”）。
    """
    import coach.cards as cards_mod
    real = cards_mod.load_cards()
    patched = dict(real)
    for cid in ("card-training-cardio-basics", "card-nutrition-alcohol",
                "card-nutrition-supplements",
                "card-training-layoff-comeback", "card-training-fat-loss-plateau"):
        patched[cid] = _reapprove(real[cid], "coaching_card")
    monkeypatch.setattr(cards_mod, "load_cards", lambda: patched)
    assert cards_mod.card_for_topic("有氧强度怎么定")["card_id"] == "card-training-cardio-basics"
    assert cards_mod.card_for_topic("今晚要应酬喝酒")["card_id"] == "card-nutrition-alcohol"
    assert cards_mod.card_for_topic("肌酸怎么吃")["card_id"] == "card-nutrition-supplements"
    assert cards_mod.card_for_topic("过年停训两周会掉肌肉吗")["card_id"] == "card-training-layoff-comeback"
    assert cards_mod.card_for_topic("两个月一直不掉秤怎么办")["card_id"] == "card-training-fat-loss-plateau"


def test_no_card_rules_by_newest():
    """口径分歧一律并列保留（发起人 2026-10-08）：此后签署或待签的卡不得再声称按发布先后取新。

    该规则不追溯：2026-10-08 之前已批准的卡片保持原样不重签；一旦因实质改动重新签核，
    就自动落入本检查（按 review.at 日期判定，不写死卡名）。
    """
    forbidden = ("本卡采用其更新后口径", "按发布先后取最新", "采用更新后口径", "取新口径")
    for card in load_cards().values():
        signed_at = str(((card.get("review") or {}).get("at") or ""))[:10]
        if signed_at and signed_at < "2026-10-08":
            continue
        blob = card.get("body", "") + card.get("limits", "") + card.get("notes", "")
        for phrase in forbidden:
            assert phrase not in blob, f"{card['card_id']} 仍在用取新口径：{phrase}"


def test_grandfathered_card_untouched_and_still_served():
    """不追溯必须真的生效：旧规则批准的卡未被改写，审批仍有效、仍在运行时服务。"""
    card = load_cards()["card-action-lat_pulldown"]
    assert card["version"] == 1 and card["status"] == "approved_v1"
    assert "采用其更新后口径" in card["limits"]      # 旧规则原文保留
    assert "review_history" not in card              # 没有被迫出新版
    assert approval_valid(card, card["review"])
    assert card_for_exercise("lat_pulldown") == card


def test_sample_card_approval_mechanism():
    """评审二轮：示例卡须真实通过 approval_valid，且内容变化使审批失效。"""
    import copy
    import json as _json
    from pathlib import Path
    from coach.cards import approval_valid
    root = Path(__file__).resolve().parent
    card = _json.loads((root / "eval" / "fixtures" / "sample_card.json").read_text())
    assert approval_valid(card, card["review"])                  # 有效卡通过
    mutated = copy.deepcopy(card)
    mutated["body"] = mutated["body"] + "\n3) 新增要点。"
    assert not approval_valid(mutated, card["review"])           # 正文变化 → 拒绝
    mutated2 = copy.deepcopy(card)
    mutated2["bindings"][0]["claim_fingerprint"] = "changed"
    assert not approval_valid(mutated2, card["review"])          # 绑定变化 → 拒绝
