"""安全模块测试：三档拦截 + 否定/提问/病史软化 + 关键词单一来源同步

设计书 17.2：S1（漏报/两份清单不同步）、S2（误报）、S4（单一档位）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from coach.safety import (_KEYWORDS, EMERGENCY_RESPONSE, INJURY_RESPONSE,
                          check_red_flags, soft_note)


def _kws(tier):
    return [k for k, _ in _KEYWORDS[tier]]


# ---------- 单一来源解析（S1） ----------

def test_md_parse_three_tiers_nonempty():
    assert _kws("emergency") and _kws("injury") and _kws("yellow")


def test_md_parse_covers_review_misses():
    """17.2 S1 点名的漏报：代码清单与 red_flags.md 不同步的词"""
    e = _kws("emergency")
    assert "胸口紧" in e and "气短" in e and "喘不过气" in e
    assert "胸口闷" in e and "胸口痛" in e
    # 横纹肌溶解急症（S1 要求补充）
    assert "酱油色" in e
    # 头晕必须在黄色档而不是没有（S1：黄色档缺失）
    assert "头晕" in _kws("yellow") and "头晕" not in e


def test_tier_isolation():
    """同一个词不应跨档重复（档位语义要清晰）"""
    all_kws = _kws("emergency") + _kws("injury") + _kws("yellow")
    assert len(all_kws) == len(set(all_kws))


# ---------- 硬拦截（block） ----------

def test_block_emergency_chest():
    hit = check_red_flags("我今天训练时胸闷")
    assert hit and hit.mode == "block" and hit.tier == "emergency"
    assert "120" in hit.response and "就医" in hit.response


def test_block_emergency_rhabdo_synonym():
    """同义词扩召回：不说'酱油色尿'也要命中"""
    hit = check_red_flags("练完腿第二天尿变成酱油色了")
    assert hit and hit.mode == "block" and hit.tier == "emergency"


def test_block_emergency_breathing_synonym():
    hit = check_red_flags("我突然喘不过气")
    assert hit and hit.mode == "block" and hit.tier == "emergency"


def test_block_injury_sharp_pain():
    hit = check_red_flags("深蹲时膝盖刺痛")
    assert hit and hit.mode == "block" and hit.tier == "injury"
    assert "冰敷" in hit.response and "就医" in hit.response
    # S4：损伤档与急症档话术不同，损伤档不提 120
    assert "120" not in hit.response


def test_block_first_person_question():
    """第一人称亲历 + 疑问语气仍然是急症，不能按知识提问软化"""
    hit = check_red_flags("我胸闷是怎么回事")
    assert hit and hit.mode == "block"


def test_block_urgent_help():
    hit = check_red_flags("训练时突然胸痛怎么办")
    assert hit and hit.mode == "block"


# ---------- 软化（soft）：否定 / 提问 / 病史（S2） ----------

def test_soft_negated():
    hit = check_red_flags("我没有胸闷")
    assert hit and hit.mode == "soft" and hit.reason == "negated"


def test_soft_negated_variant():
    hit = check_red_flags("胸口不痛，就是有点累")
    assert hit is None or hit.mode == "soft"


def test_soft_history():
    hit = check_red_flags("我以前有过胸闷，体检说没事")
    assert hit and hit.mode == "soft" and hit.reason == "history"


def test_soft_history_injury():
    hit = check_red_flags("去年膝盖刺痛过一次，后来好了")
    assert hit and hit.mode == "soft" and hit.reason == "history"


def test_soft_knowledge_question():
    hit = check_red_flags("心悸是什么原因引起的")
    assert hit and hit.mode == "soft" and hit.reason == "question"


def test_soft_hypothetical_with_first_person():
    """"我会不会胸闷"是假设性担忧不是正在发作，应软化"""
    hit = check_red_flags("我爷爷有心脏病，我会不会胸闷")
    assert hit and hit.mode == "soft" and hit.reason == "question"


def test_soft_negated_during_onboarding():
    """建档问答场景的否定句不能被拦（17.2 S2 的核心案例）"""
    hit = check_red_flags("没有，我从来没有麻木过")
    assert hit and hit.mode == "soft"


def test_yellow_always_soft():
    hit = check_red_flags("练完头晕怎么回事")
    assert hit and hit.mode == "soft" and hit.tier == "yellow"


def test_yellow_soreness():
    hit = check_red_flags("练完腿很酸痛")
    assert hit and hit.mode == "soft" and hit.tier == "yellow"


# ---------- 放行 ----------

def test_pass_normal_input():
    assert check_red_flags("深蹲80kg 5x5完成") is None


def test_pass_normal_soreness_words():
    assert check_red_flags("今天练胸，肌肉很有灼烧感") is None


# ---------- soft 提示注入 ----------

def test_soft_note_yellow_has_guidance():
    hit = check_red_flags("练完头晕")
    note = soft_note(hit)
    assert "头晕" in note and "休息" in note


def test_soft_note_soft_red():
    hit = check_red_flags("我没有胸闷")
    note = soft_note(hit)
    assert "胸闷" in note and "不按急症" in note


def test_response_templates():
    assert "120" in EMERGENCY_RESPONSE and "诊断" in EMERGENCY_RESPONSE
    assert "冰敷" in INJURY_RESPONSE and "诊断" in INJURY_RESPONSE


# ---- S3 确定性兜底：用户带回医疗"无恙"结论时自动关闭安全记录 ----

def _agent(uid="safety_auto"):
    import tempfile
    from pathlib import Path
    from coach.agent import CoachAgent
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


def test_auto_resolve_closes_flag_on_medical_clearance():
    a = _agent()
    a.chat("我练的时候胸口痛")  # block：记录 pain_flag
    assert a.db.get_profile(a.user_id)["conditions"]["pain_flags"]
    a.chat("去医院查了，心电图没事，医生说就是太累，休息好再练")
    flags = a.db.get_profile(a.user_id)["conditions"]["pain_flags"]
    assert all(f["status"] == "resolved" for f in flags)
    assert "自动关闭" in flags[0]["note"]


def test_auto_resolve_not_triggered_by_question():
    a = _agent()
    a.chat("我练的时候胸口痛")
    a.chat("要不要去医院检查？医生说没事吗")
    flags = a.db.get_profile(a.user_id)["conditions"]["pain_flags"]
    assert any(f["status"] == "open" for f in flags)


def test_auto_resolve_not_triggered_without_medical_source():
    a = _agent()
    a.chat("我练的时候胸口痛")
    a.chat("没事了，我感觉好了")
    flags = a.db.get_profile(a.user_id)["conditions"]["pain_flags"]
    assert any(f["status"] == "open" for f in flags)
