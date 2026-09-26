"""安全前置检查（确定性规则，不经过 LLM）

设计铁律：红旗检测必须是 100% 可靠的代码规则。
- 关键词唯一来源：knowledge/60_injury_safety/red_flags.md 的一/二/三档表格
- 三档：
  emergency 急症（硬拦截，话术含 120 提示）
  injury    损伤（硬拦截，停动作 + 冰敷 + 不缓解就医）
  yellow    黄色预警（不拦截，注入处理原则让 LLM 融入回复）
- 一/二档命中后先判语境：否定 / 提问 / 病史 → 降级为软提示（soft），
  由 LLM 结合上下文回应，避免"我没有胸闷"被当成急症
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RED_FLAGS_MD = (
    Path(__file__).resolve().parent.parent
    / "knowledge" / "60_injury_safety" / "red_flags.md"
)

TIER_BY_SECTION = {"一": "emergency", "二": "injury", "三": "yellow"}
TIER_LABEL = {"emergency": "急症红旗", "injury": "损伤红旗", "yellow": "黄色预警"}

EMERGENCY_RESPONSE = (
    "⚠️ 你描述的症状属于必须重视的信号。作为教练，我必须明确：\n\n"
    "1. **请立即停止当前训练**，不要带病坚持；\n"
    "2. **建议尽快就医**，让专业医生评估；\n"
    "3. **如果症状持续或加重，请拨打 120**；\n"
    "4. 我不是医生，无法也不应该做任何医疗诊断。\n\n"
    "健康永远排在训练前面。确认无恙后随时回来，我们从低强度重新开始。"
)

INJURY_RESPONSE = (
    "⚠️ 尖锐疼痛/麻木是组织可能损伤的信号，请认真对待：\n\n"
    "1. **立即停止引发症状的动作**，不要带伤练完；\n"
    "2. 急性期（48 小时内）可冰敷缓解，每次 15-20 分钟；\n"
    "3. **48 小时不缓解或加重，请就医**；\n"
    "4. 我不是医生，无法也不应该做任何医疗诊断。\n\n"
    "休息几天不丢人，带伤练才可能停训几个月。"
)


@dataclass
class SafetyHit:
    tier: str      # emergency / injury / yellow
    mode: str      # block / soft
    keyword: str
    reason: str    # block 为 ""；soft 为 negated / question / history / yellow
    response: str  # block 时的固定话术；soft 时为 ""


# ---------- 关键词解析（单一来源：red_flags.md） ----------

def _parse_keywords(md_text: str) -> dict[str, list[tuple[str, str]]]:
    """解析一/二/三档表格，返回 {tier: [(关键词, 该行处理原则/话术要点)]}"""
    tiers: dict[str, list[tuple[str, str]]] = {
        "emergency": [], "injury": [], "yellow": [],
    }
    tier: str | None = None
    for line in md_text.splitlines():
        m = re.match(r"^##\s+([一二三四五])、", line)
        if m:
            tier = TIER_BY_SECTION.get(m.group(1))
            continue
        if tier and line.lstrip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or "关键词" in cells[1] or set(cells[1]) <= {"-", " "}:
                continue
            note = cells[2] if len(cells) > 2 else ""
            for kw in cells[1].split("、"):
                kw = kw.strip()
                if kw:
                    tiers[tier].append((kw, note))
    if not all(tiers.values()):
        raise RuntimeError("red_flags.md 解析失败：急症/损伤/黄色三档任一为空")
    return tiers


_KEYWORDS = _parse_keywords(RED_FLAGS_MD.read_text(encoding="utf-8"))

# ---------- 语境判断（否定 / 提问 / 病史 → 软化） ----------

_NEGATORS = ("没有", "没", "无", "未", "别")
# "不"在"会不会/是不是/能不能/要不要"里是疑问助词，不是否定
_NEG_BU = re.compile(r"不(?![是会能要])")
_HISTORY = ("以前", "之前", "曾经", "去年", "前年", "小时候", "有过", "病史", "那会儿")
# 假设/条件式提问：从语义上就不可能是"正在发作"，始终软化
_QUESTION_HYPOTHETICAL = (
    "会不会", "是不是", "如何预防", "怎么预防", "怎么避免", "是什么意思",
)
# 知识性提问：需排除第一人称亲历（"我胸闷是怎么回事"仍是急症）
_QUESTION = (
    "是怎么回事", "是什么原因", "为什么", "什么引起",
    "正常吗", "要紧吗", "怎么缓解", "怎么恢复",
)
# 出现这些词说明用户正在亲历，不能按知识提问软化
_FIRST_PERSON = ("我", "现在", "刚刚", "刚才", "今天", "训练时", "练的时候", "突然", "又")

_CLAUSE_SPLIT = re.compile(r"[，。！？；,;!?\n]")


def _clause_at(text: str, pos: int) -> str:
    start = 0
    for m in _CLAUSE_SPLIT.finditer(text):
        if m.start() < pos:
            start = m.end()
        else:
            break
    end = len(text)
    for m in _CLAUSE_SPLIT.finditer(text, pos):
        end = m.start()
        break
    return text[start:end]


def _soft_reason(text: str, kw: str, pos: int) -> str:
    """判断命中词的语境。返回 negated/question/history 之一，或 ""（不软化）"""
    before = text[max(0, pos - 12):pos]
    window = text[max(0, pos - 8):pos]
    if any(neg in window for neg in _NEGATORS) or _NEG_BU.search(window):
        return "negated"
    if any(h in before for h in _HISTORY):
        return "history"
    after = text[pos + len(kw):pos + len(kw) + 10]
    if any(q in before or q in after for q in _QUESTION_HYPOTHETICAL):
        return "question"
    if any(q in before or q in after for q in _QUESTION):
        clause = _clause_at(text, pos)
        if not any(fp in clause for fp in _FIRST_PERSON):
            return "question"
    return ""


def check_red_flags(text: str) -> SafetyHit | None:
    """检查用户输入。返回 SafetyHit；未命中返回 None。

    mode=block：固定话术直接返回，不调用 LLM
    mode=soft：不拦截，调用方注入 soft_note() 后继续正常流程
    """
    for tier in ("emergency", "injury", "yellow"):
        for kw, _note in _KEYWORDS[tier]:
            pos = text.find(kw)
            if pos == -1:
                continue
            if tier == "yellow":
                return SafetyHit(tier, "soft", kw, "yellow", "")
            reason = _soft_reason(text, kw, pos)
            if reason:
                return SafetyHit(tier, "soft", kw, reason, "")
            return SafetyHit(
                tier, "block", kw, "",
                EMERGENCY_RESPONSE if tier == "emergency" else INJURY_RESPONSE,
            )
    return None


_REASON_LABEL = {"negated": "否定", "question": "提问", "history": "病史", "yellow": "黄色预警"}


def soft_note(hit: SafetyHit) -> str:
    """soft 命中时注入对话的安全提示（给 LLM 看，不给用户看）"""
    if hit.tier == "yellow":
        guidance = next(
            (n for k, n in _KEYWORDS["yellow"] if k == hit.keyword), ""
        )
        return (
            f"【安全提示·勿直接引用】用户提到「{hit.keyword}」（黄色预警）。"
            f"处理原则：{guidance}。请把这些建议自然融入回复，这是降阶处理不是急症，"
            "不要渲染恐慌；若用户说症状持续或加重，建议就医。"
        )
    return (
        f"【安全提示·勿直接引用】用户输入命中安全词「{hit.keyword}」"
        f"（{TIER_LABEL[hit.tier]}），但语境为{_REASON_LABEL[hit.reason]}，不按急症处理。"
        "请：1) 正常回应当前话题；2) 简短带上安全意识——若真的出现该症状，"
        "应停止训练并及时就医；3) 不要渲染恐慌。"
    )
