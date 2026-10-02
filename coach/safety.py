"""安全前置检查（确定性规则，不经过 LLM）

设计约束：规则提供保守前置拦截，不声称能识别全部临床风险。
- 关键词唯一来源：knowledge/60_injury_safety/red_flags.md 的一/二/三档表格
- 三档：
  emergency 急症（硬拦截，话术含 120 提示）
  injury    损伤（硬拦截，停动作 + 冰敷 + 不缓解就医）
  yellow    黄色预警（不拦截，注入处理原则让 LLM 融入回复）
- 一/二档命中后先判语境：否定 / 提问 / 病史 → 降级为软提示（soft），
  由 LLM 结合上下文回应，避免"我没有胸闷"被当成急症

语境判断的收紧原则（2026-09-29，防"软化过宽"）：
- 遍历全部关键词的全部出现位置，任一位置不该软化即硬拦截
- 否定只认"命中词紧前面、同一分句内、以否定词收尾"（"我没有胸闷"算；
  "特别胸闷""练完没多久突然胸痛""练得很不舒服，胸闷"都不算）
- 病史只认同一分句内的历史时间词（"训练之前还好好的，现在胸口疼"不算病史）
- 第一人称当下陈述不因为带问句软化（"我现在胸口疼，是不是心脏出问题了"
  仍硬拦截；只有"会不会胸闷"这类假设结构才软化）
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

# 否定：必须出现在命中词紧前面、同一分句内，且否定词与命中词之间最多隔一个"过/有"
# （"没有胸闷/胸口不疼/从未麻木过"算；"特别胸闷""没多久突然胸痛"不算）
_NEGATED_PREFIX = re.compile(r"(?:没有|没|无|未|从不|从未|不)(?:过|有)?$")
_HISTORY = ("以前", "之前", "曾经", "去年", "前年", "小时候", "有过", "病史", "那会儿")
# 假设/条件式提问：只有"会不会/是不是 + 症状"这种假设结构（词在命中词之前）
# 才软化；"症状 + 是不是/会不会…"是发病时的追因提问，不软化
_QUESTION_HYPOTHETICAL_BEFORE = ("会不会", "是不是")
_QUESTION_HYPOTHETICAL_ANY = ("如何预防", "怎么预防", "怎么避免", "是什么意思")
# 知识性提问：需排除第一人称亲历（"我胸闷是怎么回事"仍是急症）
_QUESTION = (
    "是怎么回事", "是什么原因", "为什么", "什么引起",
    "正常吗", "要紧吗", "怎么缓解", "怎么恢复",
)
# 出现这些词说明用户正在亲历，不能按知识提问软化
_FIRST_PERSON = ("我", "现在", "刚刚", "刚才", "今天", "训练时", "练的时候", "突然", "又")

_CLAUSE_SPLIT = re.compile(r"[，。！？；,;!?\n]|但是|不过|然而|但")
_CURRENT = ("现在", "此刻", "正在", "刚刚", "刚才", "今天", "突然", "又", "训练时", "练的时候")


def _latest(text: str, words) -> int:
    return max((text.rfind(w) for w in words), default=-1)


def _clause_start(text: str, pos: int) -> int:
    """命中词所在分句的起始下标（分句按 ，。！？； 等切分）"""
    start = 0
    for m in _CLAUSE_SPLIT.finditer(text):
        if m.start() < pos:
            start = m.end()
        else:
            break
    return start


def _clause_at(text: str, pos: int) -> str:
    start = _clause_start(text, pos)
    end = len(text)
    for m in _CLAUSE_SPLIT.finditer(text, pos):
        end = m.start()
        break
    return text[start:end]


def _soft_reason(text: str, kw: str, pos: int) -> str:
    """判断命中词某一次出现的语境。返回 negated/question/history 之一，或 ""（不软化）"""
    prefix = text[_clause_start(text, pos):pos]  # 命中词之前的部分（限同一分句）
    # 否定：否定词必须贴着命中词（同一分句、前缀以否定词收尾）
    if _NEGATED_PREFIX.search(prefix):
        return "negated"
    # 最近一次“当前状态”切换优先于较早的病史或猜测；问原因不撤销症状。
    current = _latest(prefix, _CURRENT)
    historical = _latest(prefix, _HISTORY)
    hypothetical = _latest(prefix, (*_QUESTION_HYPOTHETICAL_BEFORE, "如果", "假如", "万一"))
    if current > max(historical, hypothetical):
        return ""
    if historical >= 0:
        return "history"
    before = text[max(0, pos - 12):pos]
    after = text[pos + len(kw):pos + len(kw) + 10]
    # 假设结构软化仅限"会不会/是不是 + 症状"（词在命中词之前）：
    # "我会不会胸闷"软化；"我现在胸口疼，是不是心脏出问题了"不软化
    if any(q in prefix for q in _QUESTION_HYPOTHETICAL_BEFORE):
        return "question"
    if any(q in before or q in after for q in _QUESTION_HYPOTHETICAL_ANY):
        return "question"
    if any(q in before or q in after for q in _QUESTION):
        clause = _clause_at(text, pos)
        if not any(fp in clause for fp in _FIRST_PERSON):
            return "question"
    return ""


def _find_all(text: str, kw: str):
    pos = text.find(kw)
    while pos != -1:
        yield pos
        pos = text.find(kw, pos + 1)


def check_red_flags(text: str) -> SafetyHit | None:
    """检查用户输入。返回 SafetyHit；未命中返回 None。

    mode=block：固定话术直接返回，不调用 LLM
    mode=soft：不拦截，调用方注入 soft_note() 后继续正常流程

    判定规则（2026-09-29 收紧）：
    - 遍历三档全部关键词的全部出现位置（不是命中第一个就返回）
    - 任一应硬拦截的位置存在 → block（取档位最高的那个）
      （"没有胸闷，但刚才眼前发黑了"：胸闷软化、眼前发黑不软化 → block）
    - 全部命中位置都软化 → soft（取档位最高的 soft 命中）
    """
    block_hit: SafetyHit | None = None
    soft_hit: SafetyHit | None = None
    for tier in ("emergency", "injury", "yellow"):
        for kw, _note in _KEYWORDS[tier]:
            for pos in _find_all(text, kw):
                if tier == "yellow":
                    if soft_hit is None:
                        soft_hit = SafetyHit(tier, "soft", kw, "yellow", "")
                    continue
                reason = _soft_reason(text, kw, pos)
                if reason:
                    if soft_hit is None:
                        soft_hit = SafetyHit(tier, "soft", kw, reason, "")
                else:
                    if block_hit is None:  # 保留本档第一个硬拦截命中
                        block_hit = SafetyHit(
                            tier, "block", kw, "",
                            EMERGENCY_RESPONSE if tier == "emergency" else INJURY_RESPONSE,
                        )
        if block_hit is not None:
            return block_hit  # 当前档位已有硬拦截，低档位不再覆盖
    return block_hit or soft_hit


_REASON_LABEL = {"negated": "否定", "question": "提问", "history": "病史", "yellow": "黄色预警"}


def soft_note(hit: SafetyHit) -> str:
    """soft 命中时注入对话的安全提示（给 LLM 看，不给用户看）"""
    if hit.tier == "yellow":
        guidance = next(
            (n for k, n in _KEYWORDS["yellow"] if k == hit.keyword), ""
        )
        return (
            f"【安全提示·勿直接引用】用户提到「{hit.keyword}」（黄色预警）。"
            f"处理原则：{guidance}。请把这些建议自然融入回复；"
            "若用户说症状持续或加重，明确建议就医。"
        )
    return (
        f"【安全提示·勿直接引用】用户输入命中安全词「{hit.keyword}」"
        f"（{TIER_LABEL[hit.tier]}），命中位置处于{_REASON_LABEL[hit.reason]}语境，"
        "规则判断该处**可能**不是正在发作，故未硬拦截。"
        "请：1) 正常回应当前话题；2) 结合上下文自行判断——若有任何迹象表明症状"
        "正在发生或加重，按急症对待并明确建议停止训练、尽快就医；"
        "3) 简短带上安全意识即可。"
    )
