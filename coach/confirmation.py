"""Conservative lexical checks for confirming staged profile changes.

The LLM may propose which pending change to confirm, but it cannot turn an
ambiguous or negative user message into consent. Acceptance must also identify
the specific staged value (or explicitly refer to the sole pending change).
"""
from __future__ import annotations

import re

from .goals import goal_label

Decision = str  # "accept" | "reject" | "unclear"

_DECLINE = re.compile(
    r"不同意|不太同意|不接受|不批准|不确认|没有同意|没同意|没有确认|没确认|"
    r"不是(?:同意|确认|接受|可以)|并非(?:同意|确认|接受)|不算(?:同意|确认)|"
    r"不可以|不行|不合适|不太好|不大好|不怎么好|不是很好|不好|"
    r"不觉得.{0,2}(?:好|可以|行|合适)|没(?:有)?(?:说|表示)?好|"
    r"拒绝|别改|不要.{0,4}改|不想改|不建议.{0,4}改|不改|不换|不转|"
    r"先不改|暂不改|先不|暂不|取消|算了|撤销|维持原|保留原|按原来"
)
_UNCLEAR = re.compile(
    r"不确定|拿不准|再考虑|再想想|回头再说|之后再说|先等等|等一等|"
    r"可能|也许|看情况|不一定|不好说|是否|要不要|好不好|怎么样|可以吗|"
    r"行不行|可不可以|能不能|行吗|好吗|应该|大概|似乎|好像|试试看|"
    r"考虑|想改|想换|想转|先想|想一下|想一想|了解一下|问一下"
)
_AFFIRM = re.compile(
    r"确认|同意|接受|批准|可以|好|对|是的|没问题|按这个|照这个|"
    r"就这么办|决定|我选|选这个|按新方案|那就|就按|嗯|行|ok", re.IGNORECASE
)
_SOLE_CHANGE_REFERENCE = re.compile(
    r"(?:这个|上述|上面|刚才的?)(?:档案)?(?:变更|修改|调整|方案)"
    r"|(?:变更|修改|调整|方案)(?:就是|按|照)刚才(?:说的|那个)?"
)
_SAFETY_RESOLUTION_NEGATIVE = re.compile(
    r"(?:还|仍|依旧|继续)(?:在|有|会|感到)?(?:胸闷|胸痛|刺痛|麻木|头晕|不适|疼痛|疼|痛|不舒服)|"
    r"(?:疼|痛|胸闷|不适|刺痛|麻木|头晕).{0,6}(?:还在|仍有|持续|加重|再次出现)|"
    r"(?:没|没有|未).{0,4}(?:消失|好转|缓解|恢复|看医生|就医)|"
    r"(?:没|没有|并非|不是)(?:真的|已经)?(?:不疼|不痛|没事|没问题|无碍|正常)|"
    r"好转|缓解|减轻|好多了|好了(?:点|一点|一些|些|多了)|好了一点|好了一些|"
    r"好些了|稍微好|有所改善|"
    r"加重|恶化|更严重|再次出现|又出现"
)
_SAFETY_RESOLUTION_POSITIVE = re.compile(
    r"(?:症状|疼痛|不适|胸闷|胸痛|刺痛|麻木|膝盖|肩膀|胸口|腰).{0,10}"
    r"(?:消失|没有了|没了|好了|恢复|不疼|不痛|没事|没问题|无碍|正常)|"
    r"(?:不疼|不痛|没疼|没痛|没有不适|没有疼痛|不再胸闷|不再刺痛)(?:了|$|[，。])|"
    r"(?:没有|不再|无)(?:任何)?(?:症状|疼痛|不适|胸闷|胸痛|刺痛|麻木)|"
    r"(?:医生|医院|检查|复查).{0,12}(?:确认|说|结果|显示)?.{0,4}"
    r"(?:没事|没问题|无碍|正常|无异常|允许|可以)|"
    r"(?:确认|证明|检查结果).{0,6}(?:没事|没问题|无碍|正常|无异常)"
)
_SAFETY_IDENTITY_GROUPS = {
    "chest": ("胸闷", "胸痛", "胸口", "胸部", "胸"),
    "chest_tightness": ("胸闷", "胸口闷", "胸部闷"),
    "chest_pain": ("胸痛", "胸口痛", "胸口疼", "心口痛"),
    "knee": ("膝关节", "膝盖", "膝"),
    "lower_back": ("下背", "腰部", "腰"),
    "shoulder": ("肩关节", "肩膀", "肩部", "肩"),
    "neck": ("颈椎", "颈部", "脖子", "颈"),
    "elbow": ("肘关节", "手肘", "肘部", "肘"),
    "wrist": ("腕关节", "手腕", "腕"),
    "ankle": ("踝关节", "脚踝", "踝"),
    "hip": ("髋关节", "髋部", "髋"),
    "head": ("头晕", "眩晕", "眼前发黑", "头昏", "头疼", "头痛"),
    "breathing": ("呼吸困难", "喘不过气", "气短", "气促", "喘"),
    "palpitation": ("心悸", "心慌", "心跳"),
    "urine": ("酱油色尿", "尿色", "尿"),
    "sharp_pain": ("刺痛", "剧痛", "撕裂感", "锐痛"),
    "joint_pain": ("关节疼痛", "关节疼", "关节痛"),
    "nausea": ("恶心", "呕吐"),
    "injury": ("骨折", "受伤", "损伤"),
    "general_pain": ("疼痛", "疼", "痛"),
}

