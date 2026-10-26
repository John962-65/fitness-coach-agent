"""确定性安全分流规则库（P3-2）。

规则资产纪律：
- 每条规则带 rule_id / source / review_status / version / action /
  restriction_hint——可审计、可测版本；
- 规则内容为通用运动健康安全提示中的常见警示情形（红旗症状），
  **来源标注为公开常识性安全提示，非临床指南**；专业审核缺口在交付
  文档如实记录（P3-8）；
- 输出四态（信息分流，非诊断）：
  urgent_evaluation / professional_evaluation / uncertain / general_information；
- "未报告危险症状 ≠ 没有危险症状"：描述信息不足时返回 uncertain，
  绝不把未知解释为无风险；
- severity（自报 1-10）不单独决定分流级别——高严重度但无红旗 →
  uncertain（建议观察/必要时评估），只有命中警示情形才升级。

版本：RULES_VERSION = "rehab-rules-1"。修改规则必须升版本并跑
test_p3 的规则版本测试。
"""
from __future__ import annotations

import re
from datetime import date, datetime

RULES_VERSION = "rehab-rules-1"
REVIEW_STATUS = "system_default（待专业审核）"
SOURCE = "通用运动健康安全提示（常识性警示情形汇总，非临床指南、非诊断依据）"

RULES: list[dict] = [
    {
        "rule_id": "rf-cardiovascular",
        "terms": ["胸闷", "胸痛", "胸部疼痛", "胸口疼痛", "胸口痛",
                  "胸部剧痛", "心悸", "呼吸困难", "喘不上气", "气短",
                  "头晕", "眩晕", "眼前发黑", "晕厥", "昏倒", "晕倒",
                  "意识丧失", "出冷汗"],
        "action": "urgent_evaluation",
        "message": ("你描述的症状可能涉及心血管等需要立即评估的情况。请立即停止运动，"
                    "尽快就医或拨打急救电话；在获得专业评估结论前不要恢复训练。"),
        "restriction_hint": "暂停全部训练，等待专业评估",
    },
    {
        "rule_id": "rf-trauma-unable-weightbearing",
        "terms": ["无法负重", "不能走路", "站不起来", "无法站立", "不能踩地",
                  "剧痛", "剧烈疼痛", "撕裂感", "啪的一声", "听到响声",
                  "受伤当时"],
        "action": "urgent_evaluation",
        "message": ("创伤后无法负重或疑似组织损伤需要尽快专业评估（必要时影像检查）。"
                    "请停止相关部位活动并就医。"),
        "restriction_hint": "暂停相关部位全部训练，等待专业评估",
    },
    {
        "rule_id": "rf-swelling-deformity",
        "terms": ["肿胀", "肿起来", "越来越肿", "肿了", "变形", "淤青扩散",
                  "发烫", "发热局部", "红肿", "皮肤发红"],
        "action": "urgent_evaluation",
        "message": ("进行性肿胀/局部红热提示需要尽快专业评估，不宜等待观察。"
                    "请就医检查后再决定活动安排。"),
        "restriction_hint": "暂停相关部位全部训练，等待专业评估",
    },
    {
        "rule_id": "rf-night-rest-pain",
        "terms": ["夜里痛", "夜间痛", "静息痛", "不活动也痛", "睡觉痛醒",
                  "休息也痛", "持续不停"],
        "action": "professional_evaluation",
        "message": ("休息或夜间仍持续疼痛不是普通训练后酸痛的典型表现，"
                    "建议尽快咨询医生或物理治疗师进行评估。"),
        "restriction_hint": "暂停相关部位训练，等待评估",
    },
    {
        "rule_id": "rf-numbness-radiating",
        "terms": ["麻木", "发麻", "放射", "窜到", "刺痛向下", "无力", "拿不住",
                  "脚麻", "手麻"],
        "action": "professional_evaluation",
        "message": ("麻木或放射性症状涉及神经层面，需要专业评估；"
                    "不建议继续对相关部位施加训练负荷。"),
        "restriction_hint": "暂停相关部位训练，等待评估",
    },
    {
        "rule_id": "rf-locking-giving-way",
        "terms": ["交锁", "卡住", "打软腿", "打软", "错位感", "不稳", "打滑"],
        "action": "professional_evaluation",
        "message": ("关节交锁或不稳（打软腿）需要专业评估，继续训练可能加重损伤。"),
        "restriction_hint": "暂停相关部位训练，等待评估",
    },
    {
        "rule_id": "rf-fever-systemic",
        "terms": ["发烧", "发热", "寒战", "全身乏力"],
        "action": "professional_evaluation",
        "message": ("发热或全身症状伴随局部不适时，请先就医排查，不要把训练当作手段。"),
        "restriction_hint": "发热期间暂停训练",
    },
]

