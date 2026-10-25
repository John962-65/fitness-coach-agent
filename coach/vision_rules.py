"""动作规则引擎（设计书 15.3 线 B 第 2 步）——纯 Python 计算角度/距离，输出故障码

确定性规则，不经过 LLM（设计铁律：安全与判断不放概率性环节）。
输入：MediaPipe 姿态关键点时序（33 点，见 vision.py）；输出：故障码列表 + 数值证据。

MVP 覆盖（15.3 视角与局限）：侧面视角的深蹲/硬拉/卧推 3 个动作；
正面视角的膝盖内扣作为深蹲的附加检查（有正面帧时）。

关键点索引（MediaPipe Pose）：
  11 左肩 12 右肩 23 左髋 24 右髋 25 左膝 26 右膝 27 左踝 28 右踝
"""
from __future__ import annotations

import math


FAULT_LABELS = {
    "SQUAT_SHALLOW": "画面内髋点未低于膝点，需结合目标幅度复核",
    "SQUAT_KNEE_DISPLACEMENT": "画面内膝点水平位移较大",
    "SQUAT_ANKLE_MOVEMENT": "画面内踝点有明显竖直位移",
    "SQUAT_VALGUS": "膝盖内扣（正面视角）",
    "HINGE_TRUNK_ANGLE": "画面内肩髋膝夹角较小",
    "HINGE_SHALLOW_HIP": "髋没往后坐（像深蹲不像硬拉）",
    "BENCH_ELBOW_FRAME_CHANGE": "相邻采样帧肘角变化较大",
    "BENCH_HALF_ROM": "采样中最小肘角大于参考区间，需人工复核",
    "ROW_SHALLOW_PULL": "拉起幅度参考：最小肘角仍较大（画面内）",
    "PRESS_SHALLOW_LOCKOUT": "推起幅度参考：肘角未接近伸直（画面内）",
}
# 15.7 局限声明：以下只能作为「提示」而非诊断；数值阈值可由发起人校准


