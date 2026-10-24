"""M6.4-B B0.3：公共教学媒体元数据（版本化 manifest，二进制不入 SQLite）。

两层结构：
- assets/teaching_media/manifest.json —— 全局教学媒体资产索引（图片/视频/
  三维模型），每条含 B0.3 全字段（来源/许可证/授权证据/审核状态/sha256）。
- assets/exercise_3d/manifests/<ex_id>.json —— 三维播放描述（B3.2 字段：
  model_path/preview_path/animation_name/duration/loop/supported_views/
  teaching_phases/license/review_status/version），通过 asset_id 回链索引。

发布纪律（B0 验收）：任何未确认授权的素材不得作为公共演示内容发布。
- scope=global 才是公共素材；用户上传媒体只存在于既有 per-user SQLite/
  media 目录体系，绝不进入本 manifest（隔离从结构上保证）。
- 授权判定：source_kind=project_created（本项目自制，授权明确）需
  license+license_evidence；third_party_licensed 必须提供许可证证据且
  review_status=approved 才可发布；user_uploaded 一律不得为 global。
- 完整性：发布前校验文件存在且 sha256 与 manifest 一致，不一致视为
  未授权（损坏/被篡改）素材，不予发布。

动作三维入口只按稳定 exercise_id 关联；不按中文名称拼接路径。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ASSETS_DIR = (Path(__file__).resolve().parent.parent / "assets").resolve()
MEDIA_MANIFEST = ASSETS_DIR / "teaching_media" / "manifest.json"
MANIFESTS_3D_DIR = ASSETS_DIR / "exercise_3d" / "manifests"

MEDIA_TYPES = {"image", "video", "model_3d"}
SOURCE_KINDS = {"project_created", "third_party_licensed", "user_uploaded"}
SCOPES = {"global", "user"}

REQUIRED_ASSET_FIELDS = (
    "asset_id", "exercise_id", "media_type", "source_kind", "file_path",
    "license", "license_evidence", "scope", "review_status", "sha256",
)
REQUIRED_3D_FIELDS = (
    "exercise_id", "asset_id", "model_path", "animation_name", "duration",
    "loop", "supported_views", "teaching_phases", "license", "review_status",
    "version",
)


class MediaManifestError(ValueError):
    """manifest 结构不合法或含未授权条目被拒。"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_media_manifest(path: Path | None = None) -> list[dict]:
    """读取全局媒体索引并做结构校验（不校验文件存在，见 authorized_assets）。"""
    p = path or MEDIA_MANIFEST
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MediaManifestError(f"{p}: JSON 解析失败：{e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("assets"), list):
        raise MediaManifestError(f"{p}: 结构必须为 {{version, assets: []}}")
    seen: set[str] = set()
    for a in data["assets"]:
        missing = [k for k in REQUIRED_ASSET_FIELDS if not a.get(k)]
        if missing:
            raise MediaManifestError(f"{p}: 资产 {a.get('asset_id')!r} 缺字段 {missing}")
        if a["asset_id"] in seen:
            raise MediaManifestError(f"{p}: asset_id 重复 {a['asset_id']!r}")
        seen.add(a["asset_id"])
        if a["media_type"] not in MEDIA_TYPES:
            raise MediaManifestError(f"{p}: {a['asset_id']} media_type 非法")
        if a["source_kind"] not in SOURCE_KINDS:
            raise MediaManifestError(f"{p}: {a['asset_id']} source_kind 非法")
        if a["scope"] not in SCOPES:
            raise MediaManifestError(f"{p}: {a['asset_id']} scope 非法")
        if a["scope"] == "global" and a["source_kind"] == "user_uploaded":
            raise MediaManifestError(
                f"{p}: {a['asset_id']} 用户上传素材不得登记为 global（隔离纪律）")
    return data["assets"]


def authorized(entry: dict) -> bool:
    """发布授权判定（仅结构层；文件完整性另验）。"""
    if entry.get("scope") != "global":
        return False
    kind = entry.get("source_kind")
    if kind == "project_created":
        return bool(entry.get("license") and entry.get("license_evidence"))
    if kind == "third_party_licensed":
        return (bool(entry.get("license") and entry.get("license_evidence"))
                and entry.get("review_status") == "approved")
    return False


def authorized_assets(ex_id: str | None = None,
                      media_type: str | None = None) -> list[dict]:
    """已确认授权且文件完整（存在 + sha256 一致）的公共资产。"""
    out: list[dict] = []
    for a in load_media_manifest():
        if ex_id and a["exercise_id"] != ex_id:
            continue
        if media_type and a["media_type"] != media_type:
            continue
        if not authorized(a):
            continue
        f = ASSETS_DIR / a["file_path"]
        if not f.is_file() or not str(f).startswith(str(ASSETS_DIR)):
            continue
        if _sha256(f) != a["sha256"]:
            continue
        out.append(a)
    return out


def load_3d_descriptor(ex_id: str) -> dict | None:
    """读取并校验某动作的三维播放描述（B3.2 字段）。"""
    from .exercises import library  # 内置动作才有公共三维；自定义动作不关联
    if library.get(ex_id) is None:
        return None
    p = MANIFESTS_3D_DIR / f"{ex_id}.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    missing = [k for k in REQUIRED_3D_FIELDS if not d.get(k)]
    if missing:
        raise MediaManifestError(f"{p}: 三维描述缺字段 {missing}")
    return d


def demo_3d(ex_id: str) -> dict | None:
    """动作详情三维演示入口：资产已授权 + 文件完整才透出。

    返回播放器所需信息（URL 由路由层拼），不含内部路径细节。
    """
    desc = load_3d_descriptor(ex_id)
    if not desc:
        return None
    asset = next((a for a in load_media_manifest()
                  if a["asset_id"] == desc.get("asset_id")), None)
    if not asset or not authorized(asset):
        return None
    model = ASSETS_DIR / asset["file_path"]
    if not model.is_file() or _sha256(model) != asset["sha256"]:
        return None
    preview_url = ""
    if desc.get("preview_path"):
        preview = ASSETS_DIR / desc["preview_path"]
        if preview.is_file() and str(preview).startswith(str(ASSETS_DIR)):
            preview_url = str(desc["preview_path"])
    return {
        "exercise_id": ex_id,
        "asset_id": asset["asset_id"],
        "model_path": asset["file_path"],
        "preview_path": preview_url,
        "animation_name": desc["animation_name"],
        "duration": float(desc["duration"]),
        "loop": bool(desc.get("loop", True)),
        "supported_views": desc["supported_views"],
        "teaching_phases": desc["teaching_phases"],
        "license": asset["license"],
        "review_status": asset["review_status"],
        "content_version": asset.get("content_version"),
        "size_bytes": model.stat().st_size,
    }


def asset_file_for_serving(ex_id: str, name: str) -> Path | None:
    """静态路由用：文件必须在该动作已授权资产/描述清单内才可下发。

    防目录穿越 + 防未授权素材借 URL 直接发布（双保险，与 manifest 校验独立）。
    """
    if not re_name_ok(name):
        return None
    allowed: dict[str, Path] = {}
    for a in authorized_assets(ex_id):
        f = ASSETS_DIR / a["file_path"]
        allowed.setdefault(f.name, f)
        if a.get("poster_path"):
            poster = ASSETS_DIR / a["poster_path"]
            allowed.setdefault(poster.name, poster)
    desc = load_3d_descriptor(ex_id)
    if desc:
        for key in ("model_path", "preview_path"):
            if desc.get(key):
                f = ASSETS_DIR / desc[key]
                if f.is_file():
                    allowed.setdefault(f.name, f)
    f = allowed.get(name)
    if f and f.is_file() and str(f.resolve()).startswith(str(ASSETS_DIR)):
        return f
    return None


def re_name_ok(name: str) -> bool:
    return bool(name) and "/" not in name and "\\" not in name \
        and ".." not in name and all(c.isalnum() or c in "._-" for c in name)
