"""M2 专业 Agent 定义：五个专家（训练科学/营养/恢复/动作/知识研究）。

每个专家 = 角色系统提示 + 统一结构化输出（AgentAdvice）。输出经
parse_advice 确定性校验：缺字段补空、类型不符丢弃该字段，绝不把
模型自由文本当结构化建议使用。FAKE_LLM 模式返回按专家固定的确定性
建议（离线测试/开发用）。
"""
from __future__ import annotations

import json
import re

# 统一建议格式（2.0 §5.3）：当前问题/相关事实/知识依据/候选方案/适用条件/风险与不确定性/需用户确认
ADVICE_FIELDS = ("problem", "facts", "knowledge_basis", "options",
                 "conditions", "risks", "needs_confirmation")

SPECIALISTS = {
    "training_science": {
        "label": "训练科学",
        "prompt": (
            "你是训练科学专家，负责训练结构、容量、强度、周期与进阶分析。"
            "基于用户档案与数据给建议。遵守：不承诺具体数字效果；"
            "医疗相关问题一律建议咨询专业人员；建议必须给出适用条件。"
            "只输出 JSON：{\"problem\":str,\"facts\":[str],\"knowledge_basis\":[str],"
            "\"options\":[{\"title\":str,\"detail\":str,\"citations\":[str]}],"
            "\"conditions\":[str],\"risks\":[str],\"needs_confirmation\":[str]}。"
            "citations 填你实际依据的上下文 ref（形如 engine:ref）；"
            "没有依据的判断不要编造引用，留空数组"),
    },
    "nutrition": {
        "label": "营养",
        "prompt": (
            "你是营养专家，负责饮食方式、能量与营养素、个体饮食适配。"
            "不强制所有用户精确计算热量；不提供医学饮食治疗建议。"
            "只输出与前述相同的 JSON 结构（options 每项含 citations：填实际依据的上下文 ref，无依据留空数组，不要编造）。"),
    },
    "recovery": {
        "label": "恢复",
        "prompt": (
            "你是恢复专家，负责疲劳、睡眠、恢复与训练安排的平衡。"
            "区分数据观察与推测；医疗风险（如持续疼痛、心脏症状）必须建议就医，"
            "不用训练建议替代医疗评估。只输出与前述相同的 JSON 结构。"),
    },
    "movement": {
        "label": "动作",
        "prompt": (
            "你是动作教学专家，负责动作技术、常见错误与自我检查。"
            "引用动作库与已审核教练卡内容时注明来源；不可见/无法判断的动作问题"
            "如实说明，不猜。只输出与前述相同的 JSON 结构。"),
    },
    "knowledge": {
        "label": "知识研究",
        "prompt": (
            "你是知识研究专家，负责比较不同来源的观点、识别分歧与适用条件。"
            "观点分歧时并列保留双方及出处，不判赢家；未经审核的内容不得作为"
            "处方依据。只输出与前述相同的 JSON 结构。"),
    },
}

