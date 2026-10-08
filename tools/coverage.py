"""动作教学覆盖率表（设计书 21.4）：哪些动作还没有博主来源 → 下一步看哪些视频的清单

用法：
  python3 tools/coverage.py                 # 打印表格
  python3 tools/coverage.py --out sources/coverage.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from coach.claim_review import is_publishable
from coach.claims import COACHING_FIELDS

CLAIMS = ROOT / "claims"
EXERCISES = ROOT / "exercises"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    claims: list[dict] = []
    for f in sorted(CLAIMS.glob("*.yaml")):
        if f.stem == "conflicts":
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        if isinstance(data, list):
            claims += [c for c in data if c.get("status") != "rejected"]

    per_ex: dict[str, dict] = {}
    for c in claims:
        for ex in c.get("exercises") or []:
            d = per_ex.setdefault(ex, {"approved": 0, "draft": 0, "types": set()})
            status = "approved" if is_publishable(c) else "draft"
            d[status] += 1
            d["types"].add(c["type"])

    lines = ["| 动作 | 一手条目（approved/draft） | 类型 | 状态 |",
             "|---|---|---|---|"]
    missing = []
    for path in sorted(EXERCISES.glob("*.yaml")):
        ex = yaml.safe_load(path.read_text(encoding="utf-8"))
        eid = ex["id"]
        d = per_ex.get(eid)
        cue_sources = list(ex.get("cues") or [])
        if d and (d["approved"] or d["draft"]):
            kinds = "、".join(sorted(d["types"]))
            refs = {r for field in COACHING_FIELDS for r in ex.get(field, [])}
            linked = any(is_publishable(c) and c["id"] in refs
                         and eid in (c.get("exercises") or []) for c in claims)
            state = ("✅ 已审核并挂载" if linked else
                     "🔶 已审核但未挂载" if d["approved"] else "⏳ 有草稿，待双层审核")
            if ex.get("status") != "approved":
                state += "；动作属性待审"
            lines.append(f"| {ex['name']}（{eid}） | {d['approved']}/{d['draft']} "
                         f"| {kinds} | {state} |")
        elif cue_sources:
            lines.append(f"| {ex['name']}（{eid}） | - | - | 🔶 库内挂了条目 "
                         f"({', '.join(cue_sources)}) |")
        else:
            lines.append(f"| {ex['name']}（{eid}） | 0 | - | ❌ 无博主来源 → 找视频 |")
            missing.append(f"{ex['name']}（{eid}）")

    report = "\n".join(lines) + f"\n\n待补博主来源的动作 {len(missing)} 个：" \
        + "、".join(missing)
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"\n已存 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
