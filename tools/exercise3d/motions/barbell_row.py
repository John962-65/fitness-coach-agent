#!/usr/bin/env python3
"""M6.4-B B3：杠铃划船（barbell_row）骨骼动画。

俯身约 42° 站位（躯干全程稳定如板），杠铃从直臂悬垂拉向下腹部、顶点
挤压、离心回放。躯干/膝角固定，仅上肢与杠铃运动——强调"躯干像一块板"。

教学示例声明：俯身角/拉起位置为常见教学比例，非个体化动作判定。
"""
from __future__ import annotations

import numpy as np

from ..rig import Rig
from .common import X, motion_doc, pitch, shoulder_mid, smooth, solve

PHASES = [
    {"key": "prep", "label": "准备（俯身悬垂）", "t": [0.0, 0.5]},
    {"key": "row", "label": "拉起（肩胛先动）", "t": [0.5, 1.4]},
    {"key": "top", "label": "顶点（背部挤压）", "t": [1.4, 1.8]},
    {"key": "return", "label": "回放（离心控制）", "t": [1.8, 3.0]},
    {"key": "finish", "label": "结束（回到悬垂）", "t": [3.0, 3.6]},
]
DURATION = 3.6
GRIP_HALF = 0.26
LEAN = 42.0
TORSO = 0.47
HIPS = np.array([0.0, 0.86, -0.09])
ANKLES = {"Left": np.array([0.13, 0.12, 0.01]),
          "Right": np.array([-0.13, 0.12, 0.01])}


def _torso() -> dict[str, np.ndarray]:
    return {
        "Hips": pitch(0.30 * LEAN),
        "Spine": pitch(0.35 * LEAN),
        "Spine1": pitch(0.35 * LEAN),
        "Neck": pitch(-0.4 * LEAN),   # 头颈中立（不抬头看镜子）
        "Head": pitch(-0.4 * LEAN),
    }


def _bar_path(rig: Rig) -> tuple[np.ndarray, np.ndarray]:
    """悬垂位/顶点位由真实 FK 肩位推导（躯干固定，路径全程一致）。"""
    s = shoulder_mid(rig, _torso(), HIPS)
    hang = np.array([0.0, s[1] - 0.515, s[2]])          # 直臂悬垂：肩正下方
    top = np.array([0.0, 0.96, 0.12])                    # 拉至下腹（贴躯干）
    return hang, top


def depth(t: float) -> float:
    if t < 0.5:
        return 0.0
    if t < 1.4:
        return smooth((t - 0.5) / 0.9)
    if t < 1.8:
        return 1.0
    if t < 3.0:
        return 1.0 - smooth((t - 1.8) / 1.2)
    return 0.0


def frame(rig: Rig, t: float, path: tuple[np.ndarray, np.ndarray]) -> dict:
    s = depth(t)
    bar = path[0] + (path[1] - path[0]) * s
    return solve(rig, _torso(), HIPS,
                 ankle_targets=ANKLES, knee_bend=np.array([0.0, 0.0, 1.0]),
                 foot_world={"Left": np.eye(3), "Right": np.eye(3)},
                 grips={"Left": bar + X * GRIP_HALF,
                        "Right": bar - X * GRIP_HALF},
                 elbow_bend=np.array([0.0, 0.8, -0.6]),   # 肘向上向后
                 equip={"barbell": {"translation": bar, "rotation": None}})


def build() -> dict:
    rig = Rig.create()
    path = _bar_path(rig)
    times = [round(i * 0.15, 3) for i in range(int(DURATION / 0.15) + 1)]
    frames = [frame(rig, t, path) for t in times]
    return motion_doc(
        "barbell_row", "barbell_row", DURATION, times, frames, PHASES,
        equipment=["barbell"],
        note="教学示例动画：常见比例的俯身杠铃划船演示（躯干稳定约 42°、"
             "拉向下腹、离心控制），非个体化动作诊断。",
        check_keys=["Left_ankle_drift", "Right_ankle_drift",
                    "Left_grip_gap", "Right_grip_gap"])
