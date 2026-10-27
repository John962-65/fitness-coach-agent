"""账户删除闭环（RC-FIX-B）。

数据库与文件无法在同一事务里原子提交，因此采用两阶段：
1. 先把用户媒体目录重命名到 media/.deleting/<uid>-<ts>（同文件系统原子移动）；
2. 数据库删除（含无 user_id 的子表：knowledge_chunks / expert_task_events）；
3. 成功提交后删除回收目录、过滤可归属日志、VACUUM；
   若数据库失败，把回收目录移回原位并抛出，不谎报成功。

返回 complete=False 时表示数据库已删除但文件/日志清理仍有残留，调用方不得
显示“全部清理成功”。备份保留期限由部署方政策决定，本应用不自动保留副本。
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from .db import Database


def _move_to_trash(media_root: Path, uid: str) -> tuple[Path | None, int, list[str]]:
    src = media_root / uid
    if not src.exists():
        return None, 0, []
    if src.is_symlink():
        return None, 0, [f"媒体目录是符号链接，拒绝自动删除：{src}"]
    files = sum(1 for p in src.rglob("*") if p.is_file())
    trash_root = media_root / ".deleting"
    trash_root.mkdir(parents=True, exist_ok=True)
    dst = trash_root / f"{uid}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    os.replace(src, dst)
    return dst, files, []


def _filter_jsonl(path: Path, uid: str) -> tuple[int, str | None]:
    """删除 JSONL 中可明确归属该用户的行；无法归属的行保留。"""
    if not path.exists():
        return 0, None
    tmp = path.with_name(path.name + ".deleting-tmp")
    removed = kept = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as src, \
                tmp.open("w", encoding="utf-8") as dst:
            for line in src:
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    dst.write(line)
                    kept += 1
                    continue
                if obj.get("user") == uid or obj.get("user_id") == uid:
                    removed += 1
                else:
                    dst.write(line)
                    kept += 1
        os.replace(tmp, path)
        return removed, None
    except Exception as e:  # noqa: BLE001
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return 0, f"{path.name}: {e}"
    finally:
        if kept == 0 and removed > 0 and not path.exists():
            path.touch()


def delete_account(db: Database, user_id: str) -> dict:
    """完整删除账户。调用前应确认用户存在。"""
    media_root = db.path.parent / "media"
    cleanup_errors: list[str] = []
    outside_media: list[str] = []
    trash, media_files, move_errors = _move_to_trash(media_root, user_id)
    cleanup_errors.extend(move_errors)
    if move_errors:
        raise RuntimeError("媒体目录无法安全移入回收区：" + "；".join(move_errors))

    # 引用路径若不在 media/<uid> 下，不删除，只报告（防任意路径删除）
    for table, col in (("media_assets", "video_path"),
                       ("media_assets", "subtitle_path"),
                       ("exercise_media_links", "cover_path"),
                       ("exercise_media_links", "clip_path"),
                       ("motion_analyses", "video_path")):
        try:
            rows = db.conn.execute(
                f"SELECT {col} AS p FROM {table} WHERE user_id=?", (user_id,)
            ).fetchall()
        except Exception:
            continue
        base = media_root / user_id
        for r in rows:
            p = r["p"]
            if not p:
                continue
            try:
                path = Path(str(p)).resolve()
            except (OSError, ValueError):
                outside_media.append(str(p))
                continue
            if path != base and base not in path.parents:
                outside_media.append(str(p))

    try:
        rows = db.delete_user(user_id)
    except Exception:
        # 数据库失败：恢复媒体目录，保持可用
        if trash and trash.exists():
            try:
                os.replace(trash, media_root / user_id)
            except Exception as e:  # noqa: BLE001
                cleanup_errors.append(f"回滚媒体目录失败：{e}")
        raise

    # 数据库已提交；文件/日志失败只能报告为不完整
    if trash and trash.exists():
        try:
            shutil.rmtree(trash)
        except Exception as e:  # noqa: BLE001
            cleanup_errors.append(f"媒体回收目录删除失败：{trash}：{e}")
    for name in ("unmatched_exercises.jsonl", "knowledge_loads.jsonl"):
        removed, err = _filter_jsonl(db.path.parent / name, user_id)
        if err:
            cleanup_errors.append(err)
    # agent.log 无法可靠归属到单一用户，不能按行删除；在响应中明确说明
    agent_log = db.path.parent / "agent.log"
    if agent_log.exists():
        cleanup_errors.append("agent.log 未按用户过滤（日志行无稳定用户标识），"
                             "请部署方按保留政策轮转/删除")
    try:
        db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.conn.execute("VACUUM")
    except Exception as e:  # noqa: BLE001
        cleanup_errors.append(f"VACUUM/WAL checkpoint 失败：{e}")

    retention_days = int(os.getenv("ACCOUNT_BACKUP_RETENTION_DAYS", "30"))
    complete = not cleanup_errors and not outside_media
    return {
        "deleted": True,
        "complete": complete,
        "user": user_id,
        "rows": rows,
        "media_files_removed": media_files if complete else 0,
        "trash_path": str(trash) if trash and trash.exists() else None,
        "outside_media_not_deleted": outside_media,
        "cleanup_errors": cleanup_errors,
        "backup_retention_days": retention_days,
        "backup_notice": (
            "应用内不保留账户副本；部署方备份（数据库/对象存储/快照）可能按"
            f"政策保留最多 {retention_days} 天，需由运维在期限内清除。"
            if retention_days > 0 else
            "应用内不保留账户副本；部署方备份需立即清除。"),
        "legal_retention": (
            "本应用不保存依法必须保留的医疗记录；如部署方另存审计/账单数据，"
            "按适用法律与隐私政策另行告知。"),
        "note": ("数据库记录与用户媒体目录已删除；如 complete=false，"
                 "请按 cleanup_errors/trash_path 完成残留清理后再宣称彻底删除。"),
    }
