#!/usr/bin/env python3
"""M6.4-B B2/B3：器械与场景网格（刚性，随节点变换运动）。

空间规范（与 rig.py 一致）：Y-up、米制、角色面朝 +Z、地面 y=0。
杠铃沿 X 轴（横杠方向），杆长 2.2m（教学简化比例，男式奥杆规格）。
"""
from __future__ import annotations

import numpy as np


class MeshBuilder:
    """无蒙皮的刚性网格构建器（多个 box/cylinder/plate 组合成一个 mesh，
    按 mat 参数自动记录材质分组三角区间）。"""

    def __init__(self) -> None:
        self.pos: list[np.ndarray] = []
        self.nrm: list[np.ndarray] = []
        self.tris: list[tuple[int, int, int]] = []
        self.ranges: list[tuple[str, int, int]] = []   # (mat, tri 起, tri 止)

    def _mark(self, mat: str | None) -> None:
        """记录材质分组区间（必须在添加该图元的三角形**之后**调用）。"""
        if not mat:
            return
        if self.ranges and self.ranges[-1][0] == mat:
            self.ranges[-1] = (mat, self.ranges[-1][1], len(self.tris))
        else:
            self.ranges.append((mat, len(self.tris), len(self.tris)))

    def box(self, center, half, axis=(1, 0, 0), angle_deg=0.0, mat=None) -> None:
        self._add_box(center, half, axis, angle_deg)
        self._mark(mat)

    def _add_box(self, center, half, axis=(1, 0, 0), angle_deg=0.0) -> None:
        c, h = np.asarray(center, float), np.asarray(half, float)
        th = np.radians(angle_deg)
        ax = np.asarray(axis, float)
        ax = ax / np.linalg.norm(ax)
        # Rodrigues 旋转
        K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
        R = np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)
        faces = [
            (np.array([1.0, 0, 0]), [(h[0], -h[1], -h[2]), (h[0], h[1], -h[2]),
                                      (h[0], h[1], h[2]), (h[0], -h[1], h[2])]),
            (np.array([-1.0, 0, 0]), [(-h[0], h[1], -h[2]), (-h[0], -h[1], -h[2]),
                                      (-h[0], -h[1], h[2]), (-h[0], h[1], h[2])]),
            (np.array([0, 1.0, 0]), [(-h[0], h[1], -h[2]), (h[0], h[1], -h[2]),
                                     (h[0], h[1], h[2]), (-h[0], h[1], h[2])]),
            (np.array([0, -1.0, 0]), [(h[0], -h[1], -h[2]), (-h[0], -h[1], -h[2]),
                                      (-h[0], -h[1], h[2]), (h[0], -h[1], h[2])]),
            (np.array([0, 0, 1.0]), [(-h[0], -h[1], h[2]), (h[0], -h[1], h[2]),
                                     (h[0], h[1], h[2]), (-h[0], h[1], h[2])]),
            (np.array([0, 0, -1.0]), [(-h[0], h[1], -h[2]), (h[0], h[1], -h[2]),
                                      (h[0], -h[1], -h[2]), (-h[0], -h[1], -h[2])]),
        ]
        for n, quad in faces:
            vs = []
            for q in quad:
                self.pos.append(c + R @ np.asarray(q, float))
                self.nrm.append(R @ n)
                vs.append(len(self.pos) - 1)
            self.tris.append((vs[0], vs[1], vs[2]))
            self.tris.append((vs[0], vs[2], vs[3]))

    def cylinder_x(self, x0: float, x1: float, r: float, seg: int = 16,
                   mat: str | None = None) -> None:
        """沿 X 轴圆柱（两端封盖）。"""
        rings: list[list[int]] = []
        for x in (x0, x1):
            ring: list[int] = []
            for j in range(seg):
                a = 2 * np.pi * j / seg
                self.pos.append(np.array([x, r * np.cos(a), r * np.sin(a)]))
                self.nrm.append(np.array([0.0, np.cos(a), np.sin(a)]))
                ring.append(len(self.pos) - 1)
            rings.append(ring)
        for j in range(seg):
            j2 = (j + 1) % seg
            self.tris.append((rings[0][j], rings[1][j], rings[1][j2]))
            self.tris.append((rings[0][j], rings[1][j2], rings[0][j2]))
        for ring, x, s in ((rings[0], x0, 1.0), (rings[1], x1, -1.0)):
            self.pos.append(np.array([x, 0.0, 0.0]))
            self.nrm.append(np.array([s, 0.0, 0.0]))
            ci = len(self.pos) - 1
            for j in range(seg):
                j2 = (j + 1) % seg
                self.tris.append((ci, ring[j2], ring[j]) if s > 0
                                 else (ci, ring[j], ring[j2]))
        self._mark(mat)

    def plate_x(self, x: float, r: float, thick: float, seg: int = 24,
                mat: str | None = None) -> None:
        """X 处的杠铃片（短圆柱：外圈柱面 + 两侧平盖，法线解析）。"""
        hx = thick / 2
        for j in range(seg):
            a0 = 2 * np.pi * j / seg
            a1 = 2 * np.pi * (j + 1) / seg
            # 外圈柱面四边形
            v = []
            for xx, aa in ((x - hx, a0), (x - hx, a1), (x + hx, a1), (x + hx, a0)):
                self.pos.append(np.array([xx, r * np.cos(aa), r * np.sin(aa)]))
                self.nrm.append(np.array([0.0, np.cos(aa), np.sin(aa)]))
                v.append(len(self.pos) - 1)
            self.tris.append((v[0], v[1], v[2]))
            self.tris.append((v[0], v[2], v[3]))
            # 两侧平盖三角扇
            for s, xx in ((1.0, x + hx), (-1.0, x - hx)):
                self.pos.append(np.array([xx, 0.0, 0.0]))
                self.nrm.append(np.array([s, 0.0, 0.0]))
                ci = len(self.pos) - 1
                for aa in (a0, a1):
                    self.pos.append(np.array([xx, r * np.cos(aa), r * np.sin(aa)]))
                    self.nrm.append(np.array([s, 0.0, 0.0]))
                e0, e1 = len(self.pos) - 2, len(self.pos) - 1
                self.tris.append((ci, e1, e0) if s > 0 else (ci, e0, e1))
        self._mark(mat)

    def build(self) -> dict[str, np.ndarray]:
        out = {
            "position": np.array(self.pos, dtype=np.float32),
            "normal": np.array(self.nrm, dtype=np.float32),
            "indices": np.array(self.tris, dtype=np.uint32),
        }
        if self.ranges:
            out["groups"] = [(m, a, b) for m, a, b in self.ranges if b > a]
        return out


