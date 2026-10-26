"""P6：联合建议的用户决策服务（decision_service）。

联合建议首先是只读结果。允许的用户决定：
- ignore      → 忽略报告（洞察 dismiss）
- observe     → 继续观察（标记已读，不产生任何修改）
- propose     → 申请长期调整（仅当所选方案携带服务端构造的提案提示，
                走 ChangeProposal 确认协议；确认前计划不变）
其他任何决定都不修改计划；"仅本次采用"涉及训练会话，由训练页面在
读取具体候选时完成（P5-C 通道），本服务不代写会话。
"""
from __future__ import annotations

from ..changes import ProposalRejected
from ..experts import insight_service, recommendation_service

ALLOWED = ("ignore", "observe", "propose")


def record_decision(db, user_id: str, insight_id: str, decision: str,
                    option_id: str | None = None) -> dict:
    if decision not in ALLOWED:
        raise ValueError(f"decision 必须是 {'/'.join(ALLOWED)} 之一")
    insight = insight_service.get_insight(db, user_id, insight_id)
    if not insight:
        raise ValueError("联合分析不存在")
    if insight.get("insight_type") != "collaboration-review":
        raise ValueError("该决策服务只处理跨专家协作报告")
    if decision == "ignore":
        updated = insight_service.dismiss(db, user_id, insight_id)
        return {"decision": "ignore", "status": updated["status"],
                "note": "已忽略报告；可重新分析"}
    if decision == "observe":
        updated = insight_service.mark_viewed(db, user_id, insight_id)
        return {"decision": "observe", "status": updated["status"],
                "note": "继续观察：未产生任何修改"}
    # propose：必须指定方案，且方案必须由服务端构造过提案操作
    if not option_id:
        raise ValueError("propose 需要指定 option_id")
    try:
        staged = recommendation_service.stage_option_proposal(
            db, user_id, insight_id, option_id)
    except ProposalRejected:
        raise
    except ValueError as e:
        raise ValueError(f"该方案不能生成长期修改提案：{e}") from None
    return {"decision": "propose", "status": "pending",
            "proposal_id": staged["proposal"]["proposal_id"],
            "note": staged.get("note")}
