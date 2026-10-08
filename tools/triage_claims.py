"""待审素材体检（任务书 §10/§12）：把 draft 池拆成性质不同的真实队列。

人工审核单位是核心卡，不是逐条 claims。本工具只做统计与分流，不修改任何条目、
不批准任何内容，用来回答"待审素材到底欠了什么"。

用法：
  python3 tools/triage_claims.py
  python3 tools/triage_claims.py --out TRIAGE.md --json sources/maintenance/triage.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coach.cards import approved_cards, load_quarantined  # noqa: E402
from coach.claim_review import (  # noqa: E402
    is_publishable, review_issues, source_issues)

CLAIMS = ROOT / "claims"
MAINT = ROOT / "sources" / "maintenance"

SPEAKER_UNRESOLVED = ("待确认", "未知", "不确定", "语境归因")

# 分流优先级：靠前的桶先认领条目，保证互斥且穷尽
BUCKETS = (
    ("card_bound", "已被已批核心卡引用（受指纹保护，改动即触发增量复审）",
     "已人工签核（签在卡片上）"),
    ("quarantined", "高风险隔离：伤病、剂量、化验阈值等",
     "不占普通卡名额，交合适专业人员或暂不上线"),
    ("in_conflict", "已登记的观点冲突", "等裁定，不按新旧自动放行"),
    ("flagged", "反幻觉预检 FLAGGED", "待对照原文/画面处置"),
    ("speaker_unresolved", "发言者未确认（语境归因不等于画面确认）",
     "待归因，未确认前不可引用"),
    ("applicability_unknown", "适用条件三项全空",
     "待显式标未知或补条件，不得默认普适"),
    ("duplicate_window", "同视频时间窗重叠", "待合并，不重复消耗人工"),
    ("pool", "素材池：可检索、可保留来源关系", "不上线，非人工待办"),
)


def load_claims() -> list[dict]:
    claims: list[dict] = []
    for path in sorted(CLAIMS.glob("*.yaml")):
        if path.stem == "conflicts":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            claims += [c for c in data if c.get("status") != "rejected"]
    return claims


def bound_claim_ids() -> set[str]:
    ids: set[str] = set()
    for card in approved_cards().values():
        for binding in card.get("bindings") or []:
            ids.add(str(binding.get("claim_id")))
    return ids


def conflict_claim_ids() -> set[str]:
    path = MAINT / "conflicts.json"
    if not path.exists():
        return set()
    records = json.loads(path.read_text(encoding="utf-8")).get("records") or []
    return {str(cid) for record in records for cid in record.get("related_claims") or []}


def quarantined_ids() -> set[str]:
    return {str(entry.get("id")) for entry in load_quarantined() if entry.get("id")}


def applicability_empty(claim: dict) -> bool:
    applies = claim.get("applies_to") or {}
    return not any(applies.get(key) for key in ("level", "goal", "condition"))


def speaker_unresolved(claim: dict) -> bool:
    speaker = str(claim.get("speaker") or "").strip()
    return not speaker or any(marker in speaker for marker in SPEAKER_UNRESOLVED)


def duplicate_ids(claims: list[dict]) -> set[str]:
    """同一视频内时间窗重叠的条目：后出现者作为合并候选。"""
    by_video: dict[str, list[tuple[float, float, str]]] = {}
    for claim in claims:
        window = claim.get("ts")
        if isinstance(window, list) and len(window) == 2:
            by_video.setdefault(str(claim.get("video")), []).append(
                (float(window[0]), float(window[1]), str(claim.get("id"))))
    dupes: set[str] = set()
    for windows in by_video.values():
        max_end, first = -1.0, True
        for start, stop, cid in sorted(windows):
            if not first and start < max_end:
                dupes.add(cid)
            first = False
            max_end = max(max_end, stop)
    return dupes


def bucket_of(claim: dict, bound: set[str], quarantined: set[str],
              conflicts: set[str], dupes: set[str]) -> str:
    cid = str(claim.get("id"))
    if cid in bound:
        return "card_bound"
    if cid in quarantined:
        return "quarantined"
    if cid in conflicts:
        return "in_conflict"
    if claim.get("anti_hallucination") == "FLAGGED":
        return "flagged"
    if speaker_unresolved(claim):
        return "speaker_unresolved"
    if applicability_empty(claim):
        return "applicability_unknown"
    if cid in dupes:
        return "duplicate_window"
    return "pool"


def triage(claims: list[dict]) -> dict:
    bound = bound_claim_ids()
    quarantined = quarantined_ids()
    conflicts = conflict_claim_ids() - quarantined
    dupes = duplicate_ids(claims)
    buckets: dict[str, list[dict]] = {name: [] for name, _, _ in BUCKETS}
    for claim in claims:
        buckets[bucket_of(claim, bound, quarantined, conflicts, dupes)].append(claim)
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": len(claims),
        "publishable": sum(1 for c in claims if is_publishable(c)),
        "quarantined_ids": len(quarantined),
        "bound_ids": len(bound),
        "buckets": {
            name: {
                "label": label,
                "disposition": disposition,
                "count": len(buckets[name]),
                "sample": [str(c.get("id")) for c in buckets[name][:5]],
            }
            for name, label, disposition in BUCKETS
        },
        "defect_signals": {
            "source_ready_pending_sign": sum(
                1 for c in claims if not source_issues(c)),
            "missing_double_sign": sum(1 for c in claims if any(
                "审核未完成" in issue for issue in review_issues(c))),
            "stale_sign": sum(1 for c in claims if any(
                "审核已因内容变化失效" in issue for issue in review_issues(c))),
            "applicability_empty": sum(1 for c in claims if applicability_empty(c)),
            "speaker_unresolved": sum(1 for c in claims if speaker_unresolved(c)),
            "flagged": sum(1 for c in claims
                           if c.get("anti_hallucination") == "FLAGGED"),
            "duplicate_window": len(dupes),
            "cites_research": sum(1 for c in claims
                                  if c.get("evidence") == "cites_research"),
            "consensus_label": sum(1 for c in claims
                                   if c.get("evidence") == "consensus"),
        },
        "type_by_bucket": {
            name: dict(Counter(str(c.get("type")) for c in buckets[name]))
            for name, _, _ in BUCKETS if buckets[name]
        },
    }


def render(report: dict) -> str:
    lines = [
        "# 待审素材体检",
        "",
        f"> 生成：{report['generated_at']}　条目单位：claim（不是卡片）　"
        f"本工具只做分流统计，不修改条目、不批准内容。",
        "",
        f"素材池 {report['total']} 条，满足双层签核可直接引用的 {report['publishable']} 条；"
        f"被已批核心卡实际引用的 {report['bound_ids']} 条——人工判断真实发生在这里，"
        "不在其余条目上（任务书 §12.1、§12.7）。",
        "",
        "| 分流 | 条数 | 处置 | 含义 |",
        "|---|---:|---|---|",
    ]
    for name, label, _ in BUCKETS:
        info = report["buckets"][name]
        lines.append(f"| {name} | {info['count']} | {info['disposition']} | {label} |")
    lines += ["", "## 缺陷信号（同一条目可命中多项，与上表重叠）", "",
              "| 信号 | 条数 |", "|---|---:|"]
    lines += [f"| {key} | {value} |"
              for key, value in report["defect_signals"].items()]
    lines += ["", "## 各桶类型构成", ""]
    for name, counts in report["type_by_bucket"].items():
        detail = "、".join(f"{k} {v}" for k, v in sorted(
            counts.items(), key=lambda kv: -kv[1]))
        lines.append(f"- {name}：{detail}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    report = triage(load_claims())
    text = render(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
