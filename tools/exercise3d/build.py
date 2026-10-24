#!/usr/bin/env python3
"""M6.4-B B2/B3：三维动作 GLB 导出 CLI。

用法：
    python3 -m tools.exercise3d.build barbell_back_squat [more_ids...]

产出：assets/exercise_3d/exports/<exercise_id>.glb

Blender 在本环境不可用；本包生成脚本即"工程源文件"（等价 .blend 的角色），
修改骨骼/动画请改 rig.py / meshgen.py / motions/*.py 后重新导出。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from . import motions
from .equipment import barbell, bench, bench_upright, dumbbell, floor
from .gltfbuild import GlbBuilder
from .meshgen import build_body
from .rig import Rig, BONE_NAMES

EXPORTS = (Path(__file__).resolve().parent.parent.parent / "assets"
           / "exercise_3d" / "exports")
MESHES = {"barbell": barbell, "dumbbell": dumbbell, "bench": bench,
          "bench_upright": bench_upright}


def export(exercise_id: str) -> Path:
    doc = motions.MOTIONS[exercise_id].build()
    rig = Rig.create()
    g = GlbBuilder()

    joints = g.add_joint_nodes(rig)                  # 节点 0..N-1 = 骨骼树
    bone_node = dict(zip(BONE_NAMES, joints))

    body = build_body(rig)
    body_mesh, skin_idx = g.add_skinned_mesh("human", body, joints, rig)
    body_node = g.add_node("human_mesh", mesh=body_mesh, skin=skin_idx)
    scene_children = [joints[0], body_node]

    times = doc["times"]
    frames = doc["frames"]
    rot_channels: dict[int, list[np.ndarray]] = {}
    trans_channels: dict[int, list[np.ndarray]] = {}

    # 通道用「局部旋转」（世界恒定 ≠ 局部恒定：如足部需补偿胫骨旋转）
    for bone in BONE_NAMES:
        if any(bone in f["local_rots"] for f in frames):
            rot_channels[bone_node[bone]] = [
                f["local_rots"].get(bone, np.eye(3)) for f in frames]
    trans_channels[bone_node["Hips"]] = [np.asarray(f["hips"]) for f in frames]

    for spec in doc.get("equipment", []):
        # spec: "mesh名" 或 {"node": 节点名, "mesh": 网格类型}（如左右哑铃）
        if isinstance(spec, dict):
            key, mesh_name = spec["node"], spec["mesh"]
        else:
            key = mesh_name = spec
        m = MESHES[mesh_name]()
        groups = m.get("groups") or [("body", 0, len(m["indices"]))]
        mi = g.add_rigid_mesh(mesh_name if key == mesh_name else key, m, groups)
        init = np.asarray(frames[0]["equip"][key]["translation"])
        node = g.add_node(key, mesh=mi, translation=init)
        scene_children.append(node)
        trans_channels[node] = [np.asarray(f["equip"][key]["translation"])
                                for f in frames]
        if frames[0]["equip"][key].get("rotation") is not None:
            rot_channels[node] = [np.asarray(f["equip"][key]["rotation"])
                                  for f in frames]

    fl = floor()
    floor_node = g.add_node("floor", mesh=g.add_rigid_mesh(
        "floor", fl, fl.get("groups") or [("floor", 0, len(fl["indices"]))]))
    scene_children.append(floor_node)

    g.add_animation(doc["animation_name"], times, rot_channels, trans_channels)
    out = EXPORTS / f"{exercise_id}.glb"
    g.save(out, scene_children)
    return out


def main() -> None:
    ids = sys.argv[1:]
    unknown = [i for i in ids if i not in motions.MOTIONS]
    if not ids or unknown:
        print(f"用法: python3 -m tools.exercise3d.build <{'|'.join(motions.MOTIONS)}>")
        sys.exit(1)
    for ex_id in ids:
        out = export(ex_id)
        print(f"导出完成：{out}（{out.stat().st_size / 1024:.0f} KB）")


if __name__ == "__main__":
    main()
