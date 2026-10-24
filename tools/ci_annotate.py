#!/usr/bin/env python3
"""CI 失败诊断：把 pytest 结果解析成 Job Summary（无需登录即可在 run 页面读取）。

用法：pytest -q --junitxml=pytest-results.xml 2>&1 | tee pytest.log 之后执行；
GITHUB_STEP_SUMMARY 未设置时写本地 ci-summary.md（便于本地演练）。
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

XML = Path("pytest-results.xml")
LOG = Path("pytest.log")


def main() -> int:
    lines: list[str] = []
    if XML.exists():
        root = ET.parse(XML).getroot()
        cases = list(root.iter("testcase"))
        bad: list[tuple[str, str, str]] = []
        for tc in cases:
            for kind in ("failure", "error"):
                for f in tc.iter(kind):
                    msg = (f.get("message") or "").splitlines()[0][:300] if f.get("message") else ""
                    bad.append((f"{tc.get('classname')}.{tc.get('name')}", kind, msg))
        lines.append(f"**用例统计**：共 {len(cases)}，失败/错误 {len(bad)}")
        for name, kind, msg in bad[:30]:
            lines.append(f"- ❌ `{name}` ({kind}) {msg}")
            # 同步输出 GitHub Actions 注解（run 摘要页可见，无需登录）
            print(f"::error title={kind}:{name}::{msg}", file=sys.stderr)
    if LOG.exists():
        lines += ["", "<details><summary>pytest.log 末尾</summary>", "", "```text",
                  LOG.read_text(errors="replace")[-6000:], "```", "</details>"]
    summary = Path(os.environ.get("GITHUB_STEP_SUMMARY", "ci-summary.md"))
    with summary.open("a", encoding="utf-8") as fh:
        fh.write("## 后端测试诊断\n\n" + "\n".join(lines) + "\n")
    print(f"wrote diagnostics to {summary} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
