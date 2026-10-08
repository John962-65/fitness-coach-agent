"""生成本地私有高频动作审核包；只排序和摘取证据，不自动审核通过。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from coach.claim_review import is_publishable, review_issues
from tools.distill import segment_text_at
from tools.p1_backlog import _template_defaults

# 复用用户已经建立的 P1 排序，不另造一份动作名单。
PILOT_EXERCISES = tuple(eid for eid, _ in _template_defaults()[:12])
TYPE_PRIORITY = {"cue": 0, "error": 1, "self_check": 2, "method": 3, "principle": 4}


def make_packet(root: Path, per_exercise: int = 8) -> dict:
    claims = []
    for name in ("tcy", "ksw", "cs"):
        path = root / "claims" / f"{name}.yaml"
        if path.exists():
            claims.extend(yaml.safe_load(path.read_text()) or [])
    cache = {}

    def item(c):
        # 不根据来源名访问目录之外；不读取 cookies 或用户数据。
        sources = root / "sources" / "transcripts"
        path = (sources / str(c.get("blogger", "")) / f"{c.get('video', '')}.json").resolve()
        excerpt, digest = "", ""
        if path.is_relative_to(sources.resolve()) and path.is_file():
            if path not in cache:
                raw = path.read_bytes()
                cache[path] = (json.loads(raw), hashlib.sha256(raw).hexdigest())
            transcript, digest = cache[path]
            ts = c.get("ts") or []
            if len(ts) == 2:
                excerpt = segment_text_at(transcript.get("segments", []), *ts)[:800]
        return {"id": c["id"], "claim": c.get("claim", ""), "type": c.get("type"),
                "speaker": c.get("speaker") or "待确认", "video": c.get("video"),
                "ts": c.get("ts"), "usable": is_publishable(c),
                "issues": review_issues(c), "excerpt": excerpt,
                "transcript_sha256": digest,
                "source_note": "仅自动摘取原文，需人工对照片段审核；不是专业结论"}

    actions = []
    for eid in PILOT_EXERCISES:
        path = root / "exercises" / f"{eid}.yaml"
        ex = yaml.safe_load(path.read_text()) if path.exists() else {"name": eid}
        candidates = [c for c in claims if c.get("status") != "rejected"
                      and eid in (c.get("exercises") or []) and c.get("type") in TYPE_PRIORITY]
        candidates.sort(key=lambda c: (TYPE_PRIORITY[c["type"]], c["id"]))
        selected = [item(c) for c in candidates[:per_exercise]]
        actions.append({"id": eid, "name": ex["name"], "exercise_status": ex.get("status", "missing"),
                        "candidates": len(candidates), "claims": selected,
                        "ready": ex.get("status") == "approved" and any(c["usable"] for c in selected)})
    methodology = [c for c in claims if c.get("blogger") == "凯圣王"
                   and c.get("status") != "rejected" and c.get("type") in ("principle", "method")
                   and not c.get("exercises")]
    return {"scope": "受控试用：健身房、每周2–4次、无已知医疗禁忌；仍以运行时筛查为准",
            "status": "actions_reviewed_methodology_pending" if all(a["ready"] for a in actions) else "awaiting_human_review",
            "existing_prechecks": sorted(p.name for p in root.glob("precheck*P1*.md")),
            "actions": actions, "methodology_candidates": [item(c) for c in methodology[:12]],
            "missing": {"chenshi_source": not any(c.get("blogger") == "陈石" for c in claims),
                        "requires_human_source_review": True, "requires_human_applicability_review": True,
                        "longitudinal_trial": "未提供2–4周真实使用证据，不标记完成"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "sources" / "review_packet")
    parser.add_argument("--per-exercise", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.per_exercise <= 30:
        parser.error("per-exercise 须在1到30之间")
    report = make_packet(ROOT, args.per_exercise)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "packet.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    rows = ["# 高频动作待审包", "", "本地私有素材，自动整理不等于人工审核。", "",
            "| 动作 | 动作审核 | 候选条目 | 本包可引用条目 |", "|---|---|---:|---:|"]
    for a in report["actions"]:
        rows.append(f"| {a['name']} | {a['exercise_status']} | {a['candidates']} | "
                    f"{sum(c['usable'] for c in a['claims'])} |")
    rows += ["", "逐条原文、时间窗、发言者与审核缺口见 packet.json。",
             "先进行 source 审核，再进行 applicability 审核；不自动批准。",
             "方法论候选同样待双层审核，不是已验证的训练方法。",
             "陈石来源缺失时：提供公开视频URL或含video/blogger/segments的本地文字稿；不得代造。"]
    (args.out / "README.md").write_text("\n".join(rows) + "\n")
    print(f"已生成 {len(report['actions'])} 个动作的私有审核包：{args.out}")
    print("状态：" + report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
