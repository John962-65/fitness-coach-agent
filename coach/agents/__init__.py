"""M2 多智能体教练（DESIGN_2.0 §五）：主教练编排 + 专业 Agent。

原则（2.0 §5.3）：
- 按需调用：确定性路由决定咨询哪些专家，简单问题零调用；
- 结构化输出：每个专家产出统一 AgentAdvice（问题/事实/知识依据/候选方案/
  适用条件/风险/需确认事项）；
- 统一决策：专业 Agent 只出建议，绝不直接写用户数据——修改一律经
  统一修改协议（coach/changes.py）由用户确认后提交；
- 冲突处理：不同专家的分歧并列保留，不自动评赢家（2.0 §6.6）。
"""
from .orchestrator import consult_specialists, route_question
from .specialists import ADVICE_FIELDS, SPECIALISTS, parse_advice

__all__ = ["SPECIALISTS", "ADVICE_FIELDS", "parse_advice",
           "route_question", "consult_specialists"]