# 持续时间/功能限制类规则（需要结构化输入，不走关键词）
PERSISTENT_DAYS = 14
DAILY_LIMITATION_TERMS = ["走路", "上下楼", "下楼", "蹲下", "起床", "提东西",
                          "拿东西", "工作", "睡觉受影响", "生活"]

PROFESSIONAL_PERSISTENT = {
    "rule_id": "persistent-worsening",
    "action": "professional_evaluation",
    "message": (f"同一部位不适持续超过 {PERSISTENT_DAYS} 天或呈加重趋势，"
                "建议咨询医生或物理治疗师；在此之前相关部位避免大负荷训练。"),
    "restriction_hint": "相关部位避免大负荷训练，等待评估或缓解",
}
PROFESSIONAL_DAILY = {
    "rule_id": "daily-limitation",
    "action": "professional_evaluation",
    "message": ("不适已影响日常活动（走路/上下楼/提物等），建议进行专业评估；"
                "相关部位训练暂停。"),
    "restriction_hint": "暂停相关部位训练，等待评估",
}
GENERAL_MILD = {
    "rule_id": "mild-post-exercise",
    "action": "general_information",
    "message": ("运动后的轻度酸痛通常属于正常反应：保持适度活动、关注恢复"
                "（可在恢复页记录）；若加重、持续或出现新的症状，请回来更新记录，"
                "系统会重新评估。这不是诊断，只是常见情况的一般说明。"),
    "restriction_hint": None,
}
UNCERTAIN = {
    "rule_id": "insufficient-information",
    "action": "uncertain",
    "message": ("你描述的信息不足以判断风险方向。请注意：未报告危险症状不代表"
                "没有风险。如果不适加重、持续超过两周或影响日常活动，请寻求"
                "专业评估；当前相关部位建议保守安排。"),
    "restriction_hint": "相关部位保守安排（避免大负荷）",
}


_NEGATION_BEFORE = ("不", "无", "没", "消", "退", "未")


def _hit_terms(text: str, terms: list[str]) -> list[str]:
    """关键词命中，排除紧邻的否定前缀（"消肿""不头晕"不命中）。"""
    hits = []
    for t in terms:
        start = 0
        while True:
            idx = text.find(t, start)
            if idx < 0:
                break
            if idx == 0 or text[idx - 1] not in _NEGATION_BEFORE:
                hits.append(t)
                break
            start = idx + len(t)
    return hits


_NEGATION_AFTER = ("正常", "没问题", "不受影响", "不受限", "自如", "无碍", "没有受限",
                   "没有影响", "不影响")


def _hit_daily_limitations(text: str) -> list[str]:
    """功能受限词命中，排除紧随其后的否定（"走路正常"≠功能受限）。"""
    hits = []
    for t in DAILY_LIMITATION_TERMS:
        start = 0
        while True:
            idx = text.find(t, start)
            if idx < 0:
                break
            after = text[idx + len(t): idx + len(t) + 4]
            if not any(after.startswith(n) for n in _NEGATION_AFTER):
                hits.append(t)
                break
            start = idx + len(t)
    return hits


