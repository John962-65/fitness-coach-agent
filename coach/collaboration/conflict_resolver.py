"""P6：意见冲突与协作裁决（conflict_resolver）。

原则：
- 不采用多数投票；分歧被并列保留，由用户决定；
- 每条分歧展示：双方共同认可的事实、各自关注的风险、当前缺少的信息、
  维持现状的选择；
- P3 安全门优先级最高：任何建议不得覆盖安全限制；未知安全条件明确
  保留不确定性。
"""
from __future__ import annotations

from .models import COLLAB_RULES_VERSION

# 方向对 → 分歧类型（确定性规则表；未命中的方向组合视为可并列方向）
_TENSIONS = {
    frozenset({"maintain_or_progress", "observe_and_reduce_risk"}):
        "training-vs-recovery",
    frozenset({"investigate_decline", "observe_and_reduce_risk"}):
        "decline-vs-recovery",
}


def resolve(opinions: list[dict], bundle: dict) -> dict:
    agreements: list[dict] = []
    disagreements: list[dict] = []
    unknowns: list[dict] = []
    safety_gates: list[dict] = []

    by_specialist = {o["specialist"]: o for o in opinions}

    # 安全门（最高优先级，不可被覆盖）
    rehab = by_specialist.get("rehabilitation")
    if rehab:
        for d in rehab["directions"]:
            if d["direction"] == "safety_gate":
                safety_gates.append({
                    "source": "rehabilitation",
                    "basis_fact_ids": d["basis_fact_ids"],
                    "note": d["note"],
                })

    # 两两方向张力（确定性规则表）
    specs = [o for o in opinions if o["specialist"] != "rehabilitation"]
    for i, a in enumerate(specs):
        for b in specs[i + 1:]:
            for da in a["directions"]:
                for db_ in b["directions"]:
                    pair = frozenset({da["direction"], db_["direction"]})
                    kind = _TENSIONS.get(pair)
                    if kind:
                        shared = sorted(set(da["basis_fact_ids"])
                                        & set(db_["basis_fact_ids"]))
                        disagreements.append({
                            "kind": kind,
                            "between": [a["specialist"], b["specialist"]],
                            "positions": [
                                {"specialist": a["specialist"],
                                 "direction": da["direction"],
                                 "note": da["note"],
                                 "basis_fact_ids": da["basis_fact_ids"]},
                                {"specialist": b["specialist"],
                                 "direction": db_["direction"],
                                 "note": db_["note"],
                                 "basis_fact_ids": db_["basis_fact_ids"]},
                            ],
                            "shared_facts": shared,
                            "missing_information": _missing_for(kind),
                            "maintain_option": "维持现状并继续观察始终可选",
                        })
    # 同向共识
    for i, a in enumerate(specs):
        for b in specs[i + 1:]:
            for da in a["directions"]:
                for db_ in b["directions"]:
                    if da["direction"] == db_["direction"] and \
                            da["direction"] not in ("insufficient_data",):
                        agreements.append({
                            "direction": da["direction"],
                            "between": [a["specialist"], b["specialist"]],
                            "basis_fact_ids": sorted(
                                set(da["basis_fact_ids"])
                                | set(db_["basis_fact_ids"])),
                        })

    # 数据不足 → unknowns（不解释为正常值或零值）
    for o in opinions:
        for d in o["directions"]:
            if d["direction"] == "insufficient_data":
                unknowns.append({
                    "specialist": o["specialist"],
                    "note": d["note"],
                    "limitations": o["limitations"],
                })

    return {"agreements": agreements, "disagreements": disagreements,
            "unknowns": unknowns, "safety_gates": safety_gates,
            "rules_version": COLLAB_RULES_VERSION}


def _missing_for(kind: str) -> list[str]:
    if kind == "training-vs-recovery":
        return ["更高频的恢复自报（当前窗口样本可能不足）",
                "训练质量与 RPE 记录",
                "睡眠与饮食记录完整度"]
    if kind == "decline-vs-recovery":
        return ["表现下行的持续时间（单次下行不构成趋势）",
                "同期计划/生活变化记录"]
    return ["更多纵向数据"]
