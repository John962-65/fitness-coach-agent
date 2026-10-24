#!/usr/bin/env python3
"""M6.4-B B0.1：动作教学覆盖审计 —— 生成 docs/m6.4b-teaching-coverage.md。

盘点口径（明确「关联了教学文档 ≠ 已有完整教学」）：
- teaching_docs  : knowledge_refs 是否解析到存在的 knowledge/*.md（原文层）；
- setup/execution/common_errors：结构化教学 teaching/<id>.yaml 各节是否有内容
  （展示层），并给出各节状态与整体完整性（incomplete/draft/reviewed/approved）；
- source         : 教学信息来源（knowledge 文档 frontmatter source + 结构化
  教学文件的 sources）；
- media          : 公共教学媒体（assets/teaching_media/manifest.json 中已授权
  条目；用户上传媒体是 per-user 数据，不在全局盘点内）；
- model_3d       : 三维模型可用性（assets/exercise_3d/manifests/<id>.json 且
  资产已授权 + sha256 一致）；
- review_status  : 教学内容审核状态（与动作基础属性 status 相互独立）。

用法：python3 tools/teaching_audit.py [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coach import teaching_content, teaching_media  # noqa: E402
from coach.exercises import library  # noqa: E402
from coach.exercise_service import KNOWLEDGE_DIR, teaching_for  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs" / "m6.4b-teaching-coverage.md"


def audit() -> list[dict]:
    structured = teaching_content.load_all()
    media_by_ex: dict[str, list[dict]] = {}
    for a in teaching_media.authorized_assets():
        media_by_ex.setdefault(a["exercise_id"], []).append(a)
    rows = []
    for ex in library.all():
        ex_id = ex["id"]
        docs = teaching_for(ex_id)
        doc_paths = [d["path"] for d in docs]
        broken_refs = [r for r in (ex.get("knowledge_refs") or [])
                       if not (KNOWLEDGE_DIR / r).is_file()]
        st = structured.get(ex_id)
        secs = (st or {}).get("sections", {})
        row = {
            "exercise_id": ex_id,
            "name": ex["name"],
            "teaching_docs": doc_paths,
            "broken_knowledge_refs": broken_refs,
            "setup": bool(secs.get("setup", {}).get("items")),
            "execution": bool(secs.get("execution", {}).get("items")),
            "common_errors": bool(secs.get("common_errors", {}).get("items")),
            "section_statuses": {k: v.get("status") for k, v in secs.items()},
            "completeness": teaching_content.completeness(st),
            "source": sorted({s for d in docs for s in d["source"]}),
            "media": [a["asset_id"] for a in media_by_ex.get(ex_id, [])],
            "model_3d": bool(teaching_media.demo_3d(ex_id)),
            "review_status": (st or {}).get("review_status", "incomplete"),
        }
        rows.append(row)
    return rows


def render_md(rows: list[dict]) -> str:
    total = len(rows)
    comp = Counter(r["completeness"] for r in rows)
    docs_cov = sum(1 for r in rows if r["teaching_docs"])
    structured_cov = sum(1 for r in rows if r["setup"] and r["execution"]
                         and r["common_errors"])
    lines = [
        "# M6.4-B 动作教学覆盖报告（B0.1 审计）",
        "",
        f"生成时间：2026-10-25 · 动作总数：{total}（内置 exercises/*.yaml）",
        "",
        "## 总览",
        "",
        f"- 关联教学文档（knowledge_refs 解析成功）：{docs_cov}/{total}",
        f"- 结构化教学齐备（准备+执行+常见错误有内容）：{structured_cov}/{total}",
        f"- 完整性分布：incomplete {comp['incomplete']} · draft "
        f"{comp['draft']} · reviewed {comp['reviewed']} · approved {comp['approved']}",
        f"- 公共三维演示可用：{sum(1 for r in rows if r['model_3d'])}/{total}",
        f"- 公共教学媒体（已授权）资产数："
        f"{sum(len(r['media']) for r in rows)}",
        "",
        "> 口径提醒：**「关联了一篇教学文档」不等于「已有完整教学」**。结构化",
        "> 六节（准备/执行/常见错误/注意事项/适用条件/来源）齐备才算完整层级；",
        "> 呼吸节允许标 incomplete（无可靠依据时不录入）。教学内容审核状态与",
        "> 动作基础属性 status（approved）相互独立，互不继承。",
        "",
        "## 明细",
        "",
        "| 动作 ID | 名称 | 教学文档 | 准备 | 执行 | 常见错误 | 完整性 | 媒体 | 3D | 教学审核 | 来源 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        doc = "✓" if r["teaching_docs"] else "✗"
        if r["broken_knowledge_refs"]:
            doc += "⚠️断链"
        lines.append(
            f"| {r['exercise_id']} | {r['name']} | {doc} | "
            f"{'✓' if r['setup'] else '✗'} | {'✓' if r['execution'] else '✗'} | "
            f"{'✓' if r['common_errors'] else '✗'} | {r['completeness']} | "
            f"{len(r['media'])} | {'✓' if r['model_3d'] else '✗'} | "
            f"{r['review_status']} | {'、'.join(r['source']) or '—'} |")
    lines += [
        "",
        "## 媒体与三维资源",
        "",
        "- 公共教学媒体索引：`assets/teaching_media/manifest.json`（B0.3 字段：",
        "  asset_id/exercise_id/media_type/source_kind/file_path/license/",
        "  license_evidence/scope/review_status/content_version/sha256 等）。",
        "- 三维播放描述：`assets/exercise_3d/manifests/<exercise_id>.json`（B3.2 字段）。",
        "- 用户上传视频/封面：仅存于 per-user SQLite（media_assets /",
        "  exercise_media_links）与 data/media/<uid>/ 目录，**不在全局清单**，",
        "  公共演示与个人媒体隔离（详见 docs/m6.4b-exercise-visualization.md）。",
        "",
        "## 缺口（如实记录，不用未授权素材填充）",
        "",
        "- 公共视频演示：0。仓库无已确认授权的第三方演示视频；项目尚未自制。",
        "  视频演示入口仅在用户自己导入并关联后出现（既有 exercise_media_links）。",
        "- 结构化教学：首批 5 动作（barbell_back_squat / barbell_bench_press /",
        "  deadlift / barbell_row / dumbbell_shoulder_press）为 draft（AI 依据",
        "  仓库 knowledge/ 整理，未人工复核）；其余 65 动作无结构化教学文件。",
        "- deadlift 的传统硬拉起始位细节：知识来源以变式总则+RDL 为主，",
        "  站距/握法等细节待补可靠来源（teaching 文件内已标注）。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="同时输出 JSON 到指定路径")
    args = ap.parse_args()
    rows = audit()
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_md(rows), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    comp = Counter(r["completeness"] for r in rows)
    print(f"审计完成：{len(rows)} 动作 → {OUT_MD}")
    print(f"完整性：{dict(comp)}；3D 可用：{sum(1 for r in rows if r['model_3d'])}")


if __name__ == "__main__":
    main()
