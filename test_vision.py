"""视觉规则引擎测试：合成关键点时序锁定确定性规则（15.3 线 B 第 2 步）"""
import pytest

from coach import vision_rules as vr


def _frame(shoulder, hip, knee, ankle, side="left", extra=None):
    """构造一帧的最小关键点。坐标为归一化（x 右正，y 下正）。
    未用到的点 visibility=0（模拟 MediaPipe 对不可见点的输出）。"""
    idx = {"left": {"shoulder": 11, "hip": 23, "knee": 25, "ankle": 27},
           "right": {"shoulder": 12, "hip": 24, "knee": 26, "ankle": 28}}[side]
    pts = [{"x": 0, "y": 0, "visibility": 0.0} for _ in range(33)]
    for name, (x, y) in {"shoulder": shoulder, "hip": hip,
                         "knee": knee, "ankle": ankle}.items():
        pts[idx[name]] = {"x": x, "y": y, "visibility": 0.95}
    if extra:
        for i, p in extra.items():
            pts[i] = {"x": p[0], "y": p[1], "visibility": 0.9}
    return pts


def _squat_frames(bottom_hip_y, bottom_knee_y, knee_x_shift=0.02):
    """站立→下蹲→站起 的侧面三段合成。x 固定（正侧面），y 变化。"""
    frames = []
    for t in (0.0, 0.5, 1.0, 0.5, 0.0):
        hip_y = 0.55 - (0.55 - bottom_hip_y) * t
        knee_y = 0.68 - (0.68 - bottom_knee_y) * t
        knee_x = 0.50 + knee_x_shift * t
        frames.append(_frame((0.50, 0.30), (0.50, hip_y), (knee_x, knee_y),
                             (0.50, 0.85)))
    return frames


# ---- 深蹲 ----

def test_squat_good_depth_no_faults():
    """合格深蹲：髋低于膝、膝位移小 → 无故障码"""
    faults = vr.check_squat(_squat_frames(0.75, 0.62))
    assert faults == []


def test_squat_shallow():
    faults = vr.check_squat(_squat_frames(0.60, 0.70))  # 髋没到底
    codes = [f["code"] for f in faults]
    assert "SQUAT_SHALLOW" in codes


def test_squat_knee_forward():
    faults = vr.check_squat(_squat_frames(0.75, 0.62, knee_x_shift=0.30))
    codes = [f["code"] for f in faults]
    assert "SQUAT_KNEE_DISPLACEMENT" in codes


def test_squat_valgus_front_view():
    """正面视角：膝 x 越过髋-踝中点 → 内扣"""
    frames = []
    for _ in range(4):
        frames.append(_frame((0.50, 0.30), (0.44, 0.55), (0.47, 0.68),
                             (0.40, 0.85), side="left",
                             extra={24: (0.56, 0.55), 26: (0.56, 0.68), 28: (0.60, 0.85)}))
    faults = vr.check_squat(frames, view="front")
    assert any(f["code"] == "SQUAT_VALGUS" for f in faults)


def test_squat_side_view_no_valgus_check():
    """侧面视角不做内扣判断（15.3 视角局限）"""
    frames = _squat_frames(0.60, 0.70)
    assert all(f["code"] != "SQUAT_VALGUS" for f in vr.check_squat(frames, "side"))


# ---- 硬拉 / 髋铰链 ----

def _hinge_frames(hip_x_back, shoulder_angle_deg):
    """髋后坐的合成：肩绕髋旋转 shoulder_angle 度（0=直立）"""
    import math
    frames = []
    for t in (0.0, 0.5, 1.0, 0.5, 0.0):
        ang = math.radians(shoulder_angle_deg * t)
        sh = (0.50 - math.sin(ang) * 0.35, 0.30 + (1 - math.cos(ang)) * 0.1)
        hip = (0.50 - hip_x_back * t, 0.55)
        frames.append(_frame(sh, hip, (0.50, 0.68), (0.50, 0.85)))
    return frames


def test_hinge_good_pattern_no_faults():
    """髋明显后坐、躯干角不过深 → 无故障"""
    faults = vr.check_hinge(_hinge_frames(hip_x_back=0.15, shoulder_angle_deg=55))
    assert faults == []


def test_hinge_too_much_squat_not_hip():
    """髋没后坐（膝先动）→ 提示做成了蹲"""
    frames = []
    for t in (0.0, 0.5, 1.0, 0.5, 0.0):
        hip_y = 0.55 - 0.15 * t          # 髋下坠
        knee_x = 0.50 + 0.20 * t          # 膝大幅前移
        frames.append(_frame((0.50, 0.30), (0.50, hip_y), (knee_x, 0.68),
                             (0.50, 0.85)))
    faults = vr.check_hinge(frames)
    assert any(f["code"] == "HINGE_SHALLOW_HIP" for f in faults)


# ---- 卧推 ----

def _bench_frames(angles=None):
    import math
    frames = []
    angles = angles or [170.0, 140.0, 100.0, 80.0, 100.0, 160.0]
    if angles == "half":
        angles = [170.0, 150.0, 135.0, 130.0, 135.0, 155.0]
    if angles == "bounce":
        angles = [170.0, 140.0, 95.0, 80.0, 130.0, 165.0]
    sh = (0.50, 0.40)
    el = (0.42, 0.50)
    v1 = math.atan2(el[1] - sh[1], el[0] - sh[0])  # 肩→肘方向角
    for a in angles:
        # 腕放在"肘角恰为 a"的方向上：θ2 = θ1 + (180° - a)
        th2 = v1 + math.radians(180.0 - a)
        wrist = (el[0] + 0.08 * math.cos(th2), el[1] + 0.08 * math.sin(th2))
        pts = _frame(sh, (0.50, 0.55), (0.45, 0.70), (0.45, 0.85),
                     extra={13: el, 15: wrist})
        frames.append(pts)
    return frames


def test_bench_good_rom_no_faults():
    faults = vr.check_bench(_bench_frames())
    assert faults == []


def test_bench_half_rom():
    faults = vr.check_bench(_bench_frames("half"))
    assert any(f["code"] == "BENCH_HALF_ROM" for f in faults)


def test_bench_bounce():
    faults = vr.check_bench(_bench_frames("bounce"))
    assert any(f["code"] == "BENCH_ELBOW_FRAME_CHANGE" for f in faults)


# ---- 入口与边界 ----

def test_analyze_unknown_exercise():
    faults = vr.analyze("clean_and_jerk", [])
    assert faults and faults[0]["code"] == "UNSUPPORTED"


def test_analyze_attaches_labels():
    faults = vr.analyze("squat", _squat_frames(0.60, 0.70))
    assert faults and all("label" in f for f in faults)


def test_empty_frames_no_crash():
    assert vr.check_squat([]) == []
    assert vr.check_hinge([]) == []
    assert vr.check_bench([]) == []


def test_right_side_fallback():
    """左侧不可见时用右侧关键点（15.3：拍摄方向不限）"""
    f = _frame((0.50, 0.30), (0.60, 0.60), (0.60, 0.70), (0.60, 0.85), side="right")
    s = vr._side(f)
    assert s["hip"] == (0.60, 0.60)
