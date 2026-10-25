"""M2 主教练编排：确定性路由 + 并发咨询 + 冲突并列。

路由是确定性关键词匹配（不调 LLM）——"简单问题只调用必要智能体"由
代码保证，不赌模型行为；复合问题命中多类专家时全部咨询，分歧并列
保留（2.0 §6.6），由主教练向用户呈现取舍，不自动评赢家。
"""
from __future__ import annotations

from ..profile import profile_summary
from .specialists import SPECIALISTS, consult_one

# 确定性路由关键词（按专家；一个问句可命中多类 → 并行咨询）
ROUTE_KEYWORDS = {
    "nutrition": ("营养", "饮食", "吃", "蛋白", "热量", "卡路里", "碳水",
                  "脂肪", "补剂", "肌酸", "减脂餐", "食谱", "份量", "空腹"),
    "recovery": ("恢复", "睡眠", "睡", "失眠", "疲劳", "酸痛", "困", "累", "休息日",
                 "deload", "卸载", "减量"),
    "movement": ("动作", "姿势", "发力", "标准", "教学", "幅度", "站距",
                 "握距", "膝盖内扣", "塌腰", "骨盆"),
    "training_science": ("计划", "训练安排", "容量", "组数", "次数", "分化",
                         "周期", "进阶", "加重", "平台期", "练几", "频率",
                         "全身", "上下肢", "推拉腿"),
    "knowledge": ("知识", "观点", "博主", "文献", "研究", "说法", "有没有科学",
                  "谁说得对"),
}

# 简单问题（寒暄/单句汇报类）零咨询——由主教练直接回答
_SIMPLE_PATTERNS = ("你好", "您好", "谢谢", "再见", "好的", "嗯嗯", "哈哈",
                    "在吗", "hi", "hello", "ok", "测试")


def route_question(question: str) -> list[str]:
    """确定性路由：返回要咨询的专家 key 列表（按 SPECIALISTS 定义顺序去重）。"""
    text = str(question or "").strip().lower()
    if not text or len(text) <= 2 or any(p in text.lower() for p in _SIMPLE_PATTERNS):
        return []
    if text.endswith("?") or text.endswith("？"):  # 单句短提问交给主教练
        if len(text) <= 6:
            return []
    matched = [key for key, words in ROUTE_KEYWORDS.items()
               if any(w in text for w in words)]
    # 保序：按 SPECIALISTS 定义顺序稳定输出
    return [k for k in SPECIALISTS if k in matched]


def _context_for(db, user_id: str, question: str) -> str:
    """给专家的用户上下文：档案摘要 + 简短复盘 + 训练事实摘要（M6.5）。
    控制长度，避免专家提示过载。"""
    try:
        profile = db.get_existing_profile(user_id) or {}
        summary = profile_summary(profile)
    except Exception:
        summary = "（档案不可用）"
    try:
        from ..review import review_context_text
        review = review_context_text(db, user_id, db.get_active_plan(user_id))
        review = review[:600]
    except Exception:
        review = ""
    context = f"{summary}\n{review}"
    # M6.5-3：训练科学/恢复类问题附带结构化训练事实（可追溯，专家引用须基于此）
    keys = route_question(question)
    if "training_science" in keys or "recovery" in keys:
        try:
            from ..analytics.fact_service import get_training_facts
            facts = get_training_facts(db, user_id, 30)
            lines = []
            for f in facts["facts"]:
                if f["metric"] in ("sessions", "working_sets", "volume",
                                   "training_days", "plan-adherence",
                                   "best-estimated-1rm", "max-reps",
                                   "longest-set", "farthest-distance",
                                   "min-assistance-kg", "rpe-average"):
                    ex = f.get("exercise_id") or "全站"
                    val = f["value"] if f["value"] is not None else "不足"
                    lines.append(f"- {ex}·{f['metric']}={val}{f['unit']}"
                                 f"（{f['status']}）")
            if lines:
                context += ("\n\n# 训练事实（fact_service，30 天窗口；status:"
                            "observed=记录/estimated=估算/insufficient=数据不足）\n"
                            + "\n".join(lines[:18]))
        except Exception:
            pass
    return context


