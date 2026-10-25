"""动作技术顾问确定性分析器：VideoAnalysisCompleted → 技术回顾洞察。

内容纪律（P4-4）：
- 输出只基于已落库的技术档案（video_quality/observations/phase_timestamps）
  ——先有有效观测，再解释；观测不足时洞察如实说"不可判断"；
- 每条反馈区分：观察结果 / 教学参考 / 无法判断的部分；
- 不输出三维力矩、不诊断损伤、不因参考动画差异判定动作错误；
- 教学引用只取 review_status 达标（reviewed/approved）的结构化教学；
- P4-6 联动：附康复安全视图的相关限制（只读展示），不生成任何训练
  修改建议——训练修改永远走统一修改协议。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..teaching_content import public_teaching
from ..rehab import restriction_service

EXPIRE_DAYS = 30
# 三维演示动作（首批）；自定义动作无公共三维，不按名称相似挂接
DEMO_EXERCISES = ("barbell_back_squat", "barbell_bench_press", "deadlift",
                  "barbell_row", "dumbbell_shoulder_press")

SOURCE_LABEL = {"user_reported": "用户自行报告",
                "professional": "专业人员给出",
                "triage_recommended": "安全分流提示（待确认）"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def analyze_movement_review(db, user_id: str, input_refs: dict) -> dict:
    analysis_id = input_refs.get("analysis_id")
    analysis = db.get_motion_analysis(user_id, int(analysis_id)) if analysis_id else None
    if not analysis:
        raise ValueError("视频分析不存在")
    if analysis["status"] != "ready":
        raise ValueError(f"分析状态为 {analysis['status']}，无可回顾内容")
    exercise_id = analysis["exercise_id"]
    profile = db.get_motion_tech_profile(user_id, int(analysis_id))
    result = analysis.get("result") or {}

    findings: list[dict] = []
    facts: list[dict] = []
    quality = (profile or {}).get("video_quality") or {}
    observations = (profile or {}).get("motion_observations") \
        or result.get("observations") or []
    phases = (profile or {}).get("phase_timestamps") or result.get("reps") or []

    srcs = [f"motion_analysis:{analysis_id}"]
    facts.append({
        "fact_id": f"motion-quality-{analysis_id}", "metric": "video-quality",
        "value": quality.get("status") or "unknown", "unit": "",
        "measurement_type": "movement", "window": {"label": "单次视频"},
        "source_ids": srcs, "calculation": "detection_valid_ratio_gates",
        "data_quality": {"detection_ratio": quality.get("detection_ratio"),
                         "valid_ratio": quality.get("valid_ratio")},
        "status": "observed" if quality.get("status") == "usable" else "estimated",
        "note": f"视角 {quality.get('view')}；帧数 {result.get('frames', 0)}"})

    # 教学引用（只取审核达标的结构化教学；不足时如实说明）
    teaching = public_teaching(exercise_id) or {}
    review = teaching.get("review_status")
    teaching_refs: list[dict] = []
    if review in ("reviewed", "approved"):
        for sec_key, sec in (teaching.get("sections") or {}).items():
            if sec.get("status") in ("reviewed", "approved") and sec.get("items"):
                teaching_refs.append({"ref": f"teaching:{exercise_id}:{sec_key}",
                                      "title": sec_key,
                                      "review_status": sec["status"]})
        findings.append({
            "finding_id": "f-teaching", "kind": "teaching-reference",
            "text": (f"结构化教学（审核状态 {review}，版本 v{teaching.get('content_version')}）"
                     f"可作为参考依据；对照时注意身体比例、节奏、视角与器械差异。"),
            "fact_ids": [], "source_ids": [t["ref"] for t in teaching_refs]})
    else:
        findings.append({
            "finding_id": "f-teaching-missing", "kind": "teaching-reference",
            "text": (f"该动作的结构化教学当前审核状态为 {review or '缺失'}——"
                     "不足以作为已确认的专业指导依据；以下仅为画面内观察。"),
            "fact_ids": [], "source_ids": []})

    # 观察转写（引用档案）
    usable = quality.get("status") == "usable"
    for o in observations:
        findings.append({
            "finding_id": f"f-obs-{o.get('kind')}-{len(findings)}",
            "kind": f"observation/{o.get('kind')}",
            "text": o.get("text", ""),
            "fact_ids": [f"motion-quality-{analysis_id}"] if usable else [],
            "source_ids": srcs,
            **({"evidence": "context"} if not usable else {})})
    if phases:
        rep_list = "、".join(
            f"#{p.get('rep', i + 1)} {p.get('start_s', '?')}–{p.get('end_s', '?')}s"
            for i, p in enumerate(phases[:6]))
        findings.append({
            "finding_id": "f-phases", "kind": "phase-timestamps",
            "text": f"动作阶段（画面内估计）：{rep_list}"
                    + ("…" if len(phases) > 6 else "")
                    + "。可用于对照时手动对齐。",
            "fact_ids": [f"motion-quality-{analysis_id}"], "source_ids": srcs})

    # 无法判断的部分（显式声明）
    unable = ["二维投影无法测得三维关节角/力矩",
              "杠铃/哑铃器械轨迹未跟踪（无器械关键点）",
              "左右差异仅在正/背面视角部分可见",
              "接触点（如杠铃触胸）、躯干曲度等无法从关键点判断"]
    findings.append({
        "finding_id": "f-unable", "kind": "unable-to-judge",
        "text": "无法判断的部分：" + "；".join(unable) + "。",
        "fact_ids": [], "source_ids": []})

    # P4-6 康复联动：只读展示相关安全限制（不给训练建议）
    from ..rehab import safety_integration
    view = safety_integration.safety_view(db, user_id)
    related_restrictions = []
    if view.active_restrictions:
        doc_map = {"barbell_back_squat": {"primary": ["quads"], "joint_stress": {"knee": 3, "lumbar": 2}},
                   "barbell_bench_press": {"primary": ["chest"], "joint_stress": {"shoulder": 3, "wrist": 2}},
                   "deadlift": {"primary": ["hamstrings", "glutes"], "joint_stress": {"lumbar": 3}},
                   "barbell_row": {"primary": ["lats"], "joint_stress": {"lumbar": 2}},
                   "dumbbell_shoulder_press": {"primary": ["front_delt"], "joint_stress": {"shoulder": 3}}}
        doc = doc_map.get(exercise_id, {})
        from ..rehab.restriction_service import restriction_blocks
        hit = restriction_blocks(db, user_id, doc) if doc else None
        related_restrictions = [hit["restriction"]] if hit else []
        for r in (related_restrictions or view.active_restrictions[:2]):
            aff = r["affected_activities"] or {}
            findings.append({
                "finding_id": f"f-restriction-{r['id']}", "kind": "safety-restriction",
                "text": (f"训练限制[{SOURCE_LABEL.get(r['source_type'], r['source_type'])}]："
                         f"{r['restriction_description']}"
                         f"（覆盖 {'、'.join(aff.get('regions') or []) or '指定动作'}）。"
                         "观看/学习教学不受影响；是否执行该动作请遵循限制，"
                         "训练修改需经修改提案确认。"),
                "fact_ids": [], "source_ids": [f"restriction:{r['id']}"]})

    options = [{
        "option_id": "compare-with-3d", "title": "与三维教学动画分屏对照",
        "detail": "在工作台打开对照视图：两侧独立播放/倍速/手动对齐阶段；"
                  "对照用于帮助观察，不构成动作是否正确的判定。",
        "basis": [f"motion-quality-{analysis_id}"],
        "tradeoffs": {"收益": "直观看到自身动作与教学提示的差异点",
                      "代价": "需要花时间逐段对照",
                      "适用条件": f"三维演示可用（首批 {len(DEMO_EXERCISES)} 动作）时"},
    }]
    options.append({
        "option_id": "keep-records", "title": "保留本次档案，下次对比",
        "detail": "技术档案按模型版本留痕；同一动作不同日期的视频可在"
                  "「历史技术记录」对比（需可比视角与观测质量）。",
        "basis": [],
        "tradeoffs": {"收益": "长期看得到可见特征的变化",
                      "代价": "需要定期拍摄同视角视频",
                      "适用条件": "拍摄规范一致时才有可比性"},
    })
    if not usable:
        options.insert(0, {
            "option_id": "re-record", "title": "按拍摄规范重拍",
            "detail": "本次视频质量不足（见质量检查），重拍后再分析；"
                      "质量不足的结果不可作为技术评估依据。",
            "basis": [f"motion-quality-{analysis_id}"],
            "tradeoffs": {"收益": "得到可判断的观察结果",
                          "代价": "需要重新拍摄",
                          "适用条件": "全身入镜/固定机位/侧面光线充足"}})

    confidence = "medium" if usable and phases else "low"
    region_title = {"barbell_back_squat": "杠铃深蹲", "barbell_bench_press": "杠铃卧推",
                    "deadlift": "硬拉", "barbell_row": "杠铃划船",
                    "dumbbell_shoulder_press": "哑铃肩推"}.get(exercise_id, exercise_id)
    limitations = [
        "所有角度为二维投影角，非三维关节角；不含力矩/负荷推断",
        f"分析模型版本 {profile.get('model_version') if profile else '未知'}——"
        "跨版本数值差异不解释为动作变化",
        "参考动画不作为动作正确性唯一标准；本分析不构成医学诊断",
    ]
    if quality.get("limitations"):
        limitations += [str(x) for x in quality["limitations"]]

    return {
        "specialist": "movement",
        "insight_type": "movement-review",
        "title": f"动作技术回顾 · {region_title}",
        "summary": (f"视频质量 {quality.get('status') or '未知'}；"
                    f"画面内识别 {len(phases)} 个周期、{len(observations)} 条观察。"
                    f"{'相关训练限制生效中。' if related_restrictions else ''}"),
        "findings": findings,
        "evidence_refs": sorted({fid for f in findings for fid in f["fact_ids"]}),
        "facts_snapshot": {"window": {"label": "单次视频"}, "facts": facts,
                           "caliber": "MediaPipe 二维关键点 + vision-rules 确定性规则；"
                                      "无三维生物力学"},
        "knowledge_refs": teaching_refs,
        "options": options,
        "limitations": limitations,
        "confidence": confidence,
        "confidence_basis": (f"置信度规则=视频质量 {quality.get('status')} + "
                             f"周期识别 {len(phases)} 个（usable 且有周期=medium，"
                             "其余=low；症状数据不做 high 声明）"),
        "generated_at": _now(),
        "expires_at": (datetime.now() + timedelta(days=EXPIRE_DAYS)
                       ).isoformat(timespec="seconds"),
        "source_revision": {"motion": db.motion_profile_version(user_id),
                            "restrictions":
                                restriction_service.restrictions_version(db, user_id)},
        "input_refs": dict(input_refs or {}),
    }
