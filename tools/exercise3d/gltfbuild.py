#!/usr/bin/env python3
"""M6.4-B B2：GLB 组装器（手工写入 glTF 2.0 二进制，蒙皮 + 骨骼动画）。

产出结构：
- 节点 0..N-1 = 骨骼层级（真实骨骼树，Hips 为根，含绑定平移）；
- 人体为单一蒙皮网格（POSITION/NORMAL/JOINTS_0/WEIGHTS_0 + skin）；
- 器械/地面为刚性网格节点（杠铃由动画通道驱动平移）；
- 动画 = 每骨骼 rotation 通道 + 根/器械 translation 通道（LINEAR）。

矩阵按 glTF 列主序序列化；POSITION accessor 带必需的 min/max。
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from .rig import Rig, BONES, BONE_NAMES, bind_world_mats, quat_from_mat

FLOAT, USHORT, UINT = 5126, 5123, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
TYPES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

# 统一材质表（与产品暖白/深墨/青柠色系一致的低饱和教学配色）
MATERIALS = [
    {"name": "body", "baseColor": [0.855, 0.800, 0.720], "metallic": 0.02,
     "roughness": 0.82},                                   # 0 人体（暖灰人台）
    {"name": "barbell_shaft", "baseColor": [0.52, 0.55, 0.58],
     "metallic": 0.75, "roughness": 0.35},                 # 1 杆身金属
    {"name": "plate", "baseColor": [0.19, 0.23, 0.21], "metallic": 0.15,
     "roughness": 0.6},                                    # 2 杠铃片
    {"name": "floor", "baseColor": [0.90, 0.89, 0.86], "metallic": 0.0,
     "roughness": 0.95},                                   # 3 地面
    {"name": "bench_pad", "baseColor": [0.22, 0.26, 0.24], "metallic": 0.0,
     "roughness": 0.9},                                    # 4 凳垫
    {"name": "bench_frame", "baseColor": [0.48, 0.51, 0.54],
     "metallic": 0.6, "roughness": 0.4},                   # 5 凳架
    {"name": "dumbbell", "baseColor": [0.24, 0.28, 0.26], "metallic": 0.2,
     "roughness": 0.55},                                   # 6 哑铃
]


class GlbBuilder:
    def __init__(self) -> None:
        self.bin = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []
        self.meshes: list[dict] = []
        self.nodes: list[dict] = []
        self.animations: list[dict] = []
        self._skins: list[dict] = []

    # ---- buffer/accessor ----
    def _view(self, data: bytes, target: int | None) -> int:
        off = (len(self.bin) + 3) // 4 * 4
        self.bin.extend(b"\0" * (off - len(self.bin)))
        self.bin.extend(data)
        view: dict = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        self.views.append(view)
        return len(self.views) - 1

    def _accessor(self, arr: np.ndarray, t: str, comp: int,
                  target: int | None, minmax: bool = False) -> int:
        dtype = {FLOAT: np.float32, USHORT: np.uint16, UINT: np.uint32}[comp]
        a = np.ascontiguousarray(arr, dtype=dtype)
        n = 1 if t == "SCALAR" else TYPES[t]
        if a.ndim > 1 and a.shape[-1] != n:
            a = a.reshape(-1, n)
        view = self._view(a.tobytes(), target)
        acc: dict = {"bufferView": view, "componentType": comp,
                     "count": int(a.shape[0]), "type": t}
        if minmax:
            flat = a.reshape(-1, n).astype(np.float64)
            acc["min"] = [float(x) for x in flat.min(axis=0)]
            acc["max"] = [float(x) for x in flat.max(axis=0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def index_accessor(self, tri: np.ndarray) -> int:
        comp = USHORT if int(tri.max()) < 65536 else UINT
        return self._accessor(tri.reshape(-1), "SCALAR", comp, ELEMENT_ARRAY_BUFFER)

    # ---- mesh ----
    def add_rigid_mesh(self, name: str, mesh: dict[str, np.ndarray],
                       groups: list[tuple[str, int, int]]) -> int:
        """groups: [(材质名, 起始三角形索引, 结束索引)] → 拆 primitive。"""
        prims = []
        for mat_name, t0, t1 in groups:
            tri = mesh["indices"][t0:t1]
            prims.append({
                "attributes": {
                    "POSITION": self._accessor(mesh["position"], "VEC3", FLOAT,
                                               ARRAY_BUFFER, minmax=True),
                    "NORMAL": self._accessor(mesh["normal"], "VEC3", FLOAT,
                                             ARRAY_BUFFER),
                },
                "indices": self.index_accessor(tri),
                "material": next(i for i, m in enumerate(MATERIALS)
                                 if m["name"] == mat_name),
                "mode": 4,
            })
        self.meshes.append({"name": name, "primitives": prims})
        return len(self.meshes) - 1

    def add_skinned_mesh(self, name: str, mesh: dict[str, np.ndarray],
                         joints_nodes: list[int], rig: Rig) -> tuple[int, int]:
        prims = [{
            "attributes": {
                "POSITION": self._accessor(mesh["position"], "VEC3", FLOAT,
                                           ARRAY_BUFFER, minmax=True),
                "NORMAL": self._accessor(mesh["normal"], "VEC3", FLOAT,
                                         ARRAY_BUFFER),
                "JOINTS_0": self._accessor(mesh["joints"], "VEC4", USHORT,
                                           ARRAY_BUFFER),
                "WEIGHTS_0": self._accessor(mesh["weights"], "VEC4", FLOAT,
                                            ARRAY_BUFFER),
            },
            "indices": self.index_accessor(mesh["indices"]),
            "material": 0,
            "mode": 4,
        }]
        self.meshes.append({"name": name, "primitives": prims})
        mesh_idx = len(self.meshes) - 1
        bind = bind_world_mats(rig)
        inv = np.stack([np.linalg.inv(bind[n]) for n in BONE_NAMES])
        # glTF 矩阵为列主序；每关节一行 16 个 float
        col_major = inv.transpose(0, 2, 1).reshape(len(BONE_NAMES), 16)
        ibm = self._accessor(col_major.astype(np.float32), "MAT4", FLOAT,
                             None)
        skin_idx = len(self._skins)
        self._skins.append({"joints": joints_nodes,
                            "inverseBindMatrices": ibm, "skeleton": joints_nodes[0]})
        return mesh_idx, skin_idx

    # ---- nodes ----
    def add_joint_nodes(self, rig: Rig) -> list[int]:
        """骨骼节点：父/子层级 + 绑定平移。返回与 BONE_NAMES 对齐的节点索引。"""
        name_to_node: dict[str, int] = {}
        for name, parent, _off in BONES:
            node: dict = {"name": name}
            off = rig.offsets[name]
            if np.any(off):
                node["translation"] = [round(float(x), 6) for x in off]
            pnode = name_to_node.get(parent or "")
            if pnode is not None:
                node_ref = self.nodes[pnode]
                node_ref.setdefault("children", []).append(len(self.nodes))
            self.nodes.append(node)
            name_to_node[name] = len(self.nodes) - 1
        return [name_to_node[n] for n in BONE_NAMES]

    def add_node(self, name: str, mesh: int | None = None, skin: int | None = None,
                 translation: np.ndarray | None = None,
                 children: list[int] | None = None) -> int:
        node: dict = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if skin is not None:
            node["skin"] = skin
        if translation is not None and np.any(translation):
            node["translation"] = [round(float(x), 6) for x in translation]
        self.nodes.append(node)
        idx = len(self.nodes) - 1
        if children:
            self.nodes[idx]["children"] = children
        return idx

    # ---- animation ----
    def add_animation(self, name: str, times: list[float],
                       rot_channels: dict[int, list[np.ndarray]],
                       trans_channels: dict[int, list[np.ndarray]]) -> None:
        t_arr = np.array(times, dtype=np.float32)
        samplers: list[dict] = []
        channels: list[dict] = []
        for node, rots in rot_channels.items():
            if not any(np.any(r != np.eye(3)) for r in rots):
                continue
            inp = self._accessor(t_arr, "SCALAR", FLOAT, None, minmax=True)
            quats = np.array([quat_from_mat(r) for r in rots], dtype=np.float32)
            out = self._accessor(quats, "VEC4", FLOAT, None)
            samplers.append({"input": inp, "output": out,
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": node, "path": "rotation"}})
        for node, trs in trans_channels.items():
            inp = self._accessor(t_arr, "SCALAR", FLOAT, None, minmax=True)
            arr = np.array(trs, dtype=np.float32)
            out = self._accessor(arr, "VEC3", FLOAT, None)
            samplers.append({"input": inp, "output": out,
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": node, "path": "translation"}})
        self.animations.append({"name": name, "channels": channels,
                                "samplers": samplers})

    # ---- 保存 ----
    def save(self, path: Path, scene_children: list[int]) -> None:
        doc = {
            "asset": {"version": "2.0",
                      "generator": "fitness-coach-agent tools/exercise3d"},
            "scene": 0,
            "scenes": [{"name": "exercise", "nodes": scene_children}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": [
                {"name": m["name"],
                 "pbrMetallicRoughness": {
                     "baseColorFactor": [*m["baseColor"], 1.0],
                     "metallicFactor": m["metallic"],
                     "roughnessFactor": m["roughness"]},
                 "doubleSided": True}
                for m in MATERIALS],
            "bufferViews": self.views,
            "accessors": self.accessors,
            "buffers": [{"byteLength": len(self.bin)}],
        }
        if self._skins:
            doc["skins"] = self._skins
        if self.animations:
            doc["animations"] = self.animations
        js = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
        js_bytes = js.encode("utf-8")
        pad = (4 - len(js_bytes) % 4) % 4
        js_bytes += b" " * pad
        bin_data = bytes(self.bin)
        bin_pad = (4 - len(bin_data) % 4) % 4
        bin_data += b"\0" * bin_pad
        total = 12 + 8 + len(js_bytes) + 8 + len(bin_data)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(js_bytes), 0x4E4F534A))
            f.write(js_bytes)
            f.write(struct.pack("<II", len(bin_data), 0x004E4942))
            f.write(bin_data)
