"""P6：跨专家协作——模型与结构契约（2.0 §2.2 扩展）。

CollaborationReport 以 `collaboration-review` 类型 ExpertInsight 持久化
（复用任务队列、生命周期、证据校验与 options），不建第二套系统。
本模块只定义结构构造器与校验，不写业务规则。
"""
from __future__ import annotations

DOMAINS = ("training", "nutrition", "body", "recovery",
           "rehabilitation", "movement")

COLLAB_RULES_VERSION = "p6-collab-rules-v1"


def evidence_item(*, fact_id: str, domain: str, metric: str, value,
                  unit: str, time_window: dict, source_ids: list,
                  source_revisions: dict, calculation: str,
                  data_quality: dict, limitations: list) -> dict:
    """跨领域事实条目（CrossDomainEvidence）。"""
    if domain not in DOMAINS:
        raise ValueError(f"未知领域 {domain!r}")
    return {
        "fact_id": str(fact_id), "domain": domain, "metric": metric,
        "value": value, "unit": unit, "time_window": time_window,
        "source_ids": list(source_ids), "source_revisions": source_revisions,
        "calculation": calculation, "data_quality": dict(data_quality),
        "limitations": list(limitations),
    }


def specialist_opinion(*, specialist: str, question: str,
                       directions: list[dict], observations: list[str],
                       interpretations: list[str], recommendations: list[str],
                       evidence_refs: list[str], limitations: list[str]) -> dict:
    """专家意见（SpecialistOpinion）。

    directions 是结构化的观点方向（供冲突裁决的确定性规则使用）：
    {"direction": "...", "basis_fact_ids": [...], "note": "..."}。
    每位顾问只对自己的领域发言；不要求意见一致。
    """
    return {
        "specialist": specialist, "question": question,
        "directions": directions,
        "observations": observations, "interpretations": interpretations,
        "recommendations": recommendations,
        "evidence_refs": evidence_refs, "limitations": limitations,
    }


def collaboration_report(*, scenario: str, question: str, participants: list,
                         shared_facts: list, specialist_opinions: list,
                         agreements: list, disagreements: list, unknowns: list,
                         candidate_options: list, decision_requirements: list,
                         safety_gates: list, source_revisions: dict) -> dict:
    """联合分析报告（CollaborationReport）。"""
    return {
        "kind": "collaboration_report_v1",
        "rules_version": COLLAB_RULES_VERSION,
        "scenario": scenario, "question": question,
        "participants": participants,
        "shared_facts": shared_facts,
        "specialist_opinions": specialist_opinions,
        "agreements": agreements, "disagreements": disagreements,
        "unknowns": unknowns,
        "candidate_options": candidate_options,
        "decision_requirements": decision_requirements,
        "safety_gates": safety_gates,
        "source_revisions": source_revisions,
    }