_CHINESE_NUMBERS = {
    0: ("零", "〇"), 1: ("一",), 2: ("二", "两"),
    3: ("三",), 4: ("四",), 5: ("五",), 6: ("六",),
    7: ("七",), 8: ("八",), 9: ("九",), 10: ("十",),
}


def classify_decision(text: str) -> Decision:
    """Return accept/reject/unclear, checking refusal and uncertainty first."""
    value = str(text or "").strip()
    if not value:
        return "unclear"
    if _UNCLEAR.search(value) or "?" in value or "？" in value:
        return "unclear"
    declines = list(_DECLINE.finditer(value))
    if declines:
        # Contradictory messages stay pending. Mask refusal phrases first so
        # words such as “不同意” do not count again as the affirmative “同意”.
        masked = list(value)
        for match in declines:
            masked[match.start():match.end()] = " " * (match.end() - match.start())
        if _AFFIRM.search("".join(masked)):
            return "unclear"
        return "reject"
    if _AFFIRM.search(value):
        return "accept"
    return "unclear"


def _safety_identity_tags(text: str) -> set[str]:
    return {tag for tag, aliases in _SAFETY_IDENTITY_GROUPS.items()
            if any(alias in text for alias in aliases)}


def classify_safety_resolution(text: str, target: dict | None = None,
                               open_flags: list[dict] | None = None) -> Decision:
    """Require a clear resolution tied to the selected safety event."""
    value = str(text or "").strip()
    if not value or "?" in value or "？" in value:
        return "unclear"
    if _SAFETY_RESOLUTION_NEGATIVE.search(value):
        return "reject"
    if not _SAFETY_RESOLUTION_POSITIVE.search(value):
        return "unclear"
    if not isinstance(target, dict):
        return "accept"

    open_flags = [f for f in (open_flags or [target])
                  if isinstance(f, dict) and f.get("status") == "open"]
    source = " ".join(str(target.get(key) or "") for key in ("text", "kw"))
    target_tags = _safety_identity_tags(source)
    if len(open_flags) <= 1 and not target_tags:
        return "accept"
    mentioned_tags = _safety_identity_tags(value)
    other_tags = set().union(*(
        _safety_identity_tags(" ".join(str(f.get(key) or "")
                                       for key in ("text", "kw")))
        for f in open_flags if f.get("flag_id") != target.get("flag_id")
    ))
    if (target_tags - other_tags) & mentioned_tags:
        return "accept"
    # For duplicate symptom categories, require the exact trigger keyword if it
    # distinguishes this event from the other open records.
    keyword = str(target.get("kw") or "").strip()
    other_keywords = {str(f.get("kw") or "").strip() for f in open_flags
                      if f.get("flag_id") != target.get("flag_id")}
    if keyword and keyword not in other_keywords and keyword in value:
        return "accept"
    return "unclear"


def _number_forms(value) -> tuple[str, ...]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return (str(value).strip(),) if str(value).strip() else ()
    forms = [str(number)]
    forms.extend(_CHINESE_NUMBERS.get(number, ()))
    if number == 30:
        forms.append("半")
    return tuple(dict.fromkeys(forms))


def _mentions_new_value(text: str, change: dict) -> bool:
    field = str(change.get("field") or "")
    value = change.get("new")
    if value is None:
        return False

    if field == "goal.primary":
        aliases = {
            "fat_loss": ("减脂", "减重"),
            "muscle_gain": ("增肌", "肌肉增长"),
            "strength": ("力量", "力量训练"),
            "health": ("健康",),
            "shaping": ("塑形", "形体"),
        }
        return any(alias in text for alias in aliases.get(str(value), (goal_label(str(value)),)))

    if field == "resources.location":
        aliases = {
            "gym": ("健身房", "健身馆", "gym"),
            "home": ("在家", "居家", "家里", "家庭", "home"),
        }
        return any(alias.lower() in text.lower()
                   for alias in aliases.get(str(value).lower(), (str(value),)))

    if field in ("resources.session_minutes", "resources.days_per_week",
                 "experience.training_years"):
        unit = {
            "resources.session_minutes": r"(?:分钟|分|min(?:utes?)?)",
            "resources.days_per_week": r"(?:次|天)",
            "experience.training_years": r"年",
        }[field]
        for form in _number_forms(value):
            if form == "半" and field == "resources.session_minutes":
                if re.search(r"半小时|半个小时", text):
                    return True
                continue
            if re.search(rf"(?<!\d){re.escape(form)}\s*{unit}", text, re.IGNORECASE):
                return True
        return False

    raw = str(value).strip()
    return bool(raw and raw.casefold() in text.casefold())


def change_is_referenced(text: str, entry: dict, pending: list[dict],
                         decision: Decision) -> bool:
    """Require an unambiguous reference to this entry's proposed value(s)."""
    changes = entry.get("changes") or []
    if not changes:
        return False

    if len(pending) == 1 and _SOLE_CHANGE_REFERENCE.search(text):
        return True
    # A concise refusal can refer to the only outstanding change ("不改了").
    if len(pending) == 1 and decision == "reject" and _DECLINE.search(text):
        return True

    matches = []
    for candidate in pending:
        candidate_changes = candidate.get("changes") or []
        if candidate_changes and all(_mentions_new_value(text, c)
                                     for c in candidate_changes):
            matches.append(candidate.get("id"))
    return len(matches) == 1 and matches[0] == entry.get("id")
