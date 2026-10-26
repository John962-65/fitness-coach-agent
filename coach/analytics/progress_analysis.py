"""M6.5-2：可解释训练趋势分析——只分析指标变化，不直接生成训练建议。

输出四态：improving / stable / declining / insufficient，并附带：
- 支持判断的数据（前后半窗可比值、样本量、跨度）；
- 限制（可比性、缺口、测量口径变化）——解释结论边界，不给建议。

可比性纪律：
- 指标按测量类型选择（e1RM 只属于 weight_reps 1-12 次；自重看次数/
  额外负重；辅助看辅助重量；时长/距离各归各类）——与 fact_service
  的 MEASUREMENT_METRICS 同一张表。
- 相似次数范围才直接比较重量（60kg×12 与 70kg×3 的重量差不解释为力量
  进步）——e1RM 趋势统一换算后再比；直接重量比较限定同次数带。
- 样本 <3 次、总跨度 <7 天、或两半窗口有 >21 天缺口 → insufficient。
- 测量类型/动作记录方式变化 → 确定性降级说明。
- 短期波动不称平台期；相关性不归因方案（措辞约束在输出 note 里）。
"""
from __future__ import annotations

import statistics
from datetime import date

from .activity_class import (
    CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH, ACTIVITY_CLASS_VERSION,
)

MIN_SESSIONS = 3
MIN_SPAN_DAYS = 7
MAX_HALF_GAP_DAYS = 21
MEANINGFUL_REL_CHANGE = 0.025  # e1RM/负重类：±2.5% 以上视为方向性变化
MEANINGFUL_ABS_REPS = 2        # 次数类：±2 次


def _half(dates: list[str]):
    mid = len(dates) // 2
    return dates[:mid], dates[mid:]