def _severity_rule(severity, onset_date) -> dict | None:
    """severity 不单独定级：仅作为"持续/加重"路径的参考。"""
    return None


def triage(text: str, severity=None, functional_limitations=None,
           onset_at: str | None = None, professional_evaluated: bool = False) -> dict:
    """确定性分流。返回 {action, matched_rules[], message, restriction_hint,
    rules_version, review_status}。保存路径同步调用（不依赖后台任务）。"""
    text_all = " ".join(filter(None, [
        str(text or ""), " ".join(functional_limitations or [])]))
    matched: list[dict] = []
    hints: list[str] = []
    for rule in RULES:
        hits = _hit_terms(text_all, rule["terms"])
        if hits:
            matched.append({"rule_id": rule["rule_id"], "hits": hits,
                            "action": rule["action"]})
            hints.append(rule["restriction_hint"])

    # 结构化规则：持续天数 / 日常功能受限
    days = None
    if onset_at:
        try:
            start = date.fromisoformat(str(onset_at)[:10])
            days = (date.today() - start).days
        except ValueError:
            pass
    if days is not None and days >= PERSISTENT_DAYS:
        matched.append({"rule_id": PROFESSIONAL_PERSISTENT["rule_id"],
                        "hits": [f"持续 {days} 天"], "action": "professional_evaluation"})
        hints.append(PROFESSIONAL_PERSISTENT["restriction_hint"])
    daily_hits = _hit_daily_limitations(text_all)
    if daily_hits:
        matched.append({"rule_id": PROFESSIONAL_DAILY["rule_id"],
                        "hits": daily_hits, "action": "professional_evaluation"})
        hints.append(PROFESSIONAL_DAILY["restriction_hint"])

    if any(m["action"] == "urgent_evaluation" for m in matched):
        action = "urgent_evaluation"
        message = next(r for r in RULES
                       if r["rule_id"] == next(m for m in matched
                                               if m["action"] == "urgent_evaluation")
                       ["rule_id"])["message"]
        # 合并所有 urgent 提示
        msgs = [r["message"] for r in RULES
                if r["rule_id"] in {m["rule_id"] for m in matched
                                    if m["action"] == "urgent_evaluation"}]
        message = "；".join(dict.fromkeys(msgs))
    elif matched:
        action = "professional_evaluation"
        msgs = [PROFESSIONAL_PERSISTENT["message"] if m["rule_id"] == "persistent-worsening"
                else PROFESSIONAL_DAILY["message"]
                for m in matched if m["action"] == "professional_evaluation"]
        message = "；".join(dict.fromkeys(msgs))
    elif professional_evaluated:
        action = "general_information"
        message = ("你已记录正在接受专业评估——请按专业人员的安排执行（可在下方"
                   "录入为专业安排进行跟踪）；本系统的记录与提醒仅作辅助。")
    else:
        mild = severity is not None and isinstance(severity, (int, float)) \
            and severity <= 4 and (days is None or days < 7)
        if mild:
            action = "general_information"
            message = GENERAL_MILD["message"]
        else:
            action = "uncertain"
            message = UNCERTAIN["message"]

    hint = next((h for h in hints if h), None) if action != "general_information" \
        else (hints[0] if hints else None)
    return {
        "action": action,
        "matched_rules": matched,
        "message": message,
        "restriction_hint": hint,
        "rules_version": RULES_VERSION,
        "review_status": REVIEW_STATUS,
        "disclaimer": "分流结果仅用于信息提示，不构成医学诊断或治疗建议",
    }


def recommended_region_restriction(body_region: str, side: str | None,
                                   action: str) -> dict | None:
    """按分流结果给出建议限制的范围（仅 triage_recommended 来源）。"""
    if action == "general_information":
        return None
    return {"regions": [body_region], "movements": [], "notes":
            (f"{body_region}{('（' + side + '）') if side else ''}相关训练"
             f"{'暂停' if action == 'urgent_evaluation' else '保守安排'}")}
