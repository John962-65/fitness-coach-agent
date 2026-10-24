#!/usr/bin/env python3
"""M6.4-B B3：哑铃肩推（dumbbell_shoulder_press）骨骼动画。

坐姿带靠背训练凳（凳体 + 立式靠背），哑铃从耳侧（小臂垂直）弧线推起
向头顶上方汇聚，顶峰不碰撞、肘不锁死，下放回耳侧。
- 左右哑铃为两个独立器械节点，分别由对应手 IK 握持（同步构造保证）；
- 臀部贴凳、双脚踩地、腰部不反弓（躯干直立贴靠背）。

教学示例声明：轨迹弧线与握位为常见教学比例，非个体化动作判定。
"""
from __future__ import annotations

import numpy as np

from ..rig import Rig
from .common import motion_doc, smooth, solve

PHASES = [
    {"key": "prep", "label": "准备（哑铃在耳侧）", "t": [0.0, 0.5]},
    {"key": "press", "label": "上推（弧线汇聚）", "t": [0.5, 1.5]},
    {"key": "top", "label": "顶峰（肘不锁死）", "t": [1.5, 1.9]},
    {"key": "lower", "label": "下降（回耳侧）", "t": [1.9, 3.1]},
    {"key": "finish", "label": "结束", "t": [3.1, 3.6]},
]
DURATION = 3.6
HIPS = np.array([0.0, 0.575, -0.45])       # 坐在凳上、背贴靠背（肩高≈1.045）
ANKLES = {"Left": np.array([0.13, 0.12, 0.22]),
          "Right": np.array([-0.13, 0.12, 0.22])}
DB_BOTTOM = {"Left": np.array([0.26, 1.26, -0.40]),   # 耳侧（小臂垂直）
             "Right": np.array([-0.26, 1.26, -0.40])}
DB_TOP = {"Left": np.array([0.13, 1.56, -0.38]),      # 弧线汇聚（肘微屈不锁死）
          "Right": np.array([-0.13, 1.56, -0.38])}
ELBOW = {"Left": np.array([0.30, -0.9, 0.30]),    # 肘向前下（小臂垂直）
         "Right": np.array([-0.30, -0.9, 0.30])}


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
    db = {side: DB_BOTTOM[side] + (DB_TOP[side] - DB_BOTTOM[side]) * s
          for side in ("Left", "Right")}
    return solve(
        rig, {}, HIPS,                      # 躯干直立：无附加旋转
        ankle_targets=ANKLES, knee_bend=np.array([0.0, 0.0, 1.0]),
        foot_world={"Left": np.eye(3), "Right": np.eye(3)},
        grips=db, elbow_bend=ELBOW,
        equip={**{f"dumbbell_{side[0]}": {"translation": db[side], "rotation": None}
                  for side in ("Left", "Right")},
               "bench_upright": {"translation": np.zeros(3), "rotation": None}})


def build() -> dict:
    rig = Rig.create()
    times = [round(i * 0.15, 3) for i in range(int(DURATION / 0.15) + 1)]
    frames = [frame(rig, t) for t in times]
    return motion_doc(
        "dumbbell_shoulder_press", "db_shoulder_press", DURATION, times,
        frames, PHASES,
        equipment=[{"node": "dumbbell_L", "mesh": "dumbbell"},
                   {"node": "dumbbell_R", "mesh": "dumbbell"},
                   {"node": "bench_upright", "mesh": "bench_upright"}],
        note="教学示例动画：坐姿哑铃肩推演示（弧线上推、小臂垂直、"
             "顶峰不碰撞），非个体化动作诊断。",
        check_keys=["Left_ankle_drift", "Right_ankle_drift",
                    "Left_grip_gap", "Right_grip_gap"])
