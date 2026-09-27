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


def test_parse_json_array_tolerant():
    assert _parse_json_array('[{"a":1}]') == [{"a": 1}]
    assert _parse_json_array('```json\n[{"a":1}]\n```') == [{"a": 1}]
    assert _parse_json_array('前面废话 [{"a":1}] 后面') == [{"a": 1}]
    assert _parse_json_array("不是 JSON") == []


def test_claims_to_yaml_roundtrip():
    import yaml
    claims = [{"id": "tcy-0001", "claim": "x", "ts": [1.0, 2.0]}]
    assert yaml.safe_load(claims_to_yaml(claims)) == claims


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
                  "evidence": "blogger_experience", "exercises": ["barbell_back_squat"]}]
    llm = _StubLLM(claims_in, "支持")
    report = distill(_fixture_transcript(tmp_path), "谭成义", llm)
    assert report["valid"] == 1 and not report["flagged"]
    out = (tmp_path / "claims" / "tcy.yaml").read_text("utf-8")
    assert "anti_hallucination: pass" in out and "provenance: transcript" in out


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
