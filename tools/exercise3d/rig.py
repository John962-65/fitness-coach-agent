#!/usr/bin/env python3
"""M6.4-B B2：人体骨架定义 + 前向运动学（真实骨骼层级，蒙皮动画基础）。

Blender 在本环境不可用；本包以程序化方式构建等价资产：
- rig.py 定义 Mixamo 风格命名的骨骼层级与站姿绑定姿态（Y-up，米制，
  角色面朝 +Z，双脚着地 y=0）；
- 关键帧动画由各动作脚本（motions/）以「目标世界姿态 → 局部旋转」烘焙，
  保证双脚贴地、手部握点与器械由同一套运动学解算同步。

此处生成的资产即"可编辑源"：改骨骼/动画请改本包并重新导出 GLB
（等价于 .blend 工程源文件的角色，见交付报告说明）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# 骨骼名（Mixamo 风格；左右对称）
BONES = [
    # (name, parent, bind_offset_from_parent)
    ("Hips", None, (0.0, 0.98, 0.0)),
    ("Spine", "Hips", (0.0, 0.14, 0.0)),
    ("Spine1", "Spine", (0.0, 0.18, 0.0)),
    ("Neck", "Spine1", (0.0, 0.20, 0.0)),
    ("Head", "Neck", (0.0, 0.09, 0.0)),
    ("HeadTop_End", "Head", (0.0, 0.17, 0.0)),
    ("LeftShoulder", "Spine1", (0.05, 0.15, 0.0)),
    ("LeftArm", "LeftShoulder", (0.15, 0.0, 0.0)),
    ("LeftForeArm", "LeftArm", (0.28, 0.0, 0.0)),
    ("LeftHand", "LeftForeArm", (0.26, 0.0, 0.0)),
    ("LeftHandEnd", "LeftHand", (0.16, 0.0, 0.0)),
    ("RightShoulder", "Spine1", (-0.05, 0.15, 0.0)),
    ("RightArm", "RightShoulder", (-0.15, 0.0, 0.0)),
    ("RightForeArm", "RightArm", (-0.28, 0.0, 0.0)),
    ("RightHand", "RightForeArm", (-0.26, 0.0, 0.0)),
    ("RightHandEnd", "RightHand", (-0.16, 0.0, 0.0)),
    ("LeftUpLeg", "Hips", (0.11, -0.02, 0.0)),
    ("LeftLeg", "LeftUpLeg", (0.0, -0.42, 0.0)),
    ("LeftFoot", "LeftLeg", (0.0, -0.42, 0.0)),
    ("LeftToeBase", "LeftFoot", (0.0, -0.07, 0.16)),
    ("LeftToe_End", "LeftToeBase", (0.0, 0.0, 0.08)),
    ("RightUpLeg", "Hips", (-0.11, -0.02, 0.0)),
    ("RightLeg", "RightUpLeg", (0.0, -0.42, 0.0)),
    ("RightFoot", "RightLeg", (0.0, -0.42, 0.0)),
    ("RightToeBase", "RightFoot", (0.0, -0.07, 0.16)),
    ("RightToe_End", "RightToeBase", (0.0, 0.0, 0.08)),
]
BONE_NAMES = [b[0] for b in BONES]
CHILDREN: dict[str, list[str]] = {n: [] for n in BONE_NAMES}
for _n, _p, _o in BONES:
    if _p:
        CHILDREN[_p].append(_n)


# ---------- 四元数/矩阵小工具（wxyz 输入输出与 glTF 一致用 xyzw 处注意转换）----------

def quat_from_mat(m: np.ndarray) -> np.ndarray:
    """旋转矩阵 → 四元数 (x, y, z, w)（glTF 顺序）。"""
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w])
    return q / np.linalg.norm(q)


def mat_from_axis_angle(axis: np.ndarray, deg: float) -> np.ndarray:
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    th = np.radians(deg)
    x, y, z = a * np.sin(th / 2)
    w = np.cos(th / 2)
    return mat_from_quat(np.array([x, y, z, w]))


def mat_from_quat(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def frame_from_y(y_dir: np.ndarray, x_hint: np.ndarray) -> np.ndarray:
    """构造列向量为 (X', Y', Z') 的旋转矩阵：Y'=y_dir，X' 尽量贴近 x_hint。"""
    yv = y_dir / np.linalg.norm(y_dir)
    xv = x_hint - np.dot(x_hint, yv) * yv
    nx = np.linalg.norm(xv)
    if nx < 1e-6:  # x_hint 与 y 共线：任取正交向量
        tmp = np.array([1.0, 0, 0]) if abs(yv[0]) < 0.9 else np.array([0, 0, 1.0])
        xv = tmp - np.dot(tmp, yv) * yv
        nx = np.linalg.norm(xv)
    xv = xv / nx
    zv = np.cross(xv, yv)
    return np.column_stack([xv, yv, zv])


def ik2(a: np.ndarray, b: np.ndarray, l1: float, l2: float,
        bend_hint: np.ndarray) -> np.ndarray:
    """二连杆 IK：a=根(如髋)，b=末端(如踝)，l1=根到中(大腿)，l2=中到末端(小腿)。
    返回中间关节（膝）；bend_hint 指出弯曲方向一侧（如膝盖朝 +Z）。"""
    d = np.linalg.norm(b - a)
    d = float(np.clip(d, abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4))
    u = (b - a) / np.linalg.norm(b - a)
    aa = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = np.sqrt(max(l1 * l1 - aa * aa, 0.0))
    n = bend_hint - np.dot(bend_hint, u) * u
    nn = np.linalg.norm(n)
    if nn < 1e-6:
        raise ValueError("bend_hint 与根-末端轴共线")
    n = n / nn
    return a + aa * u + h * n


# ---------- 绑定姿态与 FK ----------

@dataclass
class Rig:
    bind_pos: dict[str, np.ndarray] = field(default_factory=dict)  # 关节世界坐标（绑定姿态）
    offsets: dict[str, np.ndarray] = field(default_factory=dict)   # 相对父关节偏移
    parents: dict[str, str | None] = field(default_factory=dict)

    @classmethod
    def create(cls) -> "Rig":
        rig = cls()
        for name, parent, off in BONES:
            o = np.array(off, dtype=float)
            rig.offsets[name] = o
            rig.parents[name] = parent
            rig.bind_pos[name] = (rig.bind_pos[parent] + o) if parent else o.copy()
        return rig

    def chain(self, end: str) -> list[str]:
        """根→end 的骨骼链。"""
        out, n = [], end
        while n:
            out.append(n)
            n = self.parents[n]
        return out[::-1]


def fk(rig: Rig, pose: dict[str, np.ndarray],
       translations: dict[str, np.ndarray] | None = None
       ) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """前向运动学：pose={骨骼: 目标**世界**旋转矩阵}，translations 覆盖个别
    骨骼局部平移（如 Hips 根位移）。返回 (世界矩阵, 局部旋转矩阵)。

    局部旋转 = 父世界旋转的逆 × 目标世界旋转；未给目标的骨骼局部旋转为
    单位阵（跟随父级）。两遍调用支撑 IK：先给躯干目标得到下肢/肩部世界
    位置，再补全四肢目标得到全部局部旋转（即 GLB 动画通道的旋转值）。
    """
    world: dict[str, np.ndarray] = {}
    local_rots: dict[str, np.ndarray] = {}
    for name in BONE_NAMES:
        parent = rig.parents[name]
        off = (translations or {}).get(name, rig.offsets[name])
        # 局部旋转必须相对「父骨骼」的世界旋转（而非迭代顺序上一个骨骼）
        parent_rot = (world[parent][:3, :3] if parent else np.eye(3))
        target = pose.get(name)
        local_rot = parent_rot.T @ target if target is not None else np.eye(3)
        local_rots[name] = local_rot
        local = np.eye(4)
        local[:3, :3] = local_rot
        local[:3, 3] = off
        world[name] = (world[parent] @ local) if parent else local.copy()
    return world, local_rots


def bind_world_mats(rig: Rig) -> dict[str, np.ndarray]:
    """绑定姿态的世界矩阵（骨骼无旋转，仅层级平移）。"""
    return fk(rig, {})[0]


def joint_world(world: dict[str, np.ndarray], bone: str) -> np.ndarray:
    """骨骼头部关节（= 骨骼原点）的世界坐标。"""
    return world[bone][:3, 3]
