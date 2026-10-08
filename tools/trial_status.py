"""汇总内容/真实验收/试用证据；不读取用户数据库，不把草稿或模拟结果当成通过。"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from coach.claim_review import is_publishable
from tools.p1_backlog import _template_defaults


def build_status(root: Path, acceptance: dict | None = None, trial: dict | None = None) -> dict:
    claims = []
    for name in ("ksw", "tcy", "cs"):
        path = root / "claims" / f"{name}.yaml"
        if path.exists():
            claims += yaml.safe_load(path.read_text()) or []
    usable = [c for c in claims if is_publishable(c)]
    exercises = [yaml.safe_load(p.read_text()) for p in (root / "exercises").glob("*.yaml")]
    days = set()
    for entry in (trial or {}).get("entries", []):
        try:
            day = date.fromisoformat(entry["date"])
            if day <= date.today() and entry.get("expected") and entry.get("actual"):
                days.add(day)
        except (KeyError, TypeError, ValueError):
            continue
    span = (max(days) - min(days)).days + 1 if days else 0
    return {
        "content": {"total_claims": len(claims), "usable_after_two_reviews": len(usable),
                    "by_blogger": dict(Counter(c.get("blogger") for c in usable)),
                    "missing_chenshi_source": not any(c.get("blogger") == "陈石" for c in claims),
                    "exercise_status": dict(Counter(e.get("status", "missing") for e in exercises)),
                    "pilot_exercises": [eid for eid, _ in _template_defaults()[:12]],
                    "note": "有素材、原文预核、双层签核、运行时挂载是不同阶段"},
        "acceptance": ({"mode": acceptance.get("mode"), "status": acceptance.get("status"),
                        "version": acceptance.get("version"), "summary": acceptance.get("summary"),
                        "budget": acceptance.get("budget")}
                       if acceptance else {"status": "not_provided"}),
        "trial": {"recorded_days": len(days), "span_days": span,
                  "status": "awaiting_human_evaluation" if len(days) >= 14 and span >= 14 else "insufficient_longitudinal_evidence",
                  "note": "记录数量不证明效果；需要真人核对可执行性、记录准确性和调整合理性"},
        "video": {"status": "awaiting_labeled_real_video_validation",
                  "note": "合成关键点测试和单次真机冒烟不是实际准确率"},
        "overall": "not_fully_accepted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-report", type=Path)
    parser.add_argument("--trial-file", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    acceptance = json.loads(args.acceptance_report.read_text()) if args.acceptance_report else None
    trial = json.loads(args.trial_file.read_text()) if args.trial_file else None
    text = json.dumps(build_status(ROOT, acceptance, trial), ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
