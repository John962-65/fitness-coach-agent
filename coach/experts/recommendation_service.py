"""建议服务：专家方案的呈现与（可选的）修改提案暂存。

边界（2.0 §2.4、§十）：
- 洞察里的 options 只是参考方向，永远由用户选择；
- 选中"action=proposal"的方案时，走既有统一修改协议的 AI 路径：
  stage_ai（同一套确定性校验：安全门/乐观锁/结构校验）→ pending →
  用户明确确认（changes.confirm_proposal 语义门）才生效；
- 顾问不能绕过确认协议直接写计划/训练方式（本模块是唯一桥梁，
  且只调 stage_ai，从不调用 _apply）。
"""
from __future__ import annotations

from ..changes import ProposalRejected, stage_ai


def get_option(insight: dict, option_id: str) -> dict | None:
    return next((o for o in insight.get("options") or []
                 if o.get("option_id") == option_id), None)


def stage_option_proposal(db, user_id: str, insight_id: str,
                          option_id: str) -> dict:
    """把洞察中的某个方案暂存为待确认修改提案（AI 来源）。

    返回 stage_ai 的结果（proposal_id + pending）；确认仍在
    POST /users/{uid}/changes/{id}/confirm —— 与聊天链路同一道门。
    """
    from . import insight_service
    insight = insight_service.get_insight(db, user_id, insight_id)
    if not insight:
        raise ValueError("分析不存在")
    if insight["status"] not in ("ready", "viewed"):
        raise ValueError(f"状态为 {insight['status']} 的分析不能再生成修改提案"
                         "（可先重新分析）")
    option = get_option(insight, option_id)
    if not option:
        raise ValueError("方案不存在")
    hint = option.get("proposal_hint")
    if not hint or hint.get("target") not in ("plan", "approach"):
        raise ValueError("该方案是参考说明，不包含可执行的修改操作")
    record = db.get_active_plan_record(user_id) if hint["target"] == "plan" else None
    base_version = ({"plan_id": record["id"], "plan_version": record["version"]}
                    if record else
                    {"approach_revision": (db.get_approach(user_id) or {}).get("revision")})
    reason = (f"训练科学工作台 · 分析 {insight['id'][4:12]} 方案「{option['title']}」"
              f"（置信度 {insight['confidence']}，依据见分析详情）")
    try:
        result = stage_ai(db, user_id, hint["target"], hint["operations"],
                          reason, base_version)
    except ProposalRejected:
        raise
    return {"proposal": result, "insight_id": insight_id,
            "option_id": option_id,
            "note": "提案已暂存（pending）：需你在修改确认区明确确认后才会生效"}
