#!/usr/bin/env python3
"""M6.4-B B2.1：杠铃深蹲（barbell_back_squat）骨骼动画运动学。

一个完整循环：准备 → 下蹲（离心）→ 底部 → 站起（向心）→ 结束，首尾姿态
一致以平滑循环。关键帧覆盖髋/膝/踝（足）、躯干、肩肘（手）与杠铃平移。

同步策略（B2.2 硬性要求）：杠位 = 双肩中点 + 胸廓上/后偏移（杠在斜方肌上），
双手握点 = 杠上固定位；手臂由肩→握点二连杆 IK 解算——人体、杠铃、双手
由同一套运动学解算生成，同步由构造保证（见 frames 自检 checks）。

教学示例声明：关节角度为常见教学示例比例（杠过脚中、躯干前倾角随深度增
大），不等于对任何个体理想姿态的判定（B2.3 纪律）。
"""
from __future__ import annotations

import numpy as np

from ..rig import (Rig, fk, ik2, frame_from_y, mat_from_axis_angle,
                   joint_world)

X = np.array([1.0, 0, 0])
Y = np.array([0, 1.0, 0])
Z = np.array([0, 0, 1.0])

# 相位表（秒）：准备/下蹲/底部/站起/结束
PHASES = [
    {"key": "prep", "label": "准备", "t": [0.0, 0.5]},
    {"key": "descend", "label": "下蹲（离心）", "t": [0.5, 1.7]},
    {"key": "bottom", "label": "底部", "t": [1.7, 2.1]},
    {"key": "ascend", "label": "站起（向心）", "t": [2.1, 3.3]},
    {"key": "finish", "label": "结束", "t": [3.3, 3.6]},
]
DURATION = 3.6
THIGH, SHIN = 0.42, 0.42
UPPER_ARM, FOREARM = 0.28, 0.26
TORSO_TO_SHOULDER = 0.49      # 髋中心 → 双肩中点（沿躯干，用于初值估计）
BAR_Z_TARGET = 0.05           # 杠铃 z 目标（≈脚中正上方；两遍解算钉住杠轨迹）
BAR_UP, BAR_BACK = 0.055, 0.062
GRIP_HALF = 0.30              # 握点半宽（略宽于肩）


def _smooth(u: float) -> float:
    return 3 * u * u - 2 * u * u * u


def depth(t: float) -> float:
    """s ∈ [0,1]：0=站姿，1=底部。相位分段 + smoothstep 缓动，循环闭合。"""
    if t < 0.5:
        return 0.05 * _smooth(t / 0.5)                    # 准备：轻微屈膝落位
    if t < 1.7:
        return 0.05 + 0.95 * _smooth((t - 0.5) / 1.2)     # 下蹲
    if t < 2.1:
        return 1.0                                        # 底部停顿
    if t < 3.3:
        return 1.0 - 0.95 * _smooth((t - 2.1) / 1.2)      # 站起
    return 0.05 * (1 - _smooth((t - 3.3) / 0.3))          # 结束回正


def _torso_pose(lean_deg: float) -> dict[str, np.ndarray]:
    def pitch(deg: float) -> np.ndarray:
        return mat_from_axis_angle(X, deg)

    return {
        "Hips": pitch(0.30 * lean_deg),
        "Spine": pitch(0.35 * lean_deg),
        "Spine1": pitch(0.35 * lean_deg),
        "Neck": pitch(-0.5 * lean_deg),
        "Head": pitch(-0.5 * lean_deg),
    }


def _bar_from_world(world: dict[str, np.ndarray]) -> np.ndarray:
    s_mid = (joint_world(world, "LeftArm") + joint_world(world, "RightArm")) / 2
    chest = world["Spine1"][:3, :3]
    return s_mid + chest @ Y * BAR_UP + chest @ Z * (-BAR_BACK)


