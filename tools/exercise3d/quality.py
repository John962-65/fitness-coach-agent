#!/usr/bin/env python3
"""M6.4-B 交付审查 P1-2：三维动作质量离线检查（运动学自洽 ≠ 动作合理）。

在既有运动学自检（贴地/握点）之上，补充几何与连续性约束：

1. 关节连续性：相邻关键帧骨骼旋转角变化 ≤ 阈值（含首尾衔接，循环平滑）；
2. 关节活动范围：膝屈曲/髋矢状面角不超界（默认宽松阈值，各动作可覆盖）；
3. 器械-头部间隙：杠铃杆/哑铃不得进入头部球体（教学动作不打头）；
4. 器械-地面间隙：杠铃片底缘不低于地面（允许恰好触地）；
5. 足底接触：双脚世界旋转 ≈ 单位（脚掌平贴地面，不侧翻/翘起）；
6. 双侧对称：左右镜像后对应骨骼旋转一致（双侧动作）。

阈值按教学示例动作设定，是"离线几何合理性"门槛，不是动作学评分。
"""
from __future__ import annotations

import numpy as np

from .rig import Rig, BONE_NAMES, fk, joint_world

# 默认阈值（度 / 米）
MAX_FRAME_DELTA_DEG = 30.0     # 相邻关键帧（0.15s）单骨骼旋转角变化
MAX_LOOP_DELTA_DEG = 15.0      # 首尾衔接（循环平滑性要求更严）
MAX_KNEE_FLEX_DEG = 150.0
MAX_HIP_SAG_DEG = 140.0
HEAD_CLEARANCE_MARGIN = 0.005  # 器械与头部球的最小额外间隙
FOOT_TILT_MAX_DEG = 2.5        # 足部世界旋转偏离单位阵的上限
SYMMETRY_MAX_DEG = 8.0         # 左右镜像后旋转差
PLATE_RADIUS = 0.225           # 大片半径（器械几何常量）
HEAD_R = 0.11
MIRROR = np.diag([-1.0, 1.0, 1.0])


class QualityError(ValueError):
    """动作质量约束被违反（导出应中止）。"""


def _rot_angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    """两旋转矩阵的相对旋转角（度）。"""
    r = a.T @ b
    c = (np.trace(r) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


def _seg_point_dist(p0: np.ndarray, p1: np.ndarray, q: np.ndarray) -> float:
    d = p1 - p0
    t = float(np.clip(np.dot(q - p0, d) / np.dot(d, d), 0.0, 1.0))
    return float(np.linalg.norm(p0 + t * d - q))


def _angle_at(b: np.ndarray, a: np.ndarray, c: np.ndarray) -> float:
    """∠abc（度）。"""
    u, v = a - b, c - b
    cosv = np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v))
    return float(np.degrees(np.arccos(np.clip(cosv, -1.0, 1.0))))


