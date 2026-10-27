"""Summarize an RC-1 run for human review (no secrets recorded)."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def _latest() -> Path:
    files = sorted(Path("docs/rc1-evidence").glob("rc1-2026*.json"))
    return files[-1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None)
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    path = Path(args.run) if args.run else _latest()
    run = json.loads(path.read_text())
    results = run["results"]
    print(f"run={path}")
    print(f"model={run.get('model')} cases={run.get('cases_total')} "
          f"records={len(results)} repeat_high={run.get('repeat_high')}")
    print("status:", dict(Counter(r.get("status") for r in results)))
    print("json_ok:", dict(Counter(r.get("json_ok") for r in results)))

    by_case = defaultdict(list)
    for r in results:
        by_case[r["case_id"]].append(r)

    print("\n## Cases with potential auto-flags / missing citations")
    for cid, rows in by_case.items():
        issues = []
        for r in rows:
            ac = r.get("auto_check") or {}
            if ac.get("required_missing"):
                issues.append(f"missing={ac['required_missing']}")
            if ac.get("unknown_citations"):
                issues.append(f"unknown={ac['unknown_citations']}")
            if ac.get("forbidden_hits"):
                issues.append(f"forbidden={[h['match'] for h in ac['forbidden_hits']]}")
            if r.get("status") != "RAN":
                issues.append(f"status={r.get('status')}")
        if issues:
            print(f"- {cid}: {'; '.join(sorted(set(issues)))}")

    print("\n## Per-case compact output (first run)")
    for cid, rows in by_case.items():
        r = rows[0]
        p = r.get("parsed") or {}
        print(f"\n### {cid} [{r.get('risk')}] {r.get('status')} "
              f"json={r.get('json_ok')} repeats={len(rows)}")
        if not p:
            print((r.get("raw_response") or r.get("error") or "")[:400].replace("\n", " "))
            continue
        print("problem:", str(p.get("problem"))[:220].replace("\n", " "))
        opts = p.get("options") or []
        for o in opts[:4]:
            if isinstance(o, dict):
                print("  option:", str(o.get("title"))[:90],
                      "| citations:", o.get("citations"))
        print("  safety:", p.get("safety"),
              "| safety_gate:", str(p.get("safety_gate"))[:120])
        print("  disagreements:", len(p.get("disagreements") or []),
              "| conditions:", len(p.get("conditions") or []),
              "| risks:", len(p.get("risks") or []))

    print("\n## Repeat variability (high risk)")
    for cid, rows in by_case.items():
        if len(rows) < 2:
            continue
        problems = {str((r.get("parsed") or {}).get("problem"))[:160] for r in rows}
        gates = {str((r.get("parsed") or {}).get("safety_gate"))[:80] for r in rows}
        print(f"- {cid}: distinct_problem={len(problems)} distinct_safety_gate={len(gates)}")

    if args.full:
        print("\n## Full first-run parsed JSON")
        for cid, rows in by_case.items():
            print(f"\n### {cid}")
            print(json.dumps(rows[0].get("parsed"), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
