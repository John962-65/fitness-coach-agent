"""M4 视频动作分析服务（DESIGN_2.0 §八/§十三 M4 任务 1-8 的 Web 化）。

流程：上传 → 后台任务 → 关键点提取（复用 vision.py，本地 MediaPipe）→
质量门与规则（复用 vision_rules：UNSUPPORTED / UNSUPPORTED_VIEW /
INSUFFICIENT_DATA 都如实透出）→ 动作周期分割（确定性峰值检测，画面内
计数为估计值）→ 结果与时间轴落库。

边界（§8.6）：故障为整段聚合 + 数值证据，不推断三维生物力学；
不支持动作/低质量/不可判断必须明确提示，不以"正确率"包装。
"""
from __future__ import annotations

import statistics

from .vision_rules import _angle, _point

# 动作库 id → 规则引擎动作名（未列出的动作如实返回"不支持"）
EXERCISE_RULES = {
    "barbell_back_squat": "squat",
    "goblet_squat": "squat",
    "bodyweight_squat": "squat",
    "deadlift": "deadlift",
    "romanian_deadlift": "romanian_deadlift",
    "barbell_bench_press": "bench",
}
VIEW_OPTIONS = ("side", "front", "back")


def rules_name(exercise_id: str) -> str | None:
    return EXERCISE_RULES.get(exercise_id)


# ---- 动作周期分割（确定性，标注为画面内估计）----

def _signal_for(exercise: str, kp: list[dict]) -> float | None:
    """每帧一个标量信号：蹲类=髋高（y 越大越低）、铰链=躯干前倾、卧推=肘角。"""
    if exercise == "bench":
        s, e, w = _point(kp, 12), _point(kp, 14), _point(kp, 16)
        if s and e and w:
            return _angle(s, e, w)
        s, e, w = _point(kp, 11), _point(kp, 13), _point(kp, 15)
        if s and e and w:
            return _angle(s, e, w)
        return None
    hip = _point(kp, 24) or _point(kp, 23)
    if not hip:
        return None
    if exercise in ("deadlift", "romanian_deadlift"):
        sh = _point(kp, 12) or _point(kp, 11)
        kn = _point(kp, 26) or _point(kp, 25)
        if not sh or not kn:
            return None
        return _angle(sh, hip, kn)  # 躯干-髋-膝角：俯身时变小
    return hip[1]  # squat：髋 y 越大蹲得越低


def segment_reps(exercise: str, indexed: list[tuple[int, list[dict]]],
                 fps: float, sample_every: int = 2) -> list[dict]:
    """峰值检测切分动作周期：返回 [{rep, start_s, end_s, peak_s}]。

    估计口径：以信号跨中线的完整下-上循环计数；不区分左右侧/借力，
    数值仅作画面内提示。
    """
    pts = []
    for idx, kp in indexed:
        v = _signal_for(exercise, kp)
        if v is not None:
            pts.append((idx / fps, v))
    if len(pts) < 6:
        return []
    values = [p[1] for p in pts]
    lo, hi = min(values), max(values)
    if hi - lo < 1e-6:
        return []
    span = hi - lo
    mid = lo + span * 0.5
    reps = []
    inside = False
    start = peak_t = peak_v = None
    # 下位相方向（M5.1 P1-3 修正）：蹲类=髋 y 变大（更低）；
    # 铰链=躯干-髋-膝角变小（俯身）；卧推=肘角变小（下放）
    lowers = exercise in ("deadlift", "romanian_deadlift", "bench")
    for t, v in pts:
        deep = (v < mid) if lowers else (v > mid)
        if deep and not inside:
            inside, start, peak_t, peak_v = True, t, t, v
        elif deep and inside:
            better = (v < peak_v) if lowers else (v > peak_v)
            if better:
                peak_t, peak_v = t, v
        elif not deep and inside:
            reps.append({"rep": len(reps) + 1,
                         "start_s": round(start, 2), "end_s": round(t, 2),
                         "peak_s": round(peak_t, 2)})
            inside = False
    # 结尾仍在下位相 → 计为不完整半程，不凑整
    return reps


def summary_metric(exercise: str, indexed: list[tuple[int, list[dict]]]) -> dict:
    """一次分析的代表指标（对比两次视频用；只描述画面内几何量）。"""
    pts = [(i, _signal_for(exercise, kp)) for i, kp in indexed]
    vals = [v for _i, v in pts if v is not None]
    if not vals:
        return {}
    return {"signal_min": round(min(vals), 1), "signal_max": round(max(vals), 1),
            "signal_mean": round(statistics.fmean(vals), 1)}


