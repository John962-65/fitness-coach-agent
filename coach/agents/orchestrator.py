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
    """给专家的用户上下文：档案摘要 + 简短复盘。控制长度，避免专家提示过载。"""
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
    return f"{summary}\n{review}"


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


def consult_specialists(db, llm, user_id: str, question: str) -> dict:
    """主教练咨询入口：路由 → 咨询 → 汇总 → 留痕（agent_consultations）。"""
    keys = route_question(question)
    if not keys:
        return {"consulted": [], "advices": [], "conflicts": [],
                "note": "简单或非专业问题：未咨询专家，由主教练直接回答"}
    context = _context_for(db, user_id, question)
    advices = []
    for key in keys:  # 串行调用（单用户本地服务，避免并发写库竞争）
        advices.append(consult_one(llm, key, question, context))
    combined = combine(advices)
    db.add_consultation(user_id, question, keys, combined["advices"])
    return {"consulted": keys, **combined}