def combine(advices: list[dict]) -> dict:
    """汇总各专家建议：分歧并列标注，不合并、不评赢家。"""
    conflicts = []
    with_options = [a for a in advices if a.get("options")]
    if len(with_options) > 1:
        labels = "、".join(a["label"] for a in with_options)
        conflicts.append(
            f"{labels} 都给出了候选方案：并列保留各自的适用条件，"
            "由用户结合自身情况选择，不自动裁决")
    return {"advices": advices, "conflicts": conflicts}


def _knowledge_context(db, user_id: str, question: str) -> tuple[str, list[dict]]:
    """M5.1 P1-4：专家建议前必经统一知识检索——命中(带来源与状态)注入
    专家提示，并作为 knowledge_refs 随建议留痕（可追溯）。"""
    from ..knowledge_search import search
    try:
        result = search(db, user_id, question)
    except Exception:
        return "", []
    refs, lines = [], []
    for engine, payload in (result.get("engines") or {}).items():
        for hit in payload.get("hits") or []:
            refs.append({"engine": engine, "ref": hit.get("ref"),
                         "provenance": hit.get("provenance"),
                         "title": hit.get("title")})
            lines.append(f"[{engine}] {hit.get('ref')} {hit.get('title')}"
                         f"（来源:{hit.get('provenance')}）：{hit.get('snippet')}")
        draft = (payload or {}).get("draft_matches")   # M5.2 修复：循环内逐引擎读取
        if draft:
            lines.append(f"[{engine}] 另有 {draft} 条草稿命中，审核通过前不得引用内容")
    return "\n".join(lines[:12]), refs[:12]


def consult_specialists(db, llm, user_id: str, question: str) -> dict:
    """主教练咨询入口：路由 → 统一知识检索 → 咨询 → 汇总 → 留痕。

    每位专家的提示都附带检索命中的知识上下文（含出处与可信状态）；
    knowledge_refs 随建议落库 agent_consultations——建议可追溯到知识来源。
    """
    keys = route_question(question)
    if not keys:
        return {"consulted": [], "advices": [], "conflicts": [], "knowledge_refs": [],
                "note": "简单或非专业问题：未咨询专家，由主教练直接回答"}
    context = _context_for(db, user_id, question)
    knowledge_text, knowledge_refs = _knowledge_context(db, user_id, question)
    if knowledge_text:
        context += ("\n\n# 相关知识检索命中（citations 引用其 ref，形如 engine:ref；"
                    "草稿来源不得当结论）\n" + knowledge_text)
    valid_refs = {f"{r['engine']}:{r['ref']}" for r in knowledge_refs}
    first_ref = next(iter(sorted(valid_refs)), "")
    advices = []
    for key in keys:  # 串行调用（单用户本地服务；并行化属后续优化）
        advice = consult_one(llm, key, question, context, first_ref)
        advice = _bind_citations(advice, valid_refs)
        advice["knowledge_refs"] = knowledge_refs
        advices.append(advice)
    combined = combine(advices)
    db.add_consultation(user_id, question, keys, combined["advices"])
    return {"consulted": keys, "knowledge_refs": knowledge_refs, **combined}


def _bind_citations(advice: dict, valid_refs: set[str]) -> dict:
    """证据绑定（P1）：每个 option 的 citations 校验属于本轮检索命中；
    编造引用剔除；无任何合法引用的 option 标记 evidence='inferred'（推断）。
    """
    for opt in advice.get("options") or []:
        kept = [c for c in (opt.get("citations") or []) if c in valid_refs]
        opt["citations"] = kept
        opt["evidence"] = "cited" if kept else "inferred"
    return advice
