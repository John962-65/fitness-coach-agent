#!/usr/bin/env python3
"""M6.4-B B3：动作脚本公共求解器（复用骨架/IK/自检，避免每动作一套页面）。

所有动作共用同一骨架、同一解算管线：
躯干世界姿态 → FK → 下肢 IK（踝目标 + 膝弯向）→ 器械握点 →
上肢 IK（肘弯向）→ FK 烘焙局部旋转 + 帧自检（脚贴地/握点贴合）。
"""
from __future__ import annotations

import numpy as np

from ..rig import (Rig, fk, ik2, frame_from_y, mat_from_axis_angle, joint_world)

X = np.array([1.0, 0, 0])
Y = np.array([0, 1.0, 0])
Z = np.array([0, 0, 1.0])
THIGH, SHIN = 0.42, 0.42
UPPER_ARM, FOREARM = 0.28, 0.26


def pitch(deg: float) -> np.ndarray:
    return mat_from_axis_angle(X, deg)


def smooth(u: float) -> float:
    return 3 * u * u - 2 * u * u * u


def _frame_arm(side_sign: float, seg: np.ndarray, x_hint: np.ndarray) -> np.ndarray:
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


def _frame_hand(side_sign: float, ref_dir: np.ndarray) -> np.ndarray:
    """手长轴沿器械握轴（默认 ±X），Y' 贴前臂方向。"""
    xv = X * side_sign
    yv = ref_dir - np.dot(ref_dir, xv) * xv
    ny = np.linalg.norm(yv)
    yv = yv / ny if ny > 1e-6 else Y
    zv = np.cross(xv, yv)
    return np.column_stack([xv, yv, zv])


def shoulder_mid(rig: Rig, torso: dict[str, np.ndarray],
                 hips_pos: np.ndarray) -> np.ndarray:
    """当前躯干姿态下双肩中点（用于把器械路径锚定到真实 FK 结果）。"""
    world, _ = fk(rig, torso, {"Hips": hips_pos})
    return (joint_world(world, "LeftArm") + joint_world(world, "RightArm")) / 2


def solve(rig: Rig, torso: dict[str, np.ndarray], hips_pos: np.ndarray,
          *, ankle_targets: dict[str, np.ndarray] | None = None,
          knee_bend: np.ndarray = Z, foot_world: dict[str, np.ndarray] | None = None,
          grips: dict[str, np.ndarray] | None = None,
          elbow_bend: np.ndarray | dict[str, np.ndarray] | None = None,
          equip: dict[str, dict] | None = None,
          hand_axis: str = "x") -> dict:
    """解算一帧。返回 build.py 消费的帧结构（含 local_rots 与自检）。

    - ankle_targets：{Left/Right: 世界踝位}，None 则双腿保持绑定姿态；
    - grips：{Left/Right: 世界握点}（来自器械，同步由构造保证）；
    - elbow_bend：全局弯向或 {Left/Right: 弯向}（左右异向，如肩推）；
    - equip：{节点名: {"translation": v3, "rotation": mat3|None}}；
    - hand_axis："x" 手长轴沿 ±X（杠铃/哑铃），"seg" 沿前臂方向。
    """
    pose = dict(torso)
    world, _ = fk(rig, pose, {"Hips": hips_pos})

    if ankle_targets:
        for side, A in ankle_targets.items():
            H = joint_world(world, f"{side}UpLeg")
            K = ik2(H, A, THIGH, SHIN, bend_hint=knee_bend)
            pose[f"{side}UpLeg"] = frame_from_y(-(K - H) / np.linalg.norm(K - H), X)
            pose[f"{side}Leg"] = frame_from_y(-(A - K) / np.linalg.norm(A - K), X)
            pose[f"{side}Foot"] = (foot_world or {}).get(side, np.eye(3))
        world, _ = fk(rig, pose, {"Hips": hips_pos})

    if grips:
        assert elbow_bend is not None
        for side, sx in (("Left", 1.0), ("Right", -1.0)):
            G = grips[side]
            S = joint_world(world, f"{side}Arm")
            E = ik2(S, G, UPPER_ARM, FOREARM,
                    bend_hint=elbow_bend[side] if isinstance(elbow_bend, dict)
                    else elbow_bend)
            pose[f"{side}Arm"] = _frame_arm(sx, E - S, X)
            fore_dir = (G - E) / np.linalg.norm(G - E)
            pose[f"{side}ForeArm"] = _frame_arm(sx, G - E, X)
            pose[f"{side}Hand"] = (_frame_hand(sx, fore_dir) if hand_axis == "x"
                                   else _frame_arm(sx, fore_dir, Y))
        world, _ = fk(rig, pose, {"Hips": hips_pos})

    world2, local_rots = fk(rig, pose, {"Hips": hips_pos})

    checks: dict[str, float] = {}
    if ankle_targets:
        for side, A in ankle_targets.items():
            checks[f"{side}_ankle_drift"] = float(np.linalg.norm(
                joint_world(world2, f"{side}Foot") - A))
    if grips:
        for side, G in grips.items():
            checks[f"{side}_grip_gap"] = float(np.linalg.norm(
                joint_world(world2, f"{side}Hand") - G))
    return {"rots": pose, "local_rots": local_rots, "hips": hips_pos,
            "equip": equip or {}, "checks": checks}


def motion_doc(exercise_id: str, animation_name: str, duration: float,
               times: list[float], frames: list[dict], phases: list[dict],
               equipment: list[dict], note: str,
               check_keys: list[str]) -> dict:
    """汇总 motion 文档 + 最差自检值（构造级同步应接近 0）。"""
    worst: dict[str, float | tuple] = {}
    for k in check_keys:
        if k.endswith("_drift") or k.endswith("_gap"):
            worst[k] = max(abs(f["checks"][k]) for f in frames)
    first, last = frames[0]["rots"], frames[-1]["rots"]
    common = set(first) & set(last)
    assert all(np.allclose(first[b], last[b], atol=1e-9) for b in common), \
        "首尾姿态不一致（循环会跳变）"
    return {"exercise_id": exercise_id, "animation_name": animation_name,
            "duration": duration, "loop": True, "times": times, "frames": frames,
            "phases": phases, "equipment": equipment, "checks": worst, "note": note}
