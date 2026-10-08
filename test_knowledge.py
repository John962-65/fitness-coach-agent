"""R4 知识库契约测试：provenance 全覆盖 + 17.3 事实错误修复 + distill 流水线"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from coach.knowledge import NAMEABLE_PROVENANCES, KnowledgeBase
from tools.distill import (_parse_json_array, claims_to_yaml, segment_text_at,
                           validate_claim, distill)

KNOWLEDGE = ROOT / "knowledge"
VALID_PROV = {"transcript", "article", "third_party_distill", "general"}


def _all_md():
    return [p for p in KNOWLEDGE.rglob("*.md") if p.name != "CHANGELOG.md"]


# ---------- provenance 全覆盖 ----------

def test_every_file_has_valid_provenance():
    missing, invalid = [], []
    for p in _all_md():
        m = re.search(r"^provenance:\s*(\S+)", p.read_text("utf-8"), re.M)
        if not m:
            missing.append(p.name)
        elif m.group(1) not in VALID_PROV:
            invalid.append((p.name, m.group(1)))
    assert not missing, f"缺 provenance: {missing}"
    assert not invalid, f"provenance 非法: {invalid}"


def test_no_firsthand_source_yet():
    """当前没有一手 transcript/article，故没有文件可点博主名（17.3 的核心结论）"""
    kb = KnowledgeBase()
    assert kb.nameable_files == []


def test_l2_index_shows_provenance():
    kb = KnowledgeBase()
    assert "[来源:" in kb.l2_index


def test_tan_exercise_files_are_general():
    """谭成义动作文件标 general（疑似代写挂名，17.3）"""
    kb = KnowledgeBase()
    tan = [rel for rel in kb._files if rel.startswith("20_exercises/")
           and "video_index" not in rel]
    assert tan, "应有谭成义动作文件"
    for rel in tan:
        assert kb._files[rel]["meta"].get("provenance") == "general", rel


def test_chenshi_nutrition_is_third_party():
    kb = KnowledgeBase()
    cs = [rel for rel in kb._files
          if rel.startswith("30_nutrition/") and "creatine" not in rel]
    assert cs
    for rel in cs:
        assert kb._files[rel]["meta"].get("provenance") == "third_party_distill", rel


# ---------- 17.3 事实错误修复 ----------

def _read(rel):
    return (KNOWLEDGE / rel).read_text("utf-8")


def test_leptin_glp1_fixed():
    txt = _read("30_nutrition/leptin_system.md")
    assert "作用机制与 GLP-1" not in txt
    assert "不同的激素" in txt  # 已改为澄清两者不同


def test_no_2025_conflation():
    """20-25% 不再同时出现在能量消耗和瘦素下降两处"""
    leptin = _read("30_nutrition/leptin_system.md")
    plateau = _read("80_troubleshooting/fat_loss_plateau.md")
    assert "瘦素下降 20-25%" not in plateau
    assert "能量消耗下降 **20-25%**" not in leptin


def test_deload_unified():
    recovery = _read("00_principles/recovery.md")
    adv = _read("10_programming/advanced_periodization.md")
    plateau = _read("80_troubleshooting/fat_loss_plateau.md")
    # 三处都统一到"重量约 50%"口径
    assert "50%" in recovery and "RPE 5-6" in recovery
    assert "重量约 50%" in adv
    assert "约 50%" in plateau


def test_plateau_tdee_before_refeed():
    txt = _read("80_troubleshooting/fat_loss_plateau.md")
    assert "Refeed（高碳日）—— 首选" not in txt  # 不再把 refeed 列首选
    assert txt.index("重新核算 TDEE") < txt.index("Refeed（高碳日）")


def test_recovery_seek_fixed():
    assert "seek 专业帮助" not in _read("00_principles/recovery.md")
    assert "并寻求专业帮助" in _read("00_principles/recovery.md")


# ---------- distill 流水线（确定性部分） ----------

def test_segment_text_at():
    segs = [{"start": 0, "end": 5, "text": "甲"},
            {"start": 5, "end": 10, "text": "乙"},
            {"start": 10, "end": 15, "text": "丙"}]
    assert segment_text_at(segs, 4, 6) == "甲 乙"  # 跨边界重叠
    assert segment_text_at(segs, 10, 15) == "丙"
    assert segment_text_at(segs, 20, 30) == ""


def test_validate_claim():
    good = {"claim": "x", "ts": [1.0, 2.0], "type": "cue",
            "evidence": "blogger_experience", "exercises": ["barbell_back_squat"]}
    assert validate_claim(good) == []
    assert validate_claim({"claim": "x", "ts": [1.0], "type": "cue",
                           "evidence": "blogger_experience"})  # ts 长度错
    assert validate_claim({"claim": "", "ts": [1.0, 2.0], "type": "cue",
                           "evidence": "blogger_experience"})  # 空 claim
    assert validate_claim({"claim": "x", "ts": [1.0, 2.0], "type": "bad",
                           "evidence": "blogger_experience"})  # type 非法
    assert any("不存在的 id" in e for e in validate_claim(
        {"claim": "x", "ts": [1.0, 2.0], "type": "cue",
         "evidence": "blogger_experience", "exercises": ["no_such"]}))


def test_validate_claim_applies_to_shape():
    """K-A01：applies_to 形状校验——维度固定、字符串数组；空=未知不报错"""
    base = {"claim": "x", "ts": [1.0, 2.0], "type": "cue", "evidence": "blogger_experience"}
    # 合法：空维度（未知）与已填维度
    assert validate_claim({**base, "applies_to": {"level": [], "goal": [], "condition": []}}) == []
    assert validate_claim({**base, "applies_to": {"level": ["beginner"], "goal": ["减脂"], "condition": []}}) == []
    assert validate_claim({**base, "applies_to": {}}) == []
    # 非法：未知维度 / 非数组值 / 整体不是对象
    assert validate_claim({**base, "applies_to": {"sex": ["male"]}})
    assert validate_claim({**base, "applies_to": {"level": "beginner"}})
    assert validate_claim({**base, "applies_to": "beginner"})


def test_parse_json_array_tolerant():
    assert _parse_json_array('[{"a":1}]') == [{"a": 1}]
    assert _parse_json_array('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert _parse_json_array('前面废话 [{"a":1}] 后面') == [{"a": 1}]
    assert _parse_json_array("不是 JSON") == []


def test_claims_to_yaml_roundtrip():
    import yaml
    claims = [{"id": "tcy-0001", "claim": "x", "ts": [1.0, 2.0]}]
    assert yaml.safe_load(claims_to_yaml(claims)) == claims


# ---------- claims 运行时接入（2026-09-29：博主素材与教练回答接通） ----------

def test_claim_store_loads():
    from coach.claims import claim_store
    assert len(claim_store) > 100  # tcy/ksw/cs 三个文件都加载


def test_compilation_video_has_speaker_pending():
    """BV17ooLBUEqS（凯圣王上传、双人出镜、AI 字幕不分说话人）的条目
    不能默认全记在谭成义名下：要么 speaker: 待确认，要么是带
    "语境归因"标记的留痕归因（见 speaker_attribution_BV17ooLBUEqS.md，
    2026-10-02 已归因 11 条）"""
    from coach.claims import claim_store
    group = [c for c in claim_store._by_id.values()
             if c.get("video") == "BV17ooLBUEqS"]
    assert group, "合集条目应存在"
    for c in group:
        speaker = c.get("speaker") or ""
        assert speaker, f"{c['id']} 缺少 speaker 字段"
        from coach.claim_review import content_fingerprint
        source = (c.get("reviews") or {}).get("source") or {}
        confirmed = (source.get("status") == "approved" and source.get("by")
                     and source.get("note") and source.get("at")
                     and source.get("fingerprint") == content_fingerprint(c))
        assert speaker == "待确认" or "语境归因" in speaker or confirmed, \
            f"{c['id']} 的 speaker={speaker!r} 缺少待确认/语境归因或有效来源签核留痕"


def test_ka02_mismapped_exercises_removed():
    """K-A02（KNOWLEDGE_AUDIT_2026-10-05）：语义错配修复回归。

    弹力带套膝上侧向移动（髋/臀中肌激活）≠ 弹力带扩胸（后束/中背）；
    俯身哑铃臂屈伸（kickback 姿势）≠ 仰卧臂屈伸。库内无对应动作时
    取消错误映射并待建，不得为覆盖率强挂近似 ID。
    """
    import yaml
    tcy = {c["id"]: c for c in yaml.safe_load((ROOT / "claims/tcy.yaml").read_text("utf-8"))}
    for i in range(18, 23):
        c = tcy[f"tcy-BV1pZiZBxE8y-{i:04d}"]
        assert "band_pull_apart" not in c["exercises"], f"{c['id']} 仍错挂 band_pull_apart"
    for i in range(37, 41):
        c = tcy[f"tcy-BV1MvwxzGEio-{i:04d}"]
        assert "skull_crusher" not in c["exercises"], f"{c['id']} 仍错挂 skull_crusher"
    # 组合总结条目：提示不能统一归给单一动作；颈后/俯身臂屈伸都不是仰卧臂屈伸
    combo = tcy["tcy-BV1MvwxzGEio-0041"]
    assert "skull_crusher" not in combo["exercises"], "组合条目仍错挂 skull_crusher"
    # K-A02 后续（2026-10-06 卡片准备时发现）：《New tech下斜卧推》教的是下斜，
    # 27 条不得错挂到 incline_bench_press（上斜≠下斜，库内暂无下斜动作）
    ksw = {c["id"]: c for c in yaml.safe_load((ROOT / "claims/ksw.yaml").read_text("utf-8"))}
    decline = [c for c in ksw.values() if c.get("video") == "BV1HXXsBBEiE"]
    assert decline, "下斜卧推视频条目应存在"
    for c in decline:
        assert "incline_bench_press" not in (c.get("exercises") or []), \
            f"{c['id']} 仍把下斜卧推条目挂到上斜"
    # K-A02 后续②：《倒蹬详解》教学对象是倒蹬（深蹲/高脚杯只是引用标准）
    lp = [c for c in ksw.values() if c.get("video") == "BV1mT4y1b7Z5"]
    assert lp and all(c["exercises"] == ["leg_press"] for c in lp), \
        "倒蹬详解条目应统一挂 leg_press"


def test_ka03_ea_sleep_is_conditional_research_finding():
    """K-A03：研究结果不得包装为通用 self_check 阈值。

    cs-BV1Tiec6TEv1-0008 的 EA 数值来自每周高强度训练约 15 小时的橄榄球
    运动员研究，单位为大卡/kg去脂体重；条目必须保留人群与单位并取消
    通用自检含义，引用窗口需覆盖 EA 定义段以便核对。
    """
    import yaml
    cs = {c["id"]: c for c in yaml.safe_load((ROOT / "claims/cs.yaml").read_text("utf-8"))}
    c = cs["cs-BV1Tiec6TEv1-0008"]
    assert c["type"] != "self_check", "EA 研究数值不得再标为通用 self_check"
    assert c["ts"][0] <= 32.0, "引用窗口应覆盖 EA 定义段（视频 29s 起）"
    for kw in ("橄榄球运动员", "去脂体重"):
        assert kw in c["claim"], f"claim 缺少研究要素：{kw}"


def test_format_coaching_draft_only_counts():
    """动作素材全是 draft 时：不给内容、只报数量（审核纪律）"""
    from coach.claims import claim_store
    fake_ex = {"id": "x", "cues": ["tcy-0001"], "errors": ["tcy-0003"]}
    text = claim_store.format_coaching(fake_ex)
    assert "待人工审核" in text
    # draft 的具体说法不得泄露给 LLM
    tcy1 = claim_store.get("tcy-0001")
    if tcy1 and tcy1.get("status") != "approved":
        assert tcy1["claim"] not in text


def test_format_coaching_approved_has_source():
    """approved 条目渲染时必须带出处（博主 + BV + 秒数链接）"""
    from coach.claims import ClaimStore
    store = ClaimStore.__new__(ClaimStore)
    store._by_id = {
        "x-1": {"id": "x-1", "blogger": "谭成义", "speaker": "谭成义", "video": "BV128bX6eExV",
                "ts": [192.0, 201.0], "claim": "起身先顶髋", "status": "draft", "provenance": "transcript"},
    }
    from coach.claim_review import record_review
    record_review(store._by_id["x-1"], "source", "测试审核员", "合成测试素材来源核对")
    record_review(store._by_id["x-1"], "applicability", "测试审核员", "合成测试适用性核对")
    text = store.format_coaching({"cues": ["x-1"]})
    assert "起身先顶髋" in text and "BV128bX6eExV?t=192" in text and "谭成义" in text


def test_format_coaching_plain_text_passthrough():
    """字段里人工手写的非 id 文本原样展示（兼容手写动作文件）"""
    from coach.claims import ClaimStore
    store = ClaimStore.__new__(ClaimStore)
    store._by_id = {}
    text = store.format_coaching({"self_check": ["徒手深蹲手放臀部"]})
    assert "徒手深蹲手放臀部" in text


def test_get_exercise_coaching_tool():
    """get_exercise_coaching 工具：归一动作名 → 教学要点 + 关联知识文件"""
    import json
    import tempfile
    from coach.agent import CoachAgent
    agent = CoachAgent(user_id="coaching_t",
                       db_path=Path(tempfile.mkdtemp()) / "t.db")
    result = agent._handle_tool({"name": "get_exercise_coaching",
                                 "arguments": json.dumps({"exercise": "深蹲"})},
                                "normal")
    assert "杠铃深蹲" in result
    assert "20_exercises/leg/squat_technique.md" in result  # knowledge_refs
    r2 = agent._handle_tool({"name": "get_exercise_coaching",
                             "arguments": json.dumps({"exercise": "不存在动作"})},
                            "normal")
    assert "未识别动作" in r2


class _StubLLM:
    """按脚本返回的假 LLM，用于测 distill 编排（不依赖真实 API）"""
    fake = True

    def __init__(self, extract_payload, support_answer="支持"):
        self._extract = json.dumps(extract_payload, ensure_ascii=False)
        self._support = support_answer
        self._calls = 0

    def chat(self, messages, tools=None, temperature=0.7):
        self._calls += 1
        content = self._extract if self._calls == 1 else self._support
        return {"content": content, "tool_calls": []}


def _fixture_transcript(tmp_path):
    t = {"video": "BV1test", "blogger": "谭成义", "title": "测试",
         "segments": [{"start": 0.0, "end": 10.0, "text": "深蹲起身先顶髋"}]}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t, ensure_ascii=False), "utf-8")
    return p


def test_distill_end_to_end_supported(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.distill.ROOT", tmp_path)
    (tmp_path / "claims").mkdir()
    claims_in = [{"claim": "深蹲起身先顶髋", "ts": [0.0, 10.0], "type": "cue",
                  "evidence": "blogger_experience", "exercises": ["barbell_back_squat"],
                  "applies_to": {"level": ["beginner"], "goal": [], "condition": []}}]
    llm = _StubLLM(claims_in, "支持")
    report = distill(_fixture_transcript(tmp_path), "谭成义", llm)
    assert report["valid"] == 1 and not report["flagged"]
    out = (tmp_path / "claims" / "tcy.yaml").read_text("utf-8")
    assert "anti_hallucination: pass" in out and "provenance: transcript" in out
    # K-A01：LLM 明确给出的适用条件应原样落盘（不做普适化默认）
    import yaml as _y
    saved = _y.safe_load(out)
    assert saved[0]["applies_to"]["level"] == ["beginner"]
    # 未提供 applies_to 时默认为全空=未知，不得填充臆测条件
    claims_in2 = [{"claim": "另一条", "ts": [0.0, 10.0], "type": "cue",
                   "evidence": "blogger_experience", "exercises": []}]
    llm2 = _StubLLM(claims_in2, "支持")
    distill(_fixture_transcript(tmp_path), "谭成义", llm2)
    saved2 = _y.safe_load((tmp_path / "claims" / "tcy.yaml").read_text("utf-8"))
    newest = [c for c in saved2 if c["claim"] == "另一条"][0]
    assert newest["applies_to"] == {"level": [], "goal": [], "condition": []}


def test_distill_flags_unsupported(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.distill.ROOT", tmp_path)
    (tmp_path / "claims").mkdir()
    claims_in = [{"claim": "原文没说的东西", "ts": [0.0, 10.0], "type": "cue",
                  "evidence": "blogger_experience", "exercises": []}]
    llm = _StubLLM(claims_in, "不支持")
    report = distill(_fixture_transcript(tmp_path), "谭成义", llm)
    assert report["valid"] == 1
    assert any(f["reason"] == "anti_hallucination" for f in report["flagged"])


def test_distill_drops_schema_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.distill.ROOT", tmp_path)
    (tmp_path / "claims").mkdir()
    claims_in = [{"claim": "x", "ts": [1.0], "type": "bad", "evidence": "x"}]
    llm = _StubLLM(claims_in)
    report = distill(_fixture_transcript(tmp_path), "谭成义", llm)
    assert report["valid"] == 0
    assert any(f["reason"] == "schema" for f in report["flagged"])
