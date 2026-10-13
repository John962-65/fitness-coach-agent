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


# ---------- 软化收紧（2026-09-29：真急症不得被降级） ----------

def test_block_intensifier_not_negation():
    """"特别胸闷"："别"是构词成分不是否定词，不得软化"""
    hit = check_red_flags("今天训练时特别胸闷")
    assert hit and hit.mode == "block" and hit.tier == "emergency"


def test_block_time_adverb_not_negation():
    """"没多久"是时间副词，不构成否定"""
    hit = check_red_flags("练完没多久突然胸痛")
    assert hit and hit.mode == "block"


def test_block_negation_in_other_clause():
    """否定词在另一个分句，不能否定命中词"""
    hit = check_red_flags("练得很不舒服，胸闷")
    assert hit and hit.mode == "block"


def test_block_history_word_in_other_clause():
    """"之前"在上一分句，当下症状不算病史"""
    hit = check_red_flags("训练之前还好好的，现在胸口疼")
    assert hit and hit.mode == "block"


def test_block_first_person_causal_question():
    """正在发生 + 追因提问（是不是）→ 硬拦截；真发病的人往往就这样问"""
    hit = check_red_flags("我现在胸口疼，是不是心脏出问题了？")
    assert hit and hit.mode == "block"


def test_block_rhabdo_causal_question():
    hit = check_red_flags("尿是酱油色的，是不是横纹肌溶解")
    assert hit and hit.mode == "block"


def test_block_second_occurrence_not_softened():
    """遍历所有关键词的所有位置：第一处软化、第二处不软化 → 拦截"""
    hit = check_red_flags("没有胸闷，但刚才眼前发黑了")
    assert hit and hit.mode == "block"
    assert hit.keyword == "眼前发黑"


def test_block_history_then_now():
    """"以前胸闷过"软化，"今天训练时又胸闷了"不软化 → 拦截"""
    hit = check_red_flags("以前胸闷过，今天训练时又胸闷了")
    assert hit and hit.mode == "block"


def test_block_dull_chest_pain_synonym():
    """"胸口一阵闷痛"：闷痛是胸部症状同义词，必须命中（holdout 评测抓到的漏报）"""
    hit = check_red_flags("刚才练的时候胸口一阵闷痛")
    assert hit and hit.mode == "block" and hit.tier == "emergency"


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
    assert "胸闷" in note and "未硬拦截" in note


def test_soft_note_not_trivializing():
    """软化提示不得指令 LLM"往轻里说"（"不按急症处理""不要渲染恐慌"类措辞）"""
    hit = check_red_flags("我没有胸闷")
    note = soft_note(hit)
    assert "不按急症" not in note and "不要渲染恐慌" not in note


def test_response_templates():
    assert "120" in EMERGENCY_RESPONSE and "诊断" in EMERGENCY_RESPONSE
    assert "冰敷" in INJURY_RESPONSE and "诊断" in INJURY_RESPONSE


# ---- 安全记录留痕分级（2026-09-29：否定不记录；提问/病史记 noted 不跟进） ----

def _agent(uid="safety_auto"):
    import tempfile
    from pathlib import Path
    from coach.agent import CoachAgent
    return CoachAgent(user_id=uid, db_path=Path(tempfile.mkdtemp()) / "t.db")


def _flags(agent):
    return agent.db.get_profile(agent.user_id)["conditions"]["pain_flags"]


def test_block_records_open_flag():
    a = _agent()
    a.chat("我练的时候胸口痛")
    flags = _flags(a)
    assert len(flags) == 1 and flags[0]["status"] == "open"


def test_negation_records_nothing():
    """"我没有胸闷"：否定语境不留任何记录（建档问答必然出现）"""
    a = _agent()
    a.chat("没有，我没有胸闷")
    assert _flags(a) == []