def analyze_progress(series: list[dict], measurement_type: str = "weight_reps",
                     metric: str | None = None,
                     activity_class: str | None = None) -> dict:
    """series：exercise_progress 的逐会话序列（旧→新）。

    activity_class 来自统一分类服务；未传入时从 series 的快照/推断字段读取。
    HIIT 不使用力量 e1RM/容量或持续性有氧时长指标。
    """
    derived_classes = {s.get("activity_class") for s in series
                       if s.get("activity_class")}
    resolved_class = activity_class
    if resolved_class is None:
        resolved_class = derived_classes.pop() if len(derived_classes) == 1 else None
    if activity_class is None and resolved_class not in (
            CLASS_INTERVAL, CLASS_STEADY_CARDIO, CLASS_STRENGTH):
        resolved_class = None
    usable = [s for s in series if s.get("date")]
    if len(usable) < MIN_SESSIONS:
        return {
            "verdict": "insufficient", "metric": metric,
            "evidence": {"sessions": len(usable)},
            "limitations": [f"训练样本 {len(usable)} 次 < {MIN_SESSIONS}，不足以判趋势"],
            "note": "数据不足时明确说不足，不用单次表现外推趋势。",
        }
    dates = [s["date"] for s in usable]
    span = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    if span < MIN_SPAN_DAYS:
        return {
            "verdict": "insufficient", "metric": metric,
            "evidence": {"sessions": len(usable), "span_days": span},
            "limitations": [f"记录跨度 {span} 天 < {MIN_SPAN_DAYS} 天"],
            "note": "时间跨度太短，无法区分趋势与单日波动。",
        }

    # ---- 按测量类型选择可比指标序列 ----
    def _values(s: dict, _chosen=()):
        c = _chosen or chosen
        if c == "best-e1rm":
            return s.get("best_e1rm")
        if c == "max-reps":
            bs = s.get("best_set") or {}
            return bs.get("reps")
        if c == "heaviest-set":
            bs = s.get("best_set") or {}
            return bs.get("weight_kg")
        if c == "longest-set":
            return s.get("longest_set_s")
        if c == "farthest-distance":
            return s.get("farthest_set_m")
        if c == "interval-work-seconds":
            return s.get("interval_work_seconds")
        if c == "steady-cardio-seconds":
            return s.get("steady_cardio_seconds")
        if c == "steady-cardio-distance":
            return s.get("steady_cardio_distance_m")
        return s.get("best_e1rm")

    chosen = metric or ({
        CLASS_INTERVAL: "interval-work-seconds",
        CLASS_STEADY_CARDIO: ("steady-cardio-distance"
                              if measurement_type == "distance_time"
                              else "steady-cardio-seconds"),
        CLASS_STRENGTH: {
            "weight_reps": "best-e1rm",
            "bodyweight_reps": "max-reps",
            "assisted_reps": "max-reps",
            "duration": "longest-set",
            "distance_time": "farthest-distance",
        }.get(measurement_type, "best-e1rm"),
    }.get(resolved_class) if resolved_class else {
        "weight_reps": "best-e1rm",
        "bodyweight_reps": "max-reps",
        "assisted_reps": "max-reps",
        "duration": "longest-set",
        "distance_time": "farthest-distance",
    }.get(measurement_type, "best-e1rm"))

    limitations: list[str] = []
    if resolved_class == CLASS_INTERVAL:
        limitations.append(
            "HIIT 按实际工作秒数观察；不同编排/轮次的工作与休息结构不可直接比较，"
            "该指标不代表有氧能力或力量水平")
    elif resolved_class == CLASS_STEADY_CARDIO:
        limitations.append(
            "持续性有氧按本类型指标观察；无距离记录不生成配速，"
            "不同器械/运动类型不可直接类比")
    elif measurement_type in ("duration", "distance_time"):
        limitations.append("时长/距离记录不参与力量 e1RM 或容量解释")
    if chosen == "best-e1rm":
        n_valid = sum(1 for s in usable if s.get("best_e1rm") is not None)
        if n_valid < MIN_SESSIONS:
            return {
                "verdict": "insufficient", "metric": chosen,
                "evidence": {"sessions_with_valid_e1rm": n_valid},
                "limitations": ["1-12 次区间有效组不足，e1RM 趋势不可判"],
                "note": "e1RM 只在 1-12 次区间估算；高次数训练不套用该口径。",
            }

    first_half, second_half = _half(usable)
    fv = [v for s in first_half if (v := _values(s)) is not None]
    sv = [v for s in second_half if (v := _values(s)) is not None]
    if not fv or not sv:
        return {
            "verdict": "insufficient", "metric": chosen,
            "evidence": {"first_half_n": len(fv), "second_half_n": len(sv)},
            "limitations": [f"所选指标 {chosen} 在某一半窗口无有效值"],
            "note": "先补齐记录或换该类型的适用指标再看趋势。",
        }

    # 缺口检查（两半窗口内部最大间隔）：超过阈值即降级 insufficient——
    # 只在 limitations 里提醒而不降级会让不连续的数据得出方向性结论
    # （M6.5 复查 P0-2）
    for label, half in (("前半", first_half), ("后半", second_half)):
        gap = None
        hd = [s["date"] for s in half]
        if len(hd) >= 2:
            dd = sorted(date.fromisoformat(x) for x in hd)
            gap = max((b - a).days for a, b in zip(dd, dd[1:]))
        if gap is not None and gap > MAX_HALF_GAP_DAYS:
            return {
                "verdict": "insufficient", "metric": chosen,
                "evidence": {"first_half_n": len(fv), "second_half_n": len(sv),
                             f"{label}_max_gap_days": gap},
                "limitations": [f"{label}窗口内记录间隔达 {gap} 天"
                                f"（>{MAX_HALF_GAP_DAYS}），趋势连续性不足"],
                "note": "训练记录间隔过长，先补齐观察再判断趋势。",
            }
        if gap is not None:
            limitations.append(f"{label}窗口内最大记录间隔 {gap} 天")

    f_med = statistics.median(fv)
    s_med = statistics.median(sv)
    if chosen in ("max-reps", "longest-set", "farthest-distance"):
        diff = s_med - f_med
        threshold = MEANINGFUL_ABS_REPS if chosen == "max-reps" else max(
            1.0, f_med * 0.02)
        rel = diff / f_med if f_med else None
        if diff > threshold:
            verdict = "improving"
        elif diff < -threshold:
            verdict = "declining"
        else:
            verdict = "stable"
    else:
        rel = (s_med - f_med) / f_med if f_med else None
        if rel is None:
            verdict = "insufficient"
        elif rel > MEANINGFUL_REL_CHANGE:
            verdict = "improving"
        elif rel < -MEANINGFUL_REL_CHANGE:
            verdict = "declining"
        else:
            verdict = "stable"

    return {
        "verdict": verdict,
        "metric": chosen,
        "activity_class": resolved_class,
        "classification_version": ACTIVITY_CLASS_VERSION,
        "evidence": {
            "first_half_median": round(f_med, 2),
            "second_half_median": round(s_med, 2),
            "first_half_n": len(fv), "second_half_n": len(sv),
            "sessions_total": len(usable), "span_days": span,
            "relative_change": round(rel, 3) if rel is not None else None,
        },
        "limitations": limitations,
        "note": ("前后半窗口中位数比较；短期波动不等于平台期，"
                 "趋势也不直接归因于训练方案本身。"),
    }