# FAKE 模式的确定性建议（按专家固定，保证测试可断言）
_FAKE_ADVICE = {
    "training_science": {
        "problem": "训练安排问题", "facts": ["每周训练 3 次"],
        "knowledge_basis": ["槽位式计划生成原则"],
        "options": [{"title": "维持当前分化", "detail": "进步稳定时不换结构"},
                    {"title": "评估容量", "detail": "连续 2 周无进步再调"}],
        "conditions": ["无未解除的伤病隔离"], "risks": ["改变过快难归因"],
        "needs_confirmation": ["是否调整计划需用户确认"]},
    "nutrition": {
        "problem": "营养问题", "facts": ["目标：增肌"],
        "knowledge_basis": ["营养知识层（L1 原则）"],
        "options": [{"title": "足量蛋白", "detail": "每公斤体重 1.6-2.2g 量级，因人而异"}],
        "conditions": ["无特殊医嘱"], "risks": ["精确计算负担高可先用份量法"],
        "needs_confirmation": ["当前饮食方式是否要调整"]},
    "recovery": {
        "problem": "恢复问题", "facts": ["睡眠数据未记录"],
        "knowledge_basis": ["恢复原则：疲劳管理优先于加量"],
        "options": [{"title": "观察一周", "detail": "记录主观疲劳与静息状态再决定"}],
        "conditions": ["无持续疼痛"], "risks": ["带痛硬练属风险"],
        "needs_confirmation": ["是否进入低负荷周"]},
    "movement": {
        "problem": "动作技术问题", "facts": ["涉及动作已在库内"],
        "knowledge_basis": ["动作库教学字段（未逐条绑定出处时如实说明）"],
        "options": [{"title": "自检清单", "detail": "按教学要点逐项对照"}],
        "conditions": ["有视频或现场反馈更准"], "risks": ["仅凭描述判断有限"],
        "needs_confirmation": ["是否上传视频做分析"]},
    "knowledge": {
        "problem": "知识问题", "facts": ["多来源观点可能并存"],
        "knowledge_basis": ["知识库：分歧并列保留规则（§6.6）"],
        "options": [{"title": "并列呈现", "detail": "不同说法连同出处一起给用户"}],
        "conditions": ["未经审核内容不作为处方依据"],
        "risks": ["断章取义"], "needs_confirmation": ["用户想深入哪个来源"]},
}


def _clean_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip()[:200] for x in value if str(x).strip()][:8]


def parse_advice(raw: str, specialist: str) -> dict:
    """模型输出 → 结构化 AgentAdvice。非法 JSON/字段按缺省处理，不抛出。"""
    advice = {field: ([] if field != "problem" else "")
              for field in ADVICE_FIELDS}
    advice["specialist"] = specialist
    advice["label"] = SPECIALISTS[specialist]["label"]
    if not raw:
        return advice
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return advice
    try:
        data = json.loads(m.group())
    except ValueError:
        return advice
    if not isinstance(data, dict):
        return advice
    if isinstance(data.get("problem"), str):
        advice["problem"] = data["problem"][:300]
    for field in ("facts", "knowledge_basis", "conditions", "risks",
                  "needs_confirmation"):
        advice[field] = _clean_str_list(data.get(field))
    options = []
    for opt in data.get("options") or []:
        if isinstance(opt, dict) and isinstance(opt.get("title"), str):
            options.append({"title": str(opt["title"])[:120],
                            "detail": str(opt.get("detail", ""))[:400],
                            "citations": _clean_str_list(opt.get("citations"))})
        if len(options) >= 5:
            break
    advice["options"] = options
    return advice


def fake_advice(specialist: str, citation: str = "") -> dict:
    """FAKE_LLM 确定性建议（深拷贝避免测试间串改）。

    citation：本轮真实检索命中的第一条 ref —— FAKE 也要走证据绑定
    （第一个 option 引用它），不能凭空造引用。
    """
    import copy
    advice = copy.deepcopy(_FAKE_ADVICE[specialist])
    advice["specialist"] = specialist
    advice["label"] = SPECIALISTS[specialist]["label"]
    if citation and advice.get("options"):
        advice["options"][0]["citations"] = [citation]
    return advice


def consult_one(llm, specialist: str, question: str, context_text: str,
                fake_citation: str = "") -> dict:
    """咨询单个专家：一次 LLM 调用 → 结构化建议。"""
    system = SPECIALISTS[specialist]["prompt"]
    user = (f"用户问题：{question}\n\n用户上下文：\n{context_text}\n\n"
            "按系统要求只输出 JSON。")
    if getattr(llm, "fake", False):
        return fake_advice(specialist, fake_citation)
    resp = llm.chat([{"role": "system", "content": system},
                     {"role": "user", "content": user}])
    return parse_advice(resp.get("content") or "", specialist)