def test_question_records_noted_not_open():
    """知识提问最多记一条 noted（已提醒），不进入待跟进"""
    a = _agent()
    a.chat("心悸是什么原因引起的")
    flags = _flags(a)
    assert len(flags) == 1 and flags[0]["status"] == "noted"
    # noted 不进待跟进（不影响计划注意项与登录复盘）
    from coach.profile import open_pain_flags
    assert open_pain_flags(a.db.get_profile(a.user_id)) == []


def test_history_records_noted_not_open():
    a = _agent()
    a.chat("去年肩膀刺痛过一次，后来好了")
    flags = _flags(a)
    assert len(flags) == 1 and flags[0]["status"] == "noted"


# ---- resolve_pain_flag：必须指定对应那一条，不得批量关闭 ----

def test_resolve_single_open_flag_without_index():
    a = _agent()
    a.chat("我练的时候胸口痛")
    a.db.add_message(a.user_id, "user", "胸口痛已经检查，医生说没事")
    result = a._handle_tool(
        {"name": "resolve_pain_flag", "arguments": '{"note": "胸口痛已经检查，医生说没事"}'},
        "normal")
    assert "已关闭 1 条" in result
    assert _flags(a)[0]["status"] == "resolved"


def test_resolution_requires_followup_even_without_an_active_plan():
    a = _agent()
    a.chat("我现在胸闷")
    flag = _flags(a)[0]
    assert not a.profile.get("plan_fence")

    premature = a._handle_tool({
        "name": "resolve_pain_flag",
        "arguments": '{"flag_id": "' + flag["flag_id"] + '"}',
    }, "normal")
    assert "尚无用户的后续答复" in premature
    assert _flags(a)[0]["status"] == "open"

    a.db.add_message(a.user_id, "user", "膝盖症状已经消失")
    unrelated = a._handle_tool({
        "name": "resolve_pain_flag",
        "arguments": '{"flag_id": "' + flag["flag_id"] + '"}',
    }, "normal")
    assert "未能对应到这条记录" in unrelated
    assert _flags(a)[0]["status"] == "open"

    a.db.add_message(a.user_id, "user", "胸闷已经消失")
    resolved = a._handle_tool({
        "name": "resolve_pain_flag",
        "arguments": '{"flag_id": "' + flag["flag_id"] + '"}',
    }, "normal")
    assert "已关闭 1 条" in resolved
    assert _flags(a)[0]["status"] == "resolved"


def test_resolve_multiple_flags_requires_index():
    """多条待跟进时不给 ID → 拒绝全关；解除依据必须对应具体记录。"""
    a = _agent()
    a.chat("我练的时候胸口痛")
    a.chat("硬拉时腰突然剧痛")
    assert len([f for f in _flags(a) if f["status"] == "open"]) == 2
    result = a._handle_tool(
        {"name": "resolve_pain_flag", "arguments": '{"note": "看过了"}'}, "normal")
    assert "已关闭" not in result and "哪一条" in result

    chest, back = _flags(a)
    a.db.add_message(a.user_id, "user", "腰部剧痛已经消失")
    result = a._handle_tool({
        "name": "resolve_pain_flag",
        "arguments": '{"flag_id": "' + chest["flag_id"] + '"}',
    }, "normal")
    assert "未能对应到这条记录" in result
    assert _flags(a)[0]["status"] == "open" and _flags(a)[1]["status"] == "open"

    result = a._handle_tool({
        "name": "resolve_pain_flag",
        "arguments": '{"flag_id": "' + back["flag_id"] + '"}',
    }, "normal")
    assert "已关闭 1 条" in result
    assert _flags(a)[0]["status"] == "open" and _flags(a)[1]["status"] == "resolved"

    a.db.add_message(a.user_id, "user", "胸闷已经消失")
    result = a._handle_tool({
        "name": "resolve_pain_flag",
        "arguments": '{"flag_id": "' + chest["flag_id"] + '"}',
    }, "normal")
    assert "已关闭 1 条" in result
