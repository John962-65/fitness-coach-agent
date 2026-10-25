"""安全集成：统一限制视图（多来源合并取最严，单一事实供全部模块读取）。

优先级规则（P3-0 审计后确定，不与 training_permission 矛盾）：
1. 医疗许可（training_permission）：prohibited/pending 时整体禁处方——最高优先；
2. plan_fence（计划隔离）：沿用既有行为（编辑一律拒绝）；
3. TrainingRestriction：active 限制按 affected_activities 收紧动作选择——
   多条限制并存时**全部生效**（限制是并集，不是取一条最宽），来源之间
   互不覆盖：某个专家没发现风险，不能覆盖另一个来源中明确存在的限制；
4. 任何模块不得依据自身判断放宽以上任何一层。

本模块返回的组合视图供：
- changes._validate_plan（计划修改安全校验，服务端强制）；
- 训练科学/恢复/动作技术顾问读取（尊重限制）；
- 康复工作台展示。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..medical import training_permission
from . import restriction_service

SOURCE_LABEL = {"user_reported": "用户自行报告",
                "professional": "专业人员给出",
                "triage_recommended": "系统安全分流提示（待确认）"}


@dataclass
class SafetyView:
    permission_status: str          # prohibited / pending / limited / allowed
    permission_reason: str
    permission_evidence: str
    allows_prescription: bool
    plan_fenced: bool
    fence_reason: str
    active_restrictions: list = field(default_factory=list)

    @property
    def prescription_blocked(self) -> bool:
        return not self.allows_prescription or self.plan_fenced

    def summary_lines(self) -> list[str]:
        lines = []
        if not self.allows_prescription:
            lines.append(f"医疗许可：{self.permission_status}（{self.permission_reason}）")
        if self.plan_fenced:
            lines.append(f"计划已隔离：{self.fence_reason}")
        for r in self.active_restrictions:
            aff = r["affected_activities"] or {}
            regions = "、".join(aff.get("regions") or []) or "指定动作"
            lines.append(f"[{SOURCE_LABEL.get(r['source_type'], r['source_type'])}] "
                         f"{regions}：{r['restriction_description']}")
        return lines


def safety_view(db, user_id: str) -> SafetyView:
    profile = db.get_existing_profile(user_id) or {}
    permission = training_permission(profile)
    fence = profile.get("plan_fence")
    return SafetyView(
        permission_status=permission.status,
        permission_reason=permission.reason,
        permission_evidence=permission.evidence,
        allows_prescription=permission.allows_prescription,
        plan_fenced=bool(fence),
        fence_reason=(fence or {}).get("reason", "未知原因") if fence else "",
        active_restrictions=restriction_service.effective_restrictions(db, user_id),
    )


def validate_plan_change(db, user_id: str, exercise_docs: list[dict]) -> list[str]:
    """计划修改的限制校验（在医疗许可/隔离之后调用）。返回拒绝原因列表。"""
    errors: list[str] = []
    view = safety_view(db, user_id)
    if not view.active_restrictions:
        return errors
    for doc in exercise_docs:
        hit = restriction_service.restriction_blocks(db, user_id, doc)
        if hit:
            r = hit["restriction"]
            errors.append(
                f"动作「{doc.get('name')}」与当前训练限制冲突：{hit['reason']}；"
                f"限制依据：{r['restriction_description']}"
                f"（{SOURCE_LABEL.get(r['source_type'], r['source_type'])}，"
                f"生效于 {r['effective_at'][:10]}）——如情况变化请先在康复工作台"
                f"处理该限制（专业人员限制需附专业人员说明）")
    return errors
