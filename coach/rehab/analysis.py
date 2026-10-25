"""康复顾问确定性分析器：SymptomReported/Updated → 症状回顾洞察。

内容纪律：
- 输出 = 症状事实（事件/观察/变化）+ 分流结果（引用规则版本）+ 当前限制
  + 已登记的专业安排；不含诊断、不含训练处方；
- 教育引用仅限一般性常识说明（写入 findings，标注非处方）；
- source_revision 记录症状/限制版本——记录变化即失效。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import restriction_service, triage_rules
from .symptom_service import REGION_LABELS

EXPIRE_DAYS = 7


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fact(fact_id, metric, value, unit, window, source_ids, calculation,
          status="observed", **quality):
    return {"fact_id": fact_id, "metric": metric, "value": value, "unit": unit,
            "measurement_type": "rehab", "window": window,
            "source_ids": source_ids, "calculation": calculation,
            "data_quality": quality or {}, "status": status}


def analyze_symptom_review(db, user_id: str, input_refs: dict) -> dict:
    episodes = db.list_symptom_episodes(user_id)
    active = [e for e in episodes if e["status"] == "active"]
    if not active and not episodes:
        raise ValueError("没有任何症状记录，无可分析内容")
    focus = next((e for e in active
                  if input_refs.get("episode_id") in (None, e["id"])), None) \
        or (db.get_symptom_episode(user_id, input_refs["episode_id"])
            if input_refs.get("episode_id") else None) \
        or active[0] if (active or episodes) else None
    if focus is None:
        focus = episodes[0]
    observations = db.list_symptom_observations(user_id, focus["id"])
    restrictions = restriction_service.effective_restrictions(db, user_id)
    related = [r for r in restrictions if r.get("related_episode_id") == focus["id"]]
    care_plans = [p for p in db.list_care_plans(user_id)
                  if p.get("status") == "active"
                  and (p.get("related_episode_id") == focus["id"]
                       or p.get("related_episode_id") is None)]

    window = {"start": focus["onset_at"], "end": _now()[:10],
              "days": None, "label": "事件窗口"}
    srcs = [f"symptom:{focus['id']}:obs:{o['id']}" for o in observations]
    findings: list[dict] = []
    facts: list[dict] = []

    # 事实：事件基本盘 + 程度变化（可计算的观察）
    region = REGION_LABELS.get(focus["body_region"], focus["body_region"])
    side = {"left": "左侧", "right": "右侧", "bilateral": "双侧"}.get(
        focus.get("side"), "")
    facts.append(_fact(
        f"episode-{focus['id']}", "symptom-episode", region + side, "", window,
        [f"symptom:{focus['id']}"], "active_episode_identity",
        note=f"起病 {focus['onset_at']}；观察 {len(observations)} 次"))
    findings.append({
        "finding_id": "f-episode", "kind": "episode-baseline",
        "text": (f"当前不适事件：{region}{side}，起病 {focus['onset_at']}"
                 f"（{focus.get('onset_context') or '自述逐渐出现'}）。"
                 f"你的描述：{focus['description'][:120]}"),
        "fact_ids": [f"episode-{focus['id']}"], "source_ids": [f"symptom:{focus['id']}"]})
    severities = [o["severity"] for o in observations if o.get("severity") is not None]
    if len(severities) >= 2:
        trend = "上升" if severities[-1] > severities[0] \
            else "下降" if severities[-1] < severities[0] else "持平"
        facts.append(_fact(
            f"severity-trend-{focus['id']}", "severity-trend", trend,
            f"（{severities[0]}→{severities[-1]}，{len(severities)} 次自报）",
            window, srcs, "first_vs_last_self_reported_severity",
            note="自报程度变化是观察，不等于损伤变化"))
        findings.append({
            "finding_id": "f-severity-trend", "kind": "severity-trend",
            "text": f"自报程度变化：{severities[0]} → {severities[-1]}"
                    f"（共 {len(severities)} 次记录，{trend}）。"
                    "这是你的主观记录，不构成对损伤变化的判断。",
            "fact_ids": [f"severity-trend-{focus['id']}"], "source_ids": srcs})
    # 最近一次分流结果
    latest_triage = observations[-1].get("triage_result") if observations else None
    if latest_triage:
        findings.append({
            "finding_id": "f-triage", "kind": "triage-result",
            "text": (f"最近一次安全分流：{latest_triage['action']}"
                     f"（规则 {latest_triage.get('rules_version')}，"
                     f"{latest_triage.get('review_status')}）。"
                     f"{latest_triage['message']}"),
            "fact_ids": [], "source_ids": srcs[-1:]})
    # 功能限制
    limits = [l for o in observations for l in (o.get("functional_limitations") or [])]
    if limits:
        findings.append({
            "finding_id": "f-functional", "kind": "functional-limitations",
            "text": f"你报告的功能影响：{'、'.join(dict.fromkeys(limits))}",
            "fact_ids": [], "source_ids": srcs})

    # 当前限制（含本事件关联 + 其他来源）
    for r in related or restrictions:
        aff = r["affected_activities"] or {}
        src_label = {"user_reported": "用户自行报告",
                     "professional": "专业人员给出",
                     "triage_recommended": "安全分流提示（待你确认）"}.get(
            r["source_type"], r["source_type"])
        findings.append({
            "finding_id": f"f-restriction-{r['id']}", "kind": "restriction",
            "text": (f"训练限制[{src_label}]：{r['restriction_description']}"
                     f"（覆盖：{'、'.join(aff.get('regions') or []) or '指定动作'}；"
                     f"生效 {r['effective_at'][:10]}）"
                     + (f"；复核时点 {r['review_at']}" if r.get("review_at") else "")
                     + "。训练科学/恢复/动作技术顾问都会遵守该限制。"),
            "fact_ids": [], "source_ids": [f"restriction:{r['id']}"]})

    # 专业安排（执行跟踪入口提示）
    for p in care_plans:
        findings.append({
            "finding_id": f"f-care-{p['id']}", "kind": "care-plan",
            "text": f"专业安排「{p['title']}」（来源：{p['professional_source']}）"
                    "进行中——活动执行记录请在该安排卡片内更新。",
            "fact_ids": [], "source_ids": [f"care_plan:{p['id']}"]})

    options = [{
        "option_id": "follow-restriction", "title": "遵守当前限制，观察变化",
        "detail": "按分流提示与限制安排活动；在事件下继续记录观察（程度/功能影响），"
                  "变化会实时反映到分流结果。",
        "basis": [f"episode-{focus['id']}"],
        "tradeoffs": {"收益": "不给未评估的组织额外负荷",
                      "代价": "训练连续性受影响",
                      "适用条件": "分流结果未变化时"},
    }]
    if not any(f["kind"] == "triage-result" and "urgent" in f["text"]
               for f in findings):
        options.append({
            "option_id": "seek-evaluation", "title": "寻求专业评估（如尚未评估）",
            "detail": "如果不适持续、加重或影响日常活动，请咨询医生或物理治疗师；"
                      "获得专业意见后可录入为「专业安排」进行执行跟踪。",
            "basis": [],
            "tradeoffs": {"收益": "获得个体化的专业判断",
                          "代价": "时间与费用",
                          "适用条件": "症状持续/加重/影响生活时尤其建议"},
        })
    options.append({
        "option_id": "record-professional-plan", "title": "录入专业人员的安排并跟踪执行",
        "detail": "已经获得专业人员建议的，把活动与频率录入系统，软件只做记录"
                  "与提醒，不会自行提高强度或次数。",
        "basis": [],
        "tradeoffs": {"收益": "执行情况可视、便于复诊沟通",
                      "代价": "需要记录投入",
                      "适用条件": "已有专业人员建议时"},
    })

    limitations = [
        "本分析不构成医学诊断或治疗建议；分流结果仅用于信息提示",
        f"安全分流规则 {triage_rules.RULES_VERSION} 为系统默认版本，"
        "尚待专业人员审核（审核缺口见交付文档）",
        "未报告危险症状不代表没有风险；信息不足时分流为 uncertain",
    ]
    if not observations:
        limitations.append("该事件还没有后续观察记录")

    src_revision = {"symptoms": db.symptoms_version(user_id),
                    "restrictions": restriction_service.restrictions_version(db, user_id)}
    region_title = REGION_LABELS.get(focus["body_region"], focus["body_region"])
    return {
        "specialist": "rehabilitation",
        "insight_type": "symptom-review",
        "title": f"不适回顾 · {region_title}{side}（{focus['onset_at']} 起）",
        "summary": (f"{len(observations)} 次观察记录；"
                    f"最近分流：{latest_triage['action'] if latest_triage else '未分流'}；"
                    f"{len(restrictions)} 条训练限制生效。"),
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        "facts_snapshot": {"window": window, "facts": facts,
                           "caliber": "症状事件与自报记录的确定性汇总；分流引用"
                                      "规则版本，无诊断"},
        "knowledge_refs": [],
        "options": options,
        "limitations": limitations,
        "confidence": "medium" if len(observations) >= 2 else "low",
        "confidence_basis": (f"置信度规则=观察记录 {len(observations)} 次"
                             f"（≥2 次=medium，1 次=low；症状数据不做 high 声明）"),
        "generated_at": _now(),
        "expires_at": (datetime.now() + timedelta(days=EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": src_revision,
        "input_refs": dict(input_refs or {}),
    }
