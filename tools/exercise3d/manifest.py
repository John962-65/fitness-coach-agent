#!/usr/bin/env python3
"""M6.4-B：生成/更新教学媒体 manifest（媒体索引 + 三维播放描述）。

- assets/teaching_media/manifest.json：全局教学媒体索引（B0.3 字段）
- assets/exercise_3d/manifests/<ex_id>.json：三维播放描述（B3.2 字段）

来源与授权如实登记：本项目自制（project_created）素材 license 为项目内
使用；review_status 记录为 draft（AI 生成，未人工复核——不伪造审核结果）。
用法：python3 -m tools.exercise3d.manifest <exercise_id> ...
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from . import motions

ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS = ROOT / "assets"
MEDIA_MANIFEST = ASSETS / "teaching_media" / "manifest.json"
MANIFESTS_3D = ASSETS / "exercise_3d" / "manifests"

# 动画的人工审核状态：AI 生成的教学示例，尚未人工复核
ASSET_REVIEW_STATUS = "draft"
ASSET_LICENSE = "project-internal"
ASSET_LICENSE_EVIDENCE = (
    "本项目 M6.4-B 自动生成（tools/exercise3d/ 生成脚本，无第三方素材），"
    "授权随仓库所有者；发布到仓库外前需项目所有者确认")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def upsert(exercise_id: str) -> dict:
    doc = motions.MOTIONS[exercise_id].build()
    glb = ASSETS / "exercise_3d" / "exports" / f"{exercise_id}.glb"
    if not glb.is_file():
        raise SystemExit(f"缺少导出文件：{glb}（先运行 tools.exercise3d.build）")
    asset_id = f"3d_{exercise_id}_v1"
    preview = ASSETS / "exercise_3d" / "exports" / f"preview_{exercise_id}.png"
    entry = {
        "asset_id": asset_id,
        "exercise_id": exercise_id,
        "media_type": "model_3d",
        "source_kind": "project_created",
        "file_path": f"exercise_3d/exports/{exercise_id}.glb",
        "poster_path": (f"exercise_3d/exports/preview_{exercise_id}.png"
                        if preview.is_file() else None),
        "source_name": "fitness-coach-agent tools/exercise3d",
        "source_url": None,
        "license": ASSET_LICENSE,
        "license_evidence": ASSET_LICENSE_EVIDENCE,
        "redistribution_allowed": False,
        "scope": "global",
        "review_status": ASSET_REVIEW_STATUS,
        "content_version": 1,
        "sha256": sha256(glb),
        "size_bytes": glb.stat().st_size,
        "created_at": str(date.today()),
    }
    data = {"version": 1, "assets": []}
    if MEDIA_MANIFEST.is_file():
        data = json.loads(MEDIA_MANIFEST.read_text(encoding="utf-8"))
    data["assets"] = [a for a in data["assets"] if a["asset_id"] != asset_id]
    data["assets"].append(entry)
    MEDIA_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MEDIA_MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    desc = {
        "exercise_id": exercise_id,
        "asset_id": asset_id,
        "model_path": entry["file_path"],
        "preview_path": entry["poster_path"],
        "animation_name": doc["animation_name"],
        "duration": doc["duration"],
        "loop": bool(doc.get("loop", True)),
        "supported_views": ["front", "side", "back"],
        "teaching_phases": [
            {"key": p["key"], "label": p["label"],
             "t": [p["t"][0], p["t"][1]]} for p in doc["phases"]],
        "license": ASSET_LICENSE,
        "review_status": ASSET_REVIEW_STATUS,
        "version": 1,
        "note": doc.get("note", ""),
    }
    MANIFESTS_3D.mkdir(parents=True, exist_ok=True)
    out = MANIFESTS_3D / f"{exercise_id}.json"
    out.write_text(json.dumps(desc, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return {"asset": entry, "manifest": out}


def main() -> None:
    ids = sys.argv[1:]
    unknown = [i for i in ids if i not in motions.MOTIONS]
    if not ids or unknown:
        print(f"用法: python3 -m tools.exercise3d.manifest <{'|'.join(motions.MOTIONS)}>")
        sys.exit(1)
    for ex_id in ids:
        r = upsert(ex_id)
        print(f"{ex_id}: asset={r['asset']['asset_id']} "
              f"sha256={r['asset']['sha256'][:12]}… → {r['manifest'].name}")


if __name__ == "__main__":
    main()
