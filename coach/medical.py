"""共享医疗准入：保留原话和限制，无法确认时不推断训练许可。"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SPLIT = re.compile(r"[，,。；;！!？?\n]|但是|不过|然而|但|而且|还有")
_NEGATIVE = {"", "无", "没有", "否", "none", "正常", "没问题", "没事", "无异常",
             "都正常", "都没问题", "都无", "一切正常", "身体健康", "健康"}
_NEGATED = re.compile(r"^(?:我)?(?:没有|没|无|未)(.+)$")
_AFFIRMATIVE = re.compile(r"有[：:]|患|确诊|服用|在吃|控制|不正常|异常|需要|出现")
_HEALTHY = re.compile(r"^(?:身体|心脏|血压|心脏血压|心肺|体检|一切)?(?:都)?(?:正常|没问题|没事|健康|无恙)$")


def screening_positive(value) -> bool:
    """仅把明确的阴性陈述视为阴性；混合句有一项阳性就保留。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    for clause in _SPLIT.split(str(value).strip()):
        s = clause.strip()
        if s.lower() in _NEGATIVE or re.fullmatch(r"不适用(?:[（(]男性[）)])?", s):
            continue
        if s.startswith("有") or _AFFIRMATIVE.search(s):
            return True
        # 允许明确否定的列举，但不将整段混合表述仅凭首字判阴性。
        if all(_NEGATED.fullmatch(part.strip()) for part in s.split("、")):
            continue
        if _HEALTHY.fullmatch(s):
            continue
        return True
    return False


@dataclass(frozen=True)
class TrainingPermission:
    status: str  # prohibited / pending / limited / allowed
    evidence: str
    reason: str

    @property
    def allows_prescription(self) -> bool:
        return self.status == "allowed"


_NO_RESTRICTION = re.compile(
    r"^(?:医生)?(?:没有|没)(?:说过|要求|嘱咐过)?(?:不让运动|限制运动|限制|限制训练)$")
_DENY = re.compile(r"禁止|不允许|不允許|不准|不让|不能|不可|不得|暂停|停止|避免")
_UNCONFIRMED = re.compile(r"未(?:明确)?(?:同意|允许|放行)|尚未|还没|没(?:有)?(?:允许|同意|放行)|未确认")
_LIMIT = re.compile(r"只能|仅(?:可|能|限)|只(?:允许|能|可)|限制|低强度|中等强度|中低强度|散步|步行|康复|有条件")
# 普通“可以运动/没问题”并不能证明允许恢复高强度力量处方。
_FULL_PERMISSION = re.compile(
    r"(?:允许|同意|可以|准许|放行).*(?:正常|原有|原来|不受限|无强度限制).*(?:训练|运动)|"
    r"(?:训练|运动)(?:没有|无)(?:任何)?(?:强度)?限制")


def training_permission(profile: dict) -> TrainingPermission:
    conditions = profile.get("conditions") or {}
    hs = conditions.get("health_screen") or {}
    evidence = str(hs.get("clearance") or "").strip()
    positive = any(screening_positive(v) for k, v in hs.items() if k != "clearance")
    clauses = [s.strip() for s in _SPLIT.split(evidence) if s.strip()]
    meaningful = [s for s in clauses
                  if s.lower() not in _NEGATIVE and not _NO_RESTRICTION.fullmatch(s)]
    # 禁止/不明确优先于同句或其他句的许可；不把“双重否定”擅自解释为放行。
    if any(_DENY.search(s) for s in meaningful):
        return TrainingPermission("prohibited", evidence,
                                  "医嘱含禁止或限制要求，暂停自动训练处方，请先确认允许的活动范围")
    if any(_UNCONFIRMED.search(s) for s in meaningful):
        return TrainingPermission("pending", evidence,
                                  "尚未确认训练许可，暂不生成训练处方")
    if any(_LIMIT.search(s) for s in meaningful):
        return TrainingPermission("limited", evidence,
                                  "仅有有限活动许可，不能推断为正常力量训练许可；请遵守原医嘱")
    if meaningful:
        if all(_FULL_PERMISSION.search(s) for s in meaningful):
            return TrainingPermission("allowed", evidence, "已有明确的正常训练许可")
        return TrainingPermission("pending", evidence,
                                  "医嘱的训练范围尚不明确，暂不生成训练处方")
    if positive:
        return TrainingPermission("pending", evidence,
                                  "健康筛查有需关注项，医生尚未明确放行训练，暂不生成训练处方")
    return TrainingPermission("allowed", evidence, "未报告需限制训练的健康事项")
