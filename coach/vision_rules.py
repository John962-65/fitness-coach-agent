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
    "SQUAT_SHALLOW": "蹲得不够深（髋未低于膝）",
    "SQUAT_KNEE_FORWARD": "膝盖过度前移（膝主导，臀参与不足）",
    "SQUAT_HEEL_LIFT": "脚跟离地/重心前移",
    "SQUAT_VALGUS": "膝盖内扣（正面视角）",
    "HINGE_ROUND_BACK": "下背弯曲（腰椎反弓风险）",
    "HINGE_SHALLOW_HIP": "髋没往后坐（像深蹲不像硬拉）",
    "BENCH_BOUNCE": "触胸弹起（利用反弹借力）",
    "BENCH_HALF_ROM": "幅度不足（未触胸或未伸直）",
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


def _side(points) -> dict:
    """取单侧关键点（画面朝向的一侧）：优先左，异常用右"""
    idx = {"shoulder": 11, "hip": 23, "knee": 25, "ankle": 27}
    out = {}
    for name, i in idx.items():
        p = points[i] if i < len(points) else None
        out[name] = (p["x"], p["y"]) if p and p.get("visibility", 1) > 0.5 else None
    if out["knee"] is None:  # 左侧不可见 → 右侧
        for name, i in {"shoulder": 12, "hip": 24, "knee": 26, "ankle": 28}.items():
            p = points[i]
            out[name] = (p["x"], p["y"]) if p and p.get("visibility", 1) > 0.5 else None
    return out


def check_squat(frames: list, view: str = "side") -> list[dict]:
    """深蹲。frames: 每帧 33 关键点（归一化坐标）。侧面为主，正面查膝内扣。"""
    faults: list[dict] = []
    if not frames:
        return faults
    sides = [_side(f) for f in frames]
    hip_y = [s["hip"][1] for s in sides if s["hip"]]
    knee_y = [s["knee"][1] for s in sides if s["knee"]]
    ankle_y = [s["ankle"][1] for s in sides if s["ankle"]]

    # 1) 深度：最低点髋应低于膝（y 更大）
    if hip_y and knee_y:
        ratios = [h - k for h, k in zip(hip_y, knee_y)]
        best = max(ratios)
        if best < 0.0:
            faults.append({"code": "SQUAT_SHALLOW", "value": round(best, 3),
                           "hint": f"髋-膝相对高度峰值 {best:.2f}（应为正）"})
    # 2) 膝盖前移：下蹲到底时膝水平位移相对脚踝过大
    if all(s["knee"] and s["ankle"] for s in sides):
        x_start = sides[0]["knee"][0]
        x_low = max(sides, key=lambda s: (s["hip"][1] if s["hip"] else 0))["knee"][0]
        shift = abs(x_low - x_start)
        if shift > 0.25:  # 归一化坐标，约等于肩宽的一半
            faults.append({"code": "SQUAT_KNEE_FORWARD", "value": round(shift, 3),
                           "hint": f"膝水平位移 {shift:.2f}（画面宽度比例）"})
    # 3) 脚跟离地：蹲底时踝明显上升
    if ankle_y and knee_y:
        lift = max(ankle_y) - min(ankle_y)
        if lift > 0.05:
            faults.append({"code": "SQUAT_HEEL_LIFT", "value": round(lift, 3)})
    # 4) 正面：膝内扣（膝 x 向对侧偏移超过踝-髋连线）
    if view == "front":
        valgus = 0
        for s in sides:
            if s["hip"] and s["knee"] and s["ankle"]:
                if s["knee"][0] > (s["hip"][0] + s["ankle"][0]) / 2 + 0.03:
                    valgus += 1
        if valgus >= max(1, len(sides) // 3):
            faults.append({"code": "SQUAT_VALGUS", "value": valgus})
    return faults


def check_hinge(frames: list, view: str = "side") -> list[dict]:
    """硬拉/罗马尼亚硬拉（侧面）：腰背中立 + 髋后坐"""
    faults: list[dict] = []
    if not frames:
        return faults
    sides = [_side(f) for f in frames]
    pairs = [s for s in sides if all(s[k] for k in ("shoulder", "hip", "knee"))]
    if not pairs:
        return faults
    # 1) 腰背：肩-髋连线与髋-膝连线夹角过小（躯干过度前屈且塌腰）提示
    angles = [_angle(s["shoulder"], s["hip"], s["knee"]) for s in pairs]
    min_angle = min(angles)
    # 躯干角 < 60° 且 <95 分位过小 → 提示圆背风险（粗粒度，待发起人校准）
    deep = [a for a in angles if a < 70]
    if len(deep) >= max(2, len(angles) // 4) and min_angle < 60:
        faults.append({"code": "HINGE_ROUND_BACK", "value": round(min_angle, 1),
                       "hint": "躯干角过小说明俯身过深，注意脊柱中立"})
    # 2) 髋后坐：髋的水平位移应明显大于膝
    hip_x = [s["hip"][0] for s in pairs]
    knee_x = [s["knee"][0] for s in pairs]
    hip_shift = max(hip_x) - min(hip_x)
    knee_shift = max(knee_x) - min(knee_x)
    if hip_shift < knee_shift * 1.2:
        faults.append({"code": "HINGE_SHALLOW_HIP",
                       "value": round(hip_shift / max(knee_shift, 1e-9), 2),
                       "hint": "髋位移不足——做成了蹲，不是髋铰链"})
    return faults


def check_bench(frames: list, view: str = "side") -> list[dict]:
    """卧推（侧面）：幅度与弹起借力"""
    faults: list[dict] = []
    if not frames:
        return faults
    sides = [_side(f) for f in frames]
    shoulder_y = [s["shoulder"][1] for s in sides if s["shoulder"]]
    elbow_angles = []
    for f in frames:
        p = f
        try:
            sh, el, wr = p[11], p[13], p[15]
            a = _angle((sh["x"], sh["y"]), (el["x"], el["y"]), (wr["x"], wr["y"]))
            elbow_angles.append(a)
        except (KeyError, IndexError, TypeError):
            continue
    if elbow_angles:
        # 幅度：最弯肘角过小 = 没到底（卧推底端肘角约 45-90°）
        if min(elbow_angles) > 100:
            faults.append({"code": "BENCH_HALF_ROM",
                           "value": round(min(elbow_angles), 1),
                           "hint": "肘角从未进入深度区间，可能幅度不足"})
        # 弹起：底端停留时间过短（连续帧肘角变化率过高）
        fast = sum(1 for a, b in zip(elbow_angles, elbow_angles[1:])
                   if b - a > 25)
        if fast >= 2 and min(elbow_angles) < 95:
            faults.append({"code": "BENCH_BOUNCE", "value": fast,
                           "hint": "底端到推起的角速度过快，疑似触胸弹起"})
    return faults


CHECKERS = {"squat": check_squat, "deadlift": check_hinge,
            "romanian_deadlift": check_hinge, "bench": check_bench}


def analyze(exercise: str, frames: list, view: str = "side") -> list[dict]:
    """入口：动作名 → 对应规则引擎。未知动作返回空（15.7：只承诺覆盖的动作）。"""
    fn = CHECKERS.get(exercise)
    if fn is None:
        return [{"code": "UNSUPPORTED", "value": exercise,
                 "hint": "MVP 只支持深蹲/硬拉/罗马尼亚硬拉/卧推（侧面）"}]
    faults = fn(frames, view)
    for f in faults:
        f["label"] = FAULT_LABELS.get(f["code"], f["code"])
    return faults
