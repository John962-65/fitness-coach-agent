"""恢复顾问确定性分析器：RecoveryRecorded / WorkoutSaved → 恢复回顾洞察。

纪律：
- 观察来自 recovery_metrics 的可计算结果（含训练负荷上下文，复用
  fact_service 同源口径）；"用户已过度训练"这类推断绝不输出；
- 不发明综合恢复评分；方案为可选方向（维持/调整当次/延后观察），
  不是指令；修改长期计划走 ChangeProposal 确认协议；
- 每条发现引用 recovery:/body:/训练 fact 的真实来源；数据缺失维度
  如实进入 limitations。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import recovery_metrics
from .checkin_service import SCALE_LABELS, version as day_version

EXPIRE_DAYS = 3


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _confidence(records_count: int, dims_reported: int,
                has_training: bool) -> tuple[str, str]:
    """置信度规则：窗口记录数 × 维度覆盖 × 负荷参照。"""
    if records_count >= 4 and dims_reported >= 3 and has_training:
        level = "high"
    elif records_count >= 2:
        level = "medium"
    else:
        level = "low"
    basis = (f"置信度规则=窗口记录 {records_count} 天、有记录维度 {dims_reported} 个、"
             f"训练负荷参照={'有' if has_training else '无'} → {level}")
    return level, basis


def analyze_recovery(db, user_id: str, input_refs: dict) -> dict:
    """恢复回顾（确定性）。input_refs 携带触发锚（不再用于取数）。"""
    snapshot = recovery_metrics.recovery_snapshot(db, user_id)
    records = snapshot["records"]
    if not records:
        raise ValueError("窗口内没有任何恢复记录，无可分析内容")

    window = snapshot["window"]
    facts = snapshot["facts"]
    fact_ids = {f["fact_id"] for f in facts}
    findings: list[dict] = []
    srcs = [f"recovery:{r['id']}:revision:{r['revision']}" for r in records]

    # ---- 发现：逐维度观察（带来源） ----
    for f in facts:
        if f["measurement_type"] == "recovery":
            findings.append({
                "finding_id": f"f-{f['fact_id']}",
                "kind": "recovery-observation",
                "text": (f"窗口均值 {f['value']}{f['unit']}——"
                         f"{f.get('note') or '自报记录汇总'}"
                         + (f"；其中高分报告 {f['data_quality']['high_reports']} 次"
                            if f["data_quality"].get("high_reports") else "")),
                "fact_ids": [f["fact_id"]], "source_ids": f["source_ids"]})
        elif f["measurement_type"] == "session":
            load_label = {"sessions": "训练次数", "working_sets": "正式组数",
                          "volume": "总容量", "rpe-average": "RPE 均值"
                          }.get(f["metric"], f["metric"])
            findings.append({
                "finding_id": f"f-{f['fact_id']}",
                "kind": "training-load-context",
                "text": (f"近 {window['days']} 天训练负荷：{load_label} "
                         f"{f['value']}{f['unit']}（训练事实同源口径）"),
                "fact_ids": [f["fact_id"]], "source_ids": f["source_ids"]})
    # 酸痛区域
    if snapshot["observations"] and any("酸痛区域" in o for o in snapshot["observations"]):
        region_obs = next(o for o in snapshot["observations"] if "酸痛区域" in o)
        findings.append({"finding_id": "f-soreness-regions", "kind": "soreness-regions",
                         "text": region_obs, "fact_ids": [], "source_ids": srcs})

    # ---- 方案（可选方向；永远含维持） ----
    latest = records[0]
    fatigue_high = (latest.get("fatigue") or 0) >= 4
    soreness_high = (latest.get("muscle_soreness") or 0) >= 4
    readiness_low = latest.get("training_readiness") is not None \
        and latest["training_readiness"] <= 2
    sleep_short = latest.get("sleep_hours") is not None and latest["sleep_hours"] < 6

    options = [{
        "option_id": "maintain-plan", "title": "按原计划继续训练",
        "detail": "恢复记录与训练负荷没有需要立刻改变安排的信号时，"
                  "按计划执行并继续记录是最省心的选择。",
        "basis": [f["fact_id"] for f in facts[:3]],
        "tradeoffs": {"收益": "不引入新变量，进步归因清晰",
                      "代价": "若状态确实较差，训练质量可能下降",
                      "适用条件": "无未解除的伤病限制；主观状态可接受"},
    }]
    if fatigue_high or soreness_high or sleep_short or readiness_low:
        signals = []
        if fatigue_high:
            signals.append(f"最新自报疲劳 {latest['fatigue']}/5")
        if soreness_high:
            signals.append(f"最新自报酸痛 {latest['muscle_soreness']}/5")
        if sleep_short and latest.get("sleep_hours") is not None:
            signals.append(f"最新自报睡眠 {latest['sleep_hours']:g} 小时")
        if readiness_low:
            signals.append(f"最新训练意愿 {latest['training_readiness']}/5")
        options.append({
            "option_id": "adjust-today", "title": "今天的训练量或强度调低一档",
            "detail": f"依据：{('；'.join(signals))}。这些是主观自报信号——"
                      "可选做法是把正式组数或顶组重量下调一档、取消冲击组，"
                      "完成质量优先。是否调整、调整多少由你当天决定。",
            "basis": [f["fact_id"] for f in facts
                      if f["measurement_type"] == "recovery"][:4],
            "tradeoffs": {"收益": "疲劳期降低伤病风险、保持训练连续性",
                          "代价": "当次刺激减少",
                          "适用条件": "仅当天下调，不改长期计划"},
        })
        options.append({
            "option_id": "delay-observe", "title": "今天休息，先观察一天",
            "detail": "若多个自报信号同时偏高（或出现异常疼痛），休息一天并把"
                      "感受记录下来也是正当选择；持续多日再考虑系统性减量。",
            "basis": [f["fact_id"] for f in facts
                      if f["measurement_type"] == "recovery"][:4],
            "tradeoffs": {"收益": "恢复优先；额外一天观察",
                          "代价": "少一次训练刺激",
                          "适用条件": "非备赛/无必须完成的安排；异常疼痛请优先"
                                      "考虑专业评估（见限制）"},
        })
    # 去重保序
    seen, uniq = set(), []
    for o in options:
        if o["option_id"] in seen:
            continue
        seen.add(o["option_id"])
        uniq.append(o)
    options = uniq[:3]

    # ---- 置信度 / 局限 ----
    dims = sum(1 for f in facts if f["measurement_type"] == "recovery")
    has_training = any(f["measurement_type"] == "session" for f in facts)
    confidence, confidence_basis = _confidence(len(records), dims, has_training)

    limitations = list(snapshot["limitations"])
    limitations += [
        "所有量表为主观自报（1-5 分），不是生理测量",
        "本分析不输出综合恢复评分，也不做过度训练等医学判断",
        "出现持续/剧烈疼痛、胸闷头晕等异常症状时，请优先考虑就医评估，"
        "不要用训练安排替代医疗判断",
        "修改长期训练计划仍需通过修改提案并经你确认",
    ]
    for key in snapshot["data_quality"]:
        if key in SCALE_LABELS:
            limitations.append(f"{SCALE_LABELS[key][0]}近期未记录——相关维度不做判断")

    src_revision = {
        # 与 checkin_service.version() 同一格式（id:revision:updated_at），
        # 漂移检测逐日比对——任何修订/重录都会触发失效
        "recovery": {r["local_date"]: _recovery_version(db, user_id, r["local_date"])
                     for r in snapshot["records"]},
        "checkins": _cited_checkins(facts),
    }
    latest_desc = _latest_desc(latest)
    return {
        "specialist": "recovery",
        "insight_type": "recovery-review",
        "title": f"恢复回顾 · {window['start'][5:]} ~ {window['end'][5:]}",
        "summary": (f"窗口内 {len(records)} 天恢复记录。{latest_desc} "
                    f"共 {len(options)} 个可选方向，均由你决定。"),
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        "facts_snapshot": {"window": window, "facts": facts,
                           "caliber": "recovery_metrics 自报汇总 + fact_service "
                                      "训练负荷（同源口径）；无综合评分"},
        "knowledge_refs": [],
        "options": options,
        "limitations": limitations,
        "confidence": confidence,
        "confidence_basis": confidence_basis,
        "generated_at": _now(),
        "expires_at": (datetime.now() + timedelta(days=EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": src_revision,
        "input_refs": dict(input_refs or {}),
    }


def _latest_desc(latest: dict) -> str:
    parts = []
    if latest.get("sleep_hours") is not None:
        parts.append(f"睡眠 {latest['sleep_hours']:g} 小时")
    for key in ("sleep_quality", "fatigue", "muscle_soreness", "training_readiness"):
        if latest.get(key) is not None:
            parts.append(f"{SCALE_LABELS[key][0]} {latest[key]}/5")
    return ("最新记录（" + latest["local_date"] + "）：" + ("、".join(parts) if parts
            else "仅备注/区域") + "。")


def _cited_checkins(facts: list[dict]) -> dict[str, int]:
    """训练负荷事实引用的打卡修订（漂移检测用）。"""
    import re
    out: dict[str, int] = {}
    for f in facts:
        for src in f.get("source_ids") or []:
            m = re.match(r"^checkin:(\d+):revision:(\d+)$", str(src))
            if m:
                out[m.group(1)] = max(int(m.group(2)), out.get(m.group(1), 0))
    return out


def _recovery_version(db, user_id: str, local_date: str) -> str:
    from .checkin_service import version
    return version(db, user_id, local_date)


def pre_training_brief(db, user_id: str) -> dict:
    """训练前恢复简报（确定性；不落库、不产生洞察）。

    读取：最近恢复记录 + 近 7 天训练负荷 + 现有限制（医疗安全门/计划隔离）
    + 今日计划。输出观察与可选方向，用户自主决定。
    """
    from ..medical import training_permission
    profile = db.get_existing_profile(user_id) or {}
    permission = training_permission(profile)
    snapshot = recovery_metrics.recovery_snapshot(db, user_id, window_days=7)
    records = snapshot["records"]
    latest = records[0] if records else None
    plan_record = db.get_active_plan_record(user_id)

    observations = list(snapshot["observations"][:4])
    restrictions = []
    if profile.get("plan_fence"):
        restrictions.append(f"计划已隔离（{profile['plan_fence'].get('reason', '未知原因')}）")
    if not permission.allows_prescription:
        restrictions.append("医疗许可未确认：训练处方暂停")
    flags = (profile.get("conditions") or {}).get("pain_flags") or []
    if flags:
        restrictions.append(f"有 {len(flags)} 条待跟进安全记录")

    signals = []
    if latest:
        if (latest.get("fatigue") or 0) >= 4:
            signals.append(f"自报疲劳 {latest['fatigue']}/5")
        if (latest.get("muscle_soreness") or 0) >= 4:
            signals.append(f"自报酸痛 {latest['muscle_soreness']}/5")
        if latest.get("sleep_hours") is not None and latest["sleep_hours"] < 6:
            signals.append(f"自报睡眠 {latest['sleep_hours']:g} 小时")
        if latest.get("training_readiness") is not None \
                and latest["training_readiness"] <= 2:
            signals.append(f"训练意愿 {latest['training_readiness']}/5")

    if restrictions:
        stance = "restricted"
        options = []
        headline = "存在未解除的限制：先处理安全记录，再考虑训练安排"
    elif signals:
        stance = "caution"
        headline = "最新自报信号偏高：可选方向如下（由你决定）"
        options = [
            {"option_id": "adjust-today",
             "title": "调低当次安排一档（正式组数或顶组重量）"},
            {"option_id": "delay-observe", "title": "今天休息，观察一天再练"},
            {"option_id": "maintain-plan", "title": "状态其实可以，按原计划练"},
        ]
    else:
        stance = "clear"
        headline = ("最近自报状态平稳，可以按计划训练" if latest
                    else "近期没有恢复记录——想记录的话 30 秒即可完成一次")
        options = [{"option_id": "maintain-plan", "title": "按原计划训练"}]
        if not latest:
            options.append({"option_id": "record-first",
                            "title": "先记录今天的恢复状态再决定"})

    return {
        "user_id": user_id,
        "stance": stance,           # restricted / caution / clear
        "headline": headline,
        "observations": observations,
        "signals": signals,
        "restrictions": restrictions,
        "options": options,
        "latest_recovery": ({"local_date": latest["local_date"],
                             **{k: latest.get(k) for k in
                                ("sleep_hours", "sleep_quality", "fatigue",
                                 "muscle_soreness", "training_readiness")}}
                            if latest else None),
        "training_load_7d": [
            {"metric": f["metric"], "value": f["value"], "unit": f["unit"]}
            for f in snapshot["facts"] if f["measurement_type"] == "session"],
        "plan_today": (plan_record["content"].get("template") if plan_record else None),
        "note": "简报由确定性代码生成；选项是参考方向而非指令；"
                "修改长期计划走修改提案确认。",
    }
