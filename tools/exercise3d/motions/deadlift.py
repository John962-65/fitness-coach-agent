#!/usr/bin/env python3
"""M6.4-B B3：传统硬拉（deadlift）骨骼动画。

杠铃从地面（大片 r=0.225 → 杆心 y=0.225）拉起至身体伸展锁定，再下放回地。
- 肩位由「杠高 + 悬垂臂长」反解（手臂垂直杠），髋位由躯干前倾角反解——
  人、杠、手同一套运动学解算，同步由构造保证；
- 踝固定，双脚全程贴地；膝角随站起伸展；
- 前倾角 40°（离地把杆）→ 10°（锁定微屈髋，教学示例比例）。

教学示例声明：起始背角/锁定高度为常见教学比例，不构成个体化动作判定。
"""
from __future__ import annotations

import numpy as np

from ..rig import Rig
from .common import X, motion_doc, pitch, shoulder_mid, smooth, solve

PHASES = [
    {"key": "prep", "label": "准备（俯身握杆）", "t": [0.0, 0.5]},
    {"key": "pull", "label": "拉起（伸髋伸膝）", "t": [0.5, 1.6]},
    {"key": "lockout", "label": "锁定（站直）", "t": [1.6, 2.1]},
    {"key": "lower", "label": "下放", "t": [2.1, 3.1]},
    {"key": "finish", "label": "结束（杆落回地面）", "t": [3.1, 3.6]},
]
DURATION = 3.6
# 质量检查阈值（按动作类型声明）：铰链模式髋矢状面角天然深于蹲类
QUALITY_BOUNDS = {"max_hip_sag": 155.0}
GRIP_HALF = 0.26
BAR_Z = 0.05                    # 杆在脚中正上方（教学示例垂直杆轨迹）
BAR_Y_FLOOR, BAR_Y_LOCK = 0.225, 0.83
ARM_HANG = 0.52                 # 肩→握点垂直悬垂距（< 臂展 0.54，肘微屈）
TORSO = 0.47                    # 髋→肩沿躯干长
LEAN_FLOOR, LEAN_LOCK = 68.0, 10.0   # 起始躯干约 22° 高于水平（本骨架臂/躯干比例下的传统硬拉背角）；锁定微屈髋
ANKLES = {"Left": np.array([0.13, 0.12, 0.02]),
          "Right": np.array([-0.13, 0.12, 0.02])}


def depth(t: float) -> float:
    if t < 0.5:
        return 0.0
    if t < 1.6:
        return smooth((t - 0.5) / 1.1)
    if t < 2.1:
        return 1.0
    if t < 3.1:
        return 1.0 - smooth((t - 2.1) / 1.0)
    return 0.0


def frame(rig: Rig, t: float) -> dict:
    s = depth(t)
    bar = np.array([0.0, BAR_Y_FLOOR + (BAR_Y_LOCK - BAR_Y_FLOOR) * s, BAR_Z])
    lean = LEAN_FLOOR + (LEAN_LOCK - LEAN_FLOOR) * s
    torso = {
        "Hips": pitch(0.30 * lean),      # 世界目标分配（胸部世界俯仰=lean）
        "Spine": pitch(0.65 * lean),
        "Spine1": pitch(lean),
        "Neck": pitch(-0.5 * lean),
        "Head": pitch(-0.5 * lean),
    }
    # 肩必须在杠正上方（手臂垂直）：直杆假设给髋位初值，再用 FK 实际肩位
    # 做一次平移修正（刚体平移 1:1 传递，一次即精确）。
    shoulder = np.array([0.0, bar[1] + ARM_HANG, BAR_Z + 0.02])
    th = np.radians(lean)
    hips0 = np.array([0.0,
                      shoulder[1] - TORSO * np.cos(th),
                      shoulder[2] - TORSO * np.sin(th)])
    hips = hips0 + (shoulder - shoulder_mid(rig, torso, hips0))
    return solve(rig, torso, hips,
                 ankle_targets=ANKLES, knee_bend=np.array([0.0, 0.0, 1.0]),
                 foot_world={"Left": np.eye(3), "Right": np.eye(3)},
                 grips={"Left": bar + X * GRIP_HALF,
                        "Right": bar - X * GRIP_HALF},
                 elbow_bend=np.array([0.0, -1.0, -0.2]),
                 equip={"barbell": {"translation": bar, "rotation": None}})


def build() -> dict:
    rig = Rig.create()
    times = [round(i * 0.15, 3) for i in range(int(DURATION / 0.15) + 1)]
    frames = [frame(rig, t) for t in times]
    return motion_doc(
        "deadlift", "deadlift", DURATION, times, frames, PHASES,
        equipment=["barbell"],
        note="教学示例动画：常见比例的传统硬拉演示（髋铰链、杆贴身上行、"
             "锁定不过度后仰），非个体化动作诊断。",
        check_keys=["Left_ankle_drift", "Right_ankle_drift",
                    "Left_grip_gap", "Right_grip_gap"])