def _angle(a: tuple, b: tuple, c: tuple) -> float:
    """abc 三点的角度（b 为顶点），度"""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    n1 = math.hypot(*v1) or 1e-9
    n2 = math.hypot(*v2) or 1e-9
    cos = max(-1.0, min(1.0, dot / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _point(points, index):
    try:
        p = points[index]
        x, y, visibility = float(p["x"]), float(p["y"]), float(p.get("visibility", 0))
        aspect = float(p.get("aspect_ratio", 1))
        if visibility <= 0.5 or aspect <= 0 or not all(math.isfinite(v) for v in (x, y, visibility, aspect)):
            return None
        # 坐标原本分别按宽/高归一，计算角度前统一为画面高度单位。
        return x * aspect, y
    except (IndexError, KeyError, TypeError, ValueError, OverflowError):
        return None


def _side(points) -> dict:
    """整侧选择更完整的关键点，不拼接左右关节。"""
    names = ("shoulder", "hip", "knee", "ankle")
    sides = [dict(zip(names, (_point(points, i) for i in indices)))
             for indices in ((11, 23, 25, 27), (12, 24, 26, 28))]
    return max(sides, key=lambda side: sum(p is not None for p in side.values()))


def check_squat(frames: list, view: str = "side") -> list[dict]:
    """深蹲。frames: 每帧 33 关键点（归一化坐标）。侧面为主，正面查膝内扣。"""
    faults: list[dict] = []
    if not frames:
        return faults
    if view == "front":
        valid, inward = 0, 0
        for f in frames:
            lh, rh = _point(f, 23), _point(f, 24)
            if lh is None or rh is None or abs(lh[0] - rh[0]) < 0.01:
                continue
            center = (lh[0] + rh[0]) / 2
            for hi, ki, ai in ((23, 25, 27), (24, 26, 28)):
                h, k, a = (_point(f, i) for i in (hi, ki, ai))
                if h is None or k is None or a is None:
                    continue
                valid += 1
                direction = 1 if center > h[0] else -1
                if direction * (k[0] - (h[0] + a[0]) / 2) > 0.03:
                    inward += 1
        if inward >= max(1, valid // 3):
            faults.append({"code": "SQUAT_VALGUS", "value": inward})
        return faults
    if view != "side":
        return faults
    sides = [_side(f) for f in frames]
    ankle_y = [s["ankle"][1] for s in sides if s["ankle"]]

    # 1) 深度：最低点髋应低于膝（y 更大）
    ratios = [s["hip"][1] - s["knee"][1] for s in sides if s["hip"] and s["knee"]]
    if ratios:
        best = max(ratios)
        if best < 0.0:
            faults.append({"code": "SQUAT_SHALLOW", "value": round(best, 3),
                           "hint": f"髋-膝相对高度峰值 {best:.2f}（应为正）"})
    # 2) 只观察膝点位移，不以此判断肌肉参与或动作有害。
    if all(s["knee"] and s["ankle"] for s in sides):
        x_start = sides[0]["knee"][0]
        x_low = max(sides, key=lambda s: (s["hip"][1] if s["hip"] else 0))["knee"][0]
        shift = abs(x_low - x_start)
        if shift > 0.25:  # 归一化坐标，约等于肩宽的一半
            faults.append({"code": "SQUAT_KNEE_DISPLACEMENT", "value": round(shift, 3),
                           "hint": f"膝水平位移 {shift:.2f}（画面高度比例）；不能据此推断肌肉参与或动作有害"})
    # 3) 踝点位移；没有脚跟接地信息，不能推断脚跟离地。
    if ankle_y:
        lift = max(ankle_y) - min(ankle_y)
        if lift > 0.05:
            faults.append({"code": "SQUAT_ANKLE_MOVEMENT", "value": round(lift, 3),
                           "hint": "踝点位移不能证明脚跟离地或重心位置，需检查脚部画面与机位"})
    return faults


def check_hinge(frames: list, view: str = "side") -> list[dict]:
    """硬拉/罗马尼亚硬拉侧面的可见夹角和位移，不推断腰椎曲度。"""
    faults: list[dict] = []
    if not frames:
        return faults
    sides = [_side(f) for f in frames]
    pairs = [s for s in sides if all(s[k] for k in ("shoulder", "hip", "knee"))]
    if not pairs:
        return faults
    # 1) 肩髋膝夹角是投影几何量，并不是脊柱曲线。
    angles = [_angle(s["shoulder"], s["hip"], s["knee"]) for s in pairs]
    min_angle = min(angles)
    # 原型阈值只用于选择待人工复核的几何观察。
    deep = [a for a in angles if a < 70]
    if len(deep) >= max(2, len(angles) // 4) and min_angle < 60:
        faults.append({"code": "HINGE_TRUNK_ANGLE", "value": round(min_angle, 1),
                       "hint": "肩髋膝夹角不反映腰椎曲度，无法判断圆背、组织损伤或疼痛原因"})
    # 2) 髋后坐：髋的水平位移应明显大于膝
    hip_x = [s["hip"][0] for s in pairs]
    knee_x = [s["knee"][0] for s in pairs]
    hip_shift = max(hip_x) - min(hip_x)
    knee_shift = max(knee_x) - min(knee_x)
    if hip_shift < knee_shift * 1.2:
        faults.append({"code": "HINGE_SHALLOW_HIP",
                       "value": round(hip_shift / max(knee_shift, 1e-9), 2),
                       "hint": "仅为画面内位移比，需要结合动作变式与拍摄质量复核"})
    return faults


def check_bench(frames: list, view: str = "side") -> list[dict]:
    """卧推侧面的可见肘角范围与相邻采样帧变化。"""
    faults: list[dict] = []
    if not frames:
        return faults
    elbow_angles = []
    for f in frames:
        for indices in ((11, 13, 15), (12, 14, 16)):
            pts = [_point(f, i) for i in indices]
            if all(p is not None for p in pts):
                elbow_angles.append(_angle(*pts))
                break
    if elbow_angles:
        # 可见肘角范围，不据此判断杠铃是否触胸。
        if min(elbow_angles) > 100:
            faults.append({"code": "BENCH_HALF_ROM",
                           "value": round(min(elbow_angles), 1),
                           "hint": "仅描述可见肘角范围；没有杠铃与胸部接触信息，无法判断是否触胸"})
        # 缺少时间戳，不称为角速度，也不推断触胸反弹。
        fast = sum(1 for a, b in zip(elbow_angles, elbow_angles[1:])
                   if b - a > 25)
        if fast >= 2 and min(elbow_angles) < 95:
            faults.append({"code": "BENCH_ELBOW_FRAME_CHANGE", "value": fast,
                           "hint": "相邻采样帧变化受抽帧率影响；不能据此判断触胸弹起或借力"})
    return faults


def _elbow_angles(frames: list, view: str = "side") -> list[float]:
    """两侧肘角（肩-肘-腕）投影序列（side 视角下的可见几何量）。"""
    from .vision_rules import _point  # 局部引用避免循环
    out = []
    for f in frames:
        for s, e, w in ((11, 13, 15), (12, 14, 16)):
            if _point(f, s) and _point(f, e) and _point(f, w):
                out.append(_angle(_point(f, s), _point(f, e), _point(f, w)))
    return out


def check_row(frames: list, view: str = "side") -> list[dict]:
    """杠铃划船侧面：肘角范围（拉起-下放的可见几何量）。保守：只报 ROM 参考。"""
    faults: list[dict] = []
    angles = _elbow_angles(frames, view)
    if len(angles) < 4:
        return faults
    min_a = min(angles)
    if min_a > 105:
        faults.append({"code": "ROW_SHALLOW_PULL", "value": round(min_a, 1),
                       "hint": "采样中最小肘角仍较大（拉起幅度参考）；仅画面内几何量，"
                               "负重与躯干姿态信息缺失，不构成动作质量评分"})
    return faults


def check_shoulder_press(frames: list, view: str = "side") -> list[dict]:
    """哑铃肩推侧面：肘角范围 + 头前伸粗查（肩-肘-腕投影角）。"""
    faults: list[dict] = []
    angles = _elbow_angles(frames, view)
    if len(angles) < 4:
        return faults
    max_a = max(angles)
    if max_a < 140:
        faults.append({"code": "PRESS_SHALLOW_LOCKOUT", "value": round(max_a, 1),
                       "hint": "采样中肘角未接近伸直参考区间；仅为画面内几何量，"
                               "不推断肩关节健康或负荷合理性"})
    return faults


CHECKERS = {"squat": check_squat, "deadlift": check_hinge,
            "romanian_deadlift": check_hinge, "bench": check_bench,
            "barbell_row": check_row, "shoulder_press": check_shoulder_press}


def analyze(exercise: str, frames: list, view: str = "side") -> list[dict]:
    """入口：动作名 → 对应规则引擎。未知动作返回空（15.7：只承诺覆盖的动作）。"""
    fn = CHECKERS.get(exercise)
    if fn is None:
        return [{"code": "UNSUPPORTED", "value": exercise,
                 "hint": "当前只支持深蹲/硬拉/罗马尼亚硬拉/卧推/杠铃划船/肩推（侧面）"}]
    if view != "side" and not (exercise == "squat" and view == "front"):
        return [{"code": "UNSUPPORTED_VIEW", "hint": "该动作当前只支持侧面，请按拍摄规范重新录制"}]
    elbow_exercises = ("bench", "barbell_row", "shoulder_press")
    required = ((11, 13, 15), (12, 14, 16)) if exercise in elbow_exercises \
        else ((11, 23, 25, 27), (12, 24, 26, 28))
    if exercise == "squat" and view == "front":
        required = ((23, 24, 25, 26, 27, 28),)
    valid = [f for f in (frames or []) if any(all(_point(f, i) is not None for i in group) for group in required)]
    if len(valid) < 2:
        return [{"code": "INSUFFICIENT_DATA", "hint": "可见关键点不足，不能将未命中规则当作动作正常"}]
    faults = fn(valid, view)
    for f in faults:
        f["label"] = FAULT_LABELS.get(f["code"], f["code"])
    return faults