def frame_pose(rig: Rig, t: float) -> dict:
    """单帧求解：返回 {rots: {骨骼: 世界3x3}, local_rots, hips, equip, checks}。

    两遍解算：先按躯干前倾估髋 z，再解算杠 z 与目标的偏差并平移髋部，
    使杠铃全程保持在脚中正上方（竖直杠轨迹，教学示例标准路径）。
    """
    s = depth(t)
    lean_deg = 4.0 + 25.0 * s
    hip_y = 0.96 - 0.38 * s

    # 第一遍：hip_z=0 估杠 z；髋 z 平移量对杠 z 是 1:1 传递 → 直接补偿
    torso = _torso_pose(lean_deg)
    w0, _ = fk(rig, torso, {"Hips": np.array([0.0, hip_y, 0.0])})
    hip_z = BAR_Z_TARGET - float(_bar_from_world(w0)[2])
    hips_pos = np.array([0.0, hip_y, hip_z])
    pose = dict(torso)

    world, _ = fk(rig, pose, {"Hips": hips_pos})

    # ---- 下肢 IK（踝固定，脚掌全程贴地）----
    ankles = {"Left": rig.bind_pos["LeftFoot"], "Right": rig.bind_pos["RightFoot"]}
    for side in ("Left", "Right"):
        H = joint_world(world, f"{side}UpLeg")
        A = ankles[side]
        K = ik2(H, A, THIGH, SHIN, bend_hint=Z)          # 膝朝前（+Z）
        pose[f"{side}UpLeg"] = frame_from_y(-(K - H) / np.linalg.norm(K - H), X)
        pose[f"{side}Leg"] = frame_from_y(-(A - K) / np.linalg.norm(A - K), X)
        pose[f"{side}Foot"] = np.eye(3)                  # 世界系恒定 → 脚掌贴地

    # ---- 杠位：双肩中点 + 胸廓系上/后偏移（杠在斜方肌上）----
    world, _ = fk(rig, pose, {"Hips": hips_pos})
    bar = _bar_from_world(world)

    # ---- 上肢 IK：手握点 = 杠上 ±GRIP_HALF ----
    for side, sx in (("Left", 1.0), ("Right", -1.0)):
        S = joint_world(world, f"{side}Arm")
        G = bar + X * (GRIP_HALF * sx)
        bend = np.array([0.0, -1.0, -0.35])
        bend /= np.linalg.norm(bend)                     # 肘朝下、略向后
        E = ik2(S, G, UPPER_ARM, FOREARM, bend_hint=bend)
        pose[f"{side}Arm"] = _frame_arm(sx, (E - S), X)
        pose[f"{side}ForeArm"] = _frame_arm(sx, (G - E), X)
        # 手长轴沿杠（bind 手沿 ±X），掌面朝向前臂方向
        pose[f"{side}Hand"] = _frame_hand(sx, (G - E) / np.linalg.norm(G - E))

    world2, local_rots = fk(rig, pose, {"Hips": hips_pos})

    # ---- 自检（同步/贴地由构造保证，此处量化验证）----
    checks = {}
    for side in ("Left", "Right"):
        checks[f"{side}_ankle_drift"] = float(np.linalg.norm(
            joint_world(world2, f"{side}Foot") - rig.bind_pos[f"{side}Foot"]))
        checks[f"{side}_grip_gap"] = float(np.linalg.norm(
            joint_world(world2, f"{side}Hand")
            - (bar + X * (GRIP_HALF * (1.0 if side == "Left" else -1.0)))))
    checks["bar_over_midfoot_z"] = float(bar[2])
    checks["hips_y"] = float(hips_pos[1])
    return {"rots": pose, "local_rots": local_rots, "hips": hips_pos,
            "equip": {"barbell": {"translation": bar, "rotation": None}},
            "checks": checks}


def _frame_arm(side_sign: float, seg: np.ndarray, x_hint: np.ndarray) -> np.ndarray:
    """上臂/前臂世界旋转：bind 长轴 = ±X → 世界 = ±seg 方向；X' = 长轴，
    Z' 取与 x_hint 正交后的叉积（避免翻滚）。"""
    d = seg / np.linalg.norm(seg)
    xv = side_sign * d
    zv = np.cross(x_hint, xv)
    nz = np.linalg.norm(zv)
    if nz < 1e-6:
        zv = np.cross(Y, xv)
        nz = np.linalg.norm(zv)
    zv = zv / nz
    yv = np.cross(zv, xv)
    return np.column_stack([xv, yv, zv])


def _frame_hand(side_sign: float, forearm_dir: np.ndarray) -> np.ndarray:
    """手：长轴沿杠 ±X，Y' 贴前臂方向（掌面包握杠铃）。"""
    xv = X * side_sign
    yv = forearm_dir - np.dot(forearm_dir, xv) * xv
    ny = np.linalg.norm(yv)
    yv = yv / ny if ny > 1e-6 else Y
    zv = np.cross(xv, yv)
    return np.column_stack([xv, yv, zv])


def build() -> dict:
    """生成深蹲动画文档（build.py 消费）。"""
    rig = Rig.create()
    times = [round(i * 0.15, 3) for i in range(int(DURATION / 0.15) + 1)]
    frames = [frame_pose(rig, t) for t in times]
    # 首尾帧必须一致（循环平滑）
    assert np.allclose(frames[0]["rots"]["LeftUpLeg"], frames[-1]["rots"]["LeftUpLeg"], atol=1e-9)
    worst = {
        "ankle_drift": max(max(f["checks"]["Left_ankle_drift"],
                               f["checks"]["Right_ankle_drift"]) for f in frames),
        "grip_gap": max(max(f["checks"]["Left_grip_gap"],
                            f["checks"]["Right_grip_gap"]) for f in frames),
        "bar_z_minmax": (min(f["checks"]["bar_over_midfoot_z"] for f in frames),
                         max(f["checks"]["bar_over_midfoot_z"] for f in frames)),
    }
    return {
        "exercise_id": "barbell_back_squat",
        "animation_name": "squat",
        "duration": DURATION,
        "loop": True,
        "times": times,
        "frames": frames,
        "phases": PHASES,
        "equipment": ["barbell"],
        "checks": worst,
        "note": "教学示例动画：常见比例的深蹲演示，非个体化动作诊断。",
    }
