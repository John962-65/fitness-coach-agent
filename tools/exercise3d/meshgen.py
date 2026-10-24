#!/usr/bin/env python3
"""M6.4-B B2：蒙皮人体网格生成（骨骼驱动 + 关节融合顶点权重）。

生成「绑定姿态」下的分段锥柱/盒子/球体几何，每顶点携带骨骼权重：
- 骨骼中段顶点 100% 归属该骨骼（刚性段）；
- 靠近远端关节的环带向子骨骼过渡（最小 50/50），使膝/肘弯曲平滑——
  这是真实的蒙皮（skinning）行为，而非整体平移冒充动画。
所有几何在绑定姿态生成；姿态变化完全由骨骼动画驱动。
"""
from __future__ import annotations

import numpy as np

from .rig import Rig, BONE_NAMES


class SkinMeshBuilder:
    def __init__(self) -> None:
        self.pos: list[np.ndarray] = []
        self.joints: list[tuple[int, ...]] = []   # 每顶点 ≤4 骨骼索引
        self.weights: list[tuple[float, ...]] = []
        self.tris: list[tuple[int, int, int]] = []
        self._normals: np.ndarray | None = None

    # ---- 基础顶点写入 ----
    def _vert(self, p: np.ndarray, infl: list[tuple[str, float]]) -> None:
        idx = {n: i for i, n in enumerate(BONE_NAMES)}
        js, ws = [], []
        for name, w in infl:
            if w > 1e-4:
                js.append(idx[name])
                ws.append(w)
        total = sum(ws)
        ws = [w / total for w in ws]
        while len(js) < 4:
            js.append(0)
            ws.append(0.0)
        self.pos.append(np.asarray(p, dtype=float))
        self.joints.append(tuple(js[:4]))
        self.weights.append(tuple(ws[:4]))

    def add_tri(self, a: int, b: int, c: int) -> None:
        self.tris.append((a, b, c))

    # ---- 管状段（两关节之间，含远端融合）----
    def tube(self, p0: np.ndarray, p1: np.ndarray, r0: tuple[float, float],
             r1: tuple[float, float], owner: str, child: str | None = None,
             rings: int = 7, radial: int = 12, x_hint: np.ndarray | None = None,
             cap_start: bool = True, cap_end: bool = True) -> None:
        """p0→p1 的锥柱。权重：owner 为主；child 在远端（t≥0.62）线性过渡到
        50/50，形成关节融合带。"""
        d = p1 - p0
        L = np.linalg.norm(d)
        dirv = d / L
        xh = np.asarray(x_hint if x_hint is not None else [1.0, 0, 0], dtype=float)
        e1 = xh - np.dot(xh, dirv) * dirv
        n1 = np.linalg.norm(e1)
        if n1 < 1e-6:
            e1 = np.array([0.0, 1, 0]) - np.dot([0, 1.0, 0], dirv) * dirv
            n1 = np.linalg.norm(e1)
        e1 = e1 / n1
        e2 = np.cross(dirv, e1)

        def blend(t: float) -> list[tuple[str, float]]:
            if child and t >= 0.62:
                k = (t - 0.62) / 0.38  # 0→1
                w_owner = 1.0 - 0.5 * k
                return [(owner, w_owner), (child, 1.0 - w_owner)]
            return [(owner, 1.0)]

        ring_idx: list[list[int]] = []
        for i in range(rings):
            t = i / (rings - 1)
            c = p0 + t * d
            rx = r0[0] + (r1[0] - r0[0]) * t
            rz = r0[1] + (r1[1] - r0[1]) * t
            infl = blend(t)
            cur: list[int] = []
            for j in range(radial):
                a = 2 * np.pi * j / radial
                p = c + rx * np.cos(a) * e1 + rz * np.sin(a) * e2
                self._vert(p, infl)
                cur.append(len(self.pos) - 1)
            ring_idx.append(cur)
        for i in range(rings - 1):
            ra, rb = ring_idx[i], ring_idx[i + 1]
            for j in range(radial):
                j2 = (j + 1) % radial
                self.add_tri(ra[j], rb[j], rb[j2])
                self.add_tri(ra[j], rb[j2], ra[j2])
        if cap_start:
            self._cap(p0, dirv, r0, blend(0.0), e1, e2, radial, start=True)
        if cap_end:
            self._cap(p1, dirv, r1, blend(1.0), e1, e2, radial, start=False)

    def _cap(self, center: np.ndarray, dirv: np.ndarray, r: tuple[float, float],
             infl: list[tuple[str, float]], e1: np.ndarray, e2: np.ndarray,
             radial: int, start: bool) -> None:
        shrink = 0.55
        sign = -1.0 if start else 1.0
        mid_c = center + sign * 0.45 * min(r) * dirv
        apex = center + sign * 1.0 * min(r) * dirv
        ring: list[int] = []
        for j in range(radial):
            a = 2 * np.pi * j / radial
            p = mid_c + shrink * r[0] * np.cos(a) * e1 + shrink * r[1] * np.sin(a) * e2
            self._vert(p, infl)
            ring.append(len(self.pos) - 1)
        self._vert(apex, infl)
        apex_i = len(self.pos) - 1
        for j in range(radial):
            j2 = (j + 1) % radial
            if start:
                self.add_tri(ring[j], apex_i, ring[j2])
            else:
                self.add_tri(ring[j], ring[j2], apex_i)

    # ---- 盒子（硬边：面拆分顶点 + 面法线）----
    def box(self, center: np.ndarray, half: np.ndarray, owner: str,
            child: str | None = None, child_zone: str = "") -> None:
        """轴对齐盒（绑定姿态）。child_zone: 'z+' 时 z>0 一半顶点混 child 40%。"""
        c = np.asarray(center, float)
        h = np.asarray(half, float)

        def infl_for(corner: np.ndarray) -> list[tuple[str, float]]:
            if child and child_zone == "z+" and corner[2] > c[2]:
                return [(owner, 0.6), (child, 0.4)]
            return [(owner, 1.0)]

        faces = [
            ([1, 0, 0], [(h[0], -h[1], -h[2]), (h[0], h[1], -h[2]),
                         (h[0], h[1], h[2]), (h[0], -h[1], h[2])]),
            ([-1, 0, 0], [(-h[0], h[1], -h[2]), (-h[0], -h[1], -h[2]),
                          (-h[0], -h[1], h[2]), (-h[0], h[1], h[2])]),
            ([0, 1, 0], [(-h[0], h[1], -h[2]), (h[0], h[1], -h[2]),
                         (h[0], h[1], h[2]), (-h[0], h[1], h[2])]),
            ([0, -1, 0], [(h[0], -h[1], -h[2]), (-h[0], -h[1], -h[2]),
                          (-h[0], -h[1], h[2]), (h[0], -h[1], h[2])]),
            ([0, 0, 1], [(-h[0], -h[1], h[2]), (h[0], -h[1], h[2]),
                         (h[0], h[1], h[2]), (-h[0], h[1], h[2])]),
            ([0, 0, -1], [(-h[0], h[1], -h[2]), (h[0], h[1], -h[2]),
                          (h[0], -h[1], -h[2]), (-h[0], -h[1], -h[2])]),
        ]
        for normal, quad in faces:
            n = np.asarray(normal, float)
            vs = []
            for q in quad:
                p = c + np.asarray(q, float)
                self._vert(p, infl_for(p))
                vs.append(len(self.pos) - 1)
                self._hard_normal(n)
            self.add_tri(vs[0], vs[1], vs[2])
            self.add_tri(vs[0], vs[2], vs[3])

    def _hard_normal(self, n: np.ndarray) -> None:
        if not hasattr(self, "_hard_list"):
            self._hard_list: dict[int, np.ndarray] = {}
        self._hard_list[len(self.pos) - 1] = np.asarray(n, float)

    # ---- 球 ----
    def sphere(self, center: np.ndarray, r: float, owner: str,
               seg: int = 14) -> None:
        c = np.asarray(center, float)
        rows: list[list[int]] = []
        for i in range(seg + 1):
            phi = np.pi * i / seg
            ring: list[int] = []
            for j in range(seg):
                th = 2 * np.pi * j / seg
                p = c + r * np.array(
                    [np.sin(phi) * np.cos(th), np.cos(phi), np.sin(phi) * np.sin(th)])
                self._vert(p, [(owner, 1.0)])
                ring.append(len(self.pos) - 1)
            rows.append(ring)
        for i in range(seg):
            for j in range(seg):
                j2 = (j + 1) % seg
                if i == 0:
                    self.add_tri(rows[0][j], rows[1][j2], rows[1][j])
                elif i == seg - 1:
                    self.add_tri(rows[i][j], rows[i][j2], rows[i + 1][j])
                else:
                    self.add_tri(rows[i][j], rows[i + 1][j2], rows[i + 1][j])
                    self.add_tri(rows[i][j], rows[i + 1][j2], rows[i][j2])

    # ---- 输出 ----
    def build(self) -> dict[str, np.ndarray]:
        pos = np.array(self.pos, dtype=np.float32)
        jnt = np.array(self.joints, dtype=np.uint16)
        wgt = np.array(self.weights, dtype=np.float32)
        tri = np.array(self.tris, dtype=np.uint32)
        normals = np.zeros_like(pos, dtype=np.float32)
        hard = getattr(self, "_hard_list", {})
        smooth_mask = np.ones(len(pos), dtype=bool)
        for vi in hard:
            smooth_mask[vi] = False
            normals[vi] = hard[vi].astype(np.float32)
        # 面积加权平滑法线（仅平滑部分）
        acc = np.zeros((len(pos), 3), dtype=np.float64)
        p = pos.astype(np.float64)
        for a, b, c in self.tris:
            if smooth_mask[a]:
                n = np.cross(p[b] - p[a], p[c] - p[a])
                acc[a] += n
            if smooth_mask[b]:
                n = np.cross(p[c] - p[b], p[a] - p[b])
                acc[b] += n
            if smooth_mask[c]:
                n = np.cross(p[a] - p[c], p[b] - p[c])
                acc[c] += n
        norms = np.linalg.norm(acc, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        sm = (acc / norms).astype(np.float32)
        for i in range(len(pos)):
            if smooth_mask[i]:
                normals[i] = sm[i]
        return {"position": pos, "normal": normals, "joints": jnt,
                "weights": wgt, "indices": tri}


def build_body(rig: Rig) -> dict[str, np.ndarray]:
    """组装人体（站姿绑定；比例按 rig 常量，身高约 1.78m）。"""
    b = SkinMeshBuilder()
    P = rig.bind_pos

    # 躯干（椭圆截面：rx 侧向 / rz 前后）
    b.tube(np.array([0, 0.90, 0]), np.array([0, 1.14, 0]),
           (0.125, 0.100), (0.135, 0.105), "Hips", "Spine", rings=6)
    b.tube(np.array([0, 1.14, 0]), np.array([0, 1.32, 0]),
           (0.122, 0.100), (0.150, 0.115), "Spine", "Spine1", rings=6)
    b.tube(np.array([0, 1.32, 0]), np.array([0, 1.46, 0]),
           (0.152, 0.118), (0.108, 0.088), "Spine1", None, rings=6)
    b.tube(np.array([0, 1.44, 0]), np.array([0, 1.58, 0]),
           (0.052, 0.052), (0.044, 0.044), "Spine1", "Neck", rings=4)
    b.sphere(np.array([0, 1.675, 0.012]), 0.105, "Head", seg=14)

    for s, sd in (("Left", 1), ("Right", -1)):
        # 锁骨与手臂（绑定 T-pose 沿 ±X）
        b.tube(P[f"{s}Shoulder"], P[f"{s}Arm"],
               (0.048, 0.048), (0.056, 0.056), f"{s}Shoulder",
               x_hint=np.array([0, 1.0, 0]), rings=3, radial=10)
        b.tube(P[f"{s}Arm"], P[f"{s}ForeArm"],
               (0.048, 0.048), (0.040, 0.040), f"{s}Arm", f"{s}ForeArm",
               x_hint=np.array([0, 1.0, 0]))
        b.tube(P[f"{s}ForeArm"], P[f"{s}Hand"],
               (0.038, 0.038), (0.030, 0.030), f"{s}ForeArm", f"{s}Hand",
               x_hint=np.array([0, 1.0, 0]))
        # 手（绑定姿态沿 ±X 的拳形盒）
        hc = (P[f"{s}Hand"] + P[f"{s}HandEnd"]) / 2 + np.array([0.0, -0.005, 0])
        b.box(hc, np.array([0.072, 0.036, 0.040]), f"{s}Hand")
        # 腿
        b.tube(P[f"{s}UpLeg"], P[f"{s}Leg"],
               (0.086, 0.086), (0.062, 0.062), f"{s}UpLeg", f"{s}Leg")
        b.tube(P[f"{s}Leg"], P[f"{s}Foot"],
               (0.056, 0.056), (0.037, 0.037), f"{s}Leg", f"{s}Foot")
        # 脚（脚跟到跖球，全掌贴地）+ 脚趾
        b.box(np.array([sd * 0.11, 0.048, 0.01]),
              np.array([0.048, 0.048, 0.125]), f"{s}Foot")
        b.box(np.array([sd * 0.11, 0.042, 0.185]),
              np.array([0.043, 0.036, 0.055]), f"{s}ToeBase")
    return b.build()