def process_analysis(exercise_id: str, video_path: str, view: str,
                     sample_every: int = 2) -> dict:
    """完整分析（worker 内执行）：提取→质量门→规则→周期→指标。

    返回结构直接落库：supported/frames/faults/reps/summary/note；
    UNSUPPORTED / 数据不足 / 无人体都正常返回（状态 ready，内容如实）。
    """
    from .vision import extract_keypoints_indexed
    from .vision_rules import analyze as rules_analyze

    name = rules_name(exercise_id)
    if not name:
        return {"supported": False, "frames": 0, "faults": [], "reps": [],
                "summary": {},
                "note": f"动作 {exercise_id} 暂不在视频分析支持范围"
                        f"（首批：深蹲类/硬拉/罗马尼亚硬拉/卧推，侧面为主）"}
    try:
        indexed, fps, total_sampled = extract_keypoints_indexed(video_path, sample_every)
    except RuntimeError as e:
        return {"supported": True, "frames": 0, "faults": [], "reps": [],
                "summary": {}, "note": f"关键点提取不可用：{e}"}
    if not indexed:
        return {"supported": True, "frames": 0, "faults": [], "reps": [],
                "summary": {}, "detection_ratio": 0.0,
                "note": "没有检测到人体关键点——检查拍摄规范（全身入镜/光线/固定机位），"
                        "此视频不可判断，不代表动作正常"}
    frames = [kp for _i, kp in indexed]
    # 双比例质量门（P1）：detection=检测到人体的采样帧占比；
    # valid=检测帧中所需关键点完整的占比。任一过低都如实降级。
    detection_ratio = min(1.0, len(indexed) / max(1, total_sampled))
    valid_ratio = _valid_ratio(name, frames, view)
    faults = rules_analyze(name, frames, view)
    reps = segment_reps(name, indexed, fps, sample_every)
    quality_note = None
    if any(f["code"] == "INSUFFICIENT_DATA" for f in faults):
        quality_note = "可见关键点不足：此视频不可判断，不代表动作正常"
    elif detection_ratio < 0.5:
        quality_note = (f"检测覆盖率仅 {int(detection_ratio * 100)}%"
                        f"（{len(indexed)}/{total_sampled} 采样帧检出人体；"
                        "遮挡/出镜/光线问题），以下结果仅供参考，建议按拍摄规范重拍")
    elif valid_ratio < 0.5:
        quality_note = (f"关键点完整率仅 {int(valid_ratio * 100)}%（遮挡/半身出镜？），"
                        "以下结果仅供参考，建议按拍摄规范重拍")
    return {
        "supported": True, "view": view, "frames": len(indexed),
        "detection_ratio": round(detection_ratio, 2),
        "valid_ratio": round(valid_ratio, 2),
        "faults": faults, "reps": reps,
        "summary": summary_metric(name, indexed),
        "note": quality_note or ("故障码为整段聚合的可见几何量提示，不推断三维生物力学；"
                                 "次数为画面内估计值" if faults or reps else
                                 "未命中当前覆盖的可见项目；这不代表未评估的动作细节正常"),
    }


def _valid_ratio(exercise: str, frames: list, view: str) -> float:
    """具备该动作所需关键点的帧占比（遮挡/出镜质量的确定性代理）。"""
    from .vision_rules import _point
    if not frames:
        return 0.0
    if exercise == "bench":
        groups = ((11, 13, 15), (12, 14, 16))
    elif exercise == "squat" and view == "front":
        groups = ((23, 24, 25, 26, 27, 28),)
    else:
        groups = ((11, 23, 25, 27), (12, 24, 26, 28))
    valid = sum(1 for f in frames
                if any(all(_point(f, i) is not None for i in g) for g in groups))
    return valid / len(frames)


def compare_results(a: dict, b: dict) -> dict:
    """两次分析确定性对比：同动作才可比；故障码增减 + 代表指标差值。"""
    if not a.get("supported") or not b.get("supported"):
        return {"error": "两次分析都需在支持范围内且完成处理"}
    codes_a = {f["code"] for f in a.get("faults", [])}
    codes_b = {f["code"] for f in b.get("faults", [])}
    sa, sb = a.get("summary") or {}, b.get("summary") or {}
    return {
        "faults_new": sorted(codes_b - codes_a),      # 新出现
        "faults_fixed": sorted(codes_a - codes_b),    # 已消失
        "faults_persist": sorted(codes_a & codes_b),
        "reps": {"a": len(a.get("reps", [])), "b": len(b.get("reps", []))},
        "frames": {"a": a.get("frames"), "b": b.get("frames")},
        "summary_delta": {k: {"a": sa.get(k), "b": sb.get(k)} for k in sa},
        "note": "对比只描述画面内几何量与故障码变化，不构成动作质量评分",
    }