def check(doc: dict, rig: Rig, *,
          max_knee_flex: float = MAX_KNEE_FLEX_DEG,
          max_hip_sag: float = MAX_HIP_SAG_DEG,
          expect_symmetric: bool = True) -> dict:
    frames = doc["frames"]
    issues: list[str] = []
    worst: dict[str, float] = {}

    # 世界关节（用于角度/间隙）
    worlds = [fk(rig, f["rots"], {"Hips": np.asarray(f["hips"])})[0]
              for f in frames]

    def wj(i: int, bone: str) -> np.ndarray:
        return joint_world(worlds[i], bone)

    def head_center(i: int) -> np.ndarray:
        return wj(i, "Head") + worlds[i]["Head"][:3, :3] @ np.array([0, 0.10, 0.01])

    # ---- 1. 关节连续性（相邻帧 + 首尾衔接）----
    animated = [b for b in BONE_NAMES
                if any(b in f["local_rots"] for f in frames)]
    max_delta, max_loop = 0.0, 0.0
    for bone in animated:
        rots = [f["local_rots"].get(bone, np.eye(3)) for f in frames]
        for i in range(len(rots) - 1):
            max_delta = max(max_delta, _rot_angle_deg(rots[i], rots[i + 1]))
        max_loop = max(max_loop, _rot_angle_deg(rots[-1], rots[0]))
    worst["frame_delta_deg"] = round(max_delta, 2)
    worst["loop_delta_deg"] = round(max_loop, 2)
    if max_delta > MAX_FRAME_DELTA_DEG:
        issues.append(f"关节连续性：相邻帧旋转角 {max_delta:.1f}° > {MAX_FRAME_DELTA_DEG}°")
    if max_loop > MAX_LOOP_DELTA_DEG:
        issues.append(f"循环平滑：首尾衔接旋转角 {max_loop:.1f}° > {MAX_LOOP_DELTA_DEG}°")

    # ---- 2. 关节活动范围（膝屈曲 / 髋矢状面角）----
    knee_max, hip_max = 0.0, 0.0
    for i in range(len(frames)):
        for side in ("Left", "Right"):
            H, K, A = (wj(i, f"{side}UpLeg"), wj(i, f"{side}Leg"),
                       wj(i, f"{side}Foot"))
            knee_flex = 180.0 - _angle_at(K, H, A)
            knee_max = max(knee_max, knee_flex)
            C = wj(i, f"{side}Arm")
            hip_ang = 180.0 - _angle_at(H, C, K)   # 躯干-大腿夹角（矢状近似）
            hip_max = max(hip_max, hip_ang)
    worst["knee_flex_deg"] = round(knee_max, 1)
    worst["hip_angle_deg"] = round(hip_max, 1)
    if knee_max > max_knee_flex:
        issues.append(f"膝屈曲 {knee_max:.0f}° > {max_knee_flex}°")
    if hip_max > max_hip_sag:
        issues.append(f"髋矢状面角 {hip_max:.0f}° > {max_hip_sag}°")

    # ---- 3. 器械-头部间隙 / 4. 器械-地面间隙 ----
    head_clear, plate_floor = 1e9, 1e9
    for i, f in enumerate(frames):
        hc = head_center(i)
        for _name, eq in f["equip"].items():
            if "dumbbell" in _name or "barbell" in _name:
                pos = np.asarray(eq["translation"])
                if "dumbbell" in _name:
                    head_clear = min(head_clear, float(np.linalg.norm(pos - hc))
                                     - HEAD_R - 0.075)
                else:
                    axis = pos + np.array([0.82, 0, 0.0])   # 杆身（去掉套筒）
                    axis2 = pos - np.array([0.82, 0, 0.0])
                    head_clear = min(head_clear,
                                     _seg_point_dist(axis, axis2, hc) - HEAD_R - 0.014)
                    plate_floor = min(plate_floor, pos[1] - PLATE_RADIUS)
    worst["head_clearance_m"] = round(head_clear, 3)
    if head_clear < -HEAD_CLEARANCE_MARGIN:
        issues.append(f"器械进入头部区域：间隙 {head_clear:.3f}m")
    worst["plate_floor_gap_m"] = round(plate_floor, 3)
    if plate_floor < -0.004:
        issues.append(f"杠铃片穿入地面 {plate_floor:.3f}m")

    # ---- 5. 足底接触（双脚世界旋转 ≈ 单位）----
    foot_tilt = 0.0
    for f in frames:
        for side in ("Left", "Right"):
            R = f["rots"].get(f"{side}Foot")
            if R is not None:
                foot_tilt = max(foot_tilt, _rot_angle_deg(np.eye(3), R))
    worst["foot_tilt_deg"] = round(foot_tilt, 2)
    if foot_tilt > FOOT_TILT_MAX_DEG:
        issues.append(f"脚掌倾斜 {foot_tilt:.1f}° > {FOOT_TILT_MAX_DEG}°")

    # ---- 6. 双侧对称 ----
    # 腿：旋转矩阵镜像比对（左右构造约定一致）；
    # 臂：肘部世界坐标镜像比对（手臂 frame 带左右方向约定，用几何口径）
    sym, arm_sym = 0.0, 0.0
    if expect_symmetric:
        for bone in ("UpLeg", "Leg"):
            for f in frames:
                L = f["rots"].get(f"Left{bone}")
                R = f["rots"].get(f"Right{bone}")
                if L is not None and R is not None:
                    sym = max(sym, _rot_angle_deg(L, MIRROR @ R @ MIRROR))
        for i in range(len(frames)):
            eL = wj(i, "LeftForeArm")
            eR = wj(i, "RightForeArm")
            arm_sym = max(arm_sym, float(np.linalg.norm(eL - MIRROR @ eR)))
        worst["symmetry_deg"] = round(sym, 2)
        worst["arm_symmetry_m"] = round(arm_sym, 4)
        if sym > SYMMETRY_MAX_DEG:
            issues.append(f"左右腿不对称 {sym:.1f}° > {SYMMETRY_MAX_DEG}°")
        if arm_sym > 0.012:
            issues.append(f"左右肘位置镜像偏差 {arm_sym:.3f}m > 0.012m")

    if issues:
        raise QualityError(f"{doc['exercise_id']} 动作质量检查未通过：\n  - "
                           + "\n  - ".join(issues))
    return worst