def barbell() -> dict[str, np.ndarray]:
    """奥杆 + 每侧两片（教学简化）：杆 r14mm，套筒 r26mm，大/小片。"""
    b = MeshBuilder()
    b.cylinder_x(-0.82, 0.82, 0.014, mat="barbell_shaft")   # 杆身
    b.cylinder_x(0.82, 1.10, 0.026, mat="barbell_shaft")    # 右套筒
    b.cylinder_x(-1.10, -0.82, 0.026, mat="barbell_shaft")  # 左套筒
    for s in (1, -1):
        b.plate_x(s * 0.88, 0.225, 0.052, mat="plate")      # 大片
        b.plate_x(s * 0.945, 0.155, 0.036, mat="plate")     # 小片
    return b.build()


def dumbbell() -> dict[str, np.ndarray]:
    b = MeshBuilder()
    b.cylinder_x(-0.17, 0.17, 0.013, mat="dumbbell")
    for s in (1, -1):
        b.plate_x(s * 0.115, 0.072, 0.048, mat="dumbbell")
        b.plate_x(s * 0.075, 0.055, 0.03, mat="dumbbell")
    return b.build()


def bench() -> dict[str, np.ndarray]:
    """平凳：垫面顶 y≈0.465，沿 Z 轴（头朝 −Z），教学简化比例。"""
    b = MeshBuilder()
    b.box((0, 0.43, 0), (0.155, 0.035, 0.62), mat="bench_pad")       # 垫
    for z in (-0.5, 0.5):
        b.box((0, 0.20, z * 0.35), (0.05, 0.20, 0.045),
              mat="bench_frame")                                      # 支腿
    b.box((0, 0.025, 0), (0.05, 0.025, 0.72), mat="bench_frame")     # 底架
    return b.build()


def bench_upright() -> dict[str, np.ndarray]:
    """带竖直靠背的训练凳（哑铃肩推坐姿用）：凳体同平凳 + −Z 端立式靠背。"""
    b = MeshBuilder()
    b.box((0, 0.43, 0), (0.155, 0.035, 0.62), mat="bench_pad")
    for z in (-0.5, 0.5):
        b.box((0, 0.20, z * 0.35), (0.05, 0.20, 0.045), mat="bench_frame")
    b.box((0, 0.025, 0), (0.05, 0.025, 0.72), mat="bench_frame")
    # 靠背：约 85° 微后倾，垫面中心 (0, 0.72, -0.60)
    b.box((0, 0.72, -0.60), (0.155, 0.30, 0.035), axis=(1, 0, 0),
          angle_deg=-8, mat="bench_pad")
    b.box((0, 0.46, -0.58), (0.05, 0.24, 0.04), mat="bench_frame")   # 背柱
    return b.build()


def floor() -> dict[str, np.ndarray]:
    """地面薄板（顶面 y=0）。"""
    b = MeshBuilder()
    b.box((0, -0.01, 0), (1.7, 0.01, 1.7), mat="floor")
    return b.build()
