#!/usr/bin/env python3
"""M6.4-B B3：杠铃平板卧推（barbell_bench_press）骨骼动画。

人体仰卧平凳（头朝 −Z），双脚踩地，杠铃从直臂支撑位下放至胸上、再推起。
- 凳面顶 y=0.465，人体躯干轴线 y≈0.575（仰卧 = Hips 世界俯仰 −90°）；
- 肩部由 FK 得到；握点 = 杠上 ±0.28（比肩宽 1.5 倍的简化），双臂 IK；
- 杠路径：锁定位 y≈1.04 → 触胸 y≈0.70，z 略向脚侧（乳线）；
- 踝固定于地面，脚掌全程贴地。

教学示例声明：握距/触胸点为常见教学比例，不构成个体化动作判定。
"""
from __future__ import annotations

import numpy as np

from ..rig import Rig
from .common import X, Y, Z, motion_doc, pitch, smooth, solve

PHASES = [
    {"key": "prep", "label": "准备（直臂支撑）", "t": [0.0, 0.5]},
    {"key": "descend", "label": "下放（离心）", "t": [0.5, 1.5]},
    {"key": "bottom", "label": "底部（触胸）", "t": [1.5, 1.9]},
    {"key": "press", "label": "推起（向心）", "t": [1.9, 3.1]},
    {"key": "finish", "label": "结束（锁定）", "t": [3.1, 3.6]},
]
DURATION = 3.6
GRIP_HALF = 0.28
BAR_Y_TOP, BAR_Y_BOTTOM = 1.04, 0.70
BAR_Z_TOP, BAR_Z_BOTTOM = -0.47, -0.41      # 锁定位在肩正上，触胸略向脚侧
HIPS_POS = np.array([0.0, 0.575, 0.20])     # 骨盆在凳上（仰卧）


def depth(t: float) -> float:
    if t < 0.5:
        return 0.0
    if t < 1.5:
        return smooth((t - 0.5) / 1.0)
    if t < 1.9:
        return 1.0
    if t < 3.1:
        return 1.0 - smooth((t - 1.9) / 1.2)
    return 0.0


def frame(rig: Rig, t: float) -> dict:
    s = depth(t)
    bar = np.array([0.0,
                    BAR_Y_TOP + (BAR_Y_BOTTOM - BAR_Y_TOP) * s,
                    BAR_Z_TOP + (BAR_Z_BOTTOM - BAR_Z_TOP) * s])
    torso = {  # 仰卧：整体绕 X −90°；头颈保持中立（面朝上）
        "Hips": pitch(-90.0),
    }
    grips = {
        "Left": bar + X * GRIP_HALF,
        "Right": bar - X * GRIP_HALF,
    }
    return solve(rig, torso, HIPS_POS,
                 ankle_targets={
                     "Left": np.array([0.15, 0.12, 0.55]),
                     "Right": np.array([-0.15, 0.12, 0.55])},
                 knee_bend=Y + Z * 0.3,
                 foot_world={"Left": np.eye(3), "Right": np.eye(3)},
                 grips=grips,
                 elbow_bend=np.array([0.0, -0.6, 1.0]),
                 equip={"barbell": {"translation": bar, "rotation": None}})


def build() -> dict:
    rig = Rig.create()
    times = [round(i * 0.15, 3) for i in range(int(DURATION / 0.15) + 1)]
    frames = [frame(rig, t) for t in times]
    return motion_doc(
        "barbell_bench_press", "bench_press", DURATION, times, frames, PHASES,
        equipment=["barbell"],
        note="教学示例动画：常见比例的平板卧推演示（仰卧平凳、杠铃触胸位），"
             "非个体化动作诊断。",
        check_keys=["Left_ankle_drift", "Right_ankle_drift",
                    "Left_grip_gap", "Right_grip_gap"])
