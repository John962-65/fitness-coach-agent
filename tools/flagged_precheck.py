"""FLAGGED 反幻觉标记条目预核材料导出（设计书 24.1 配套）

> 审核包里最耗时的是 🚩 条目：每条都要跳回原视频核对。本工具把
> P1 范围内（模板动作 × cue/method/error/self_check）的 FLAGGED claims
> 连同其 transcript 原文窗口一并导出，供逐条比对。
> 判断仍由人（或 AI 辅助 + 人确认）完成，本工具只负责取料。

用法：
  python3 tools/flagged_precheck.py                      # 打印
  python3 tools/flagged_precheck.py --out flagged_precheck_material.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.p1_backlog import P1_TYPES, _load_claims, _template_defaults  # noqa: E402

TRANSCRIPTS = ROOT / "sources" / "transcripts"
# 原文窗口：claim 时间戳前后各扩 N 秒，防止蒸馏时切句过紧
WINDOW_PAD = 15.0


def _git_short() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _transcript_window(blogger: str, video: str, ts: list) -> tuple[str, str]:
    """取 claim 时间戳附近的 transcript 原文；返回 (视频标题, 原文窗口文本)"""
    f = TRANSCRIPTS / blogger / f"{video}.json"
    if not f.exists():
        return "", "（transcript 缺失）"
    d = json.loads(f.read_text(encoding="utf-8"))
    lo = (ts[0] if ts else 0) - WINDOW_PAD
    hi = (ts[-1] if ts else 0) + WINDOW_PAD
    text = "".join(s["text"] for s in d.get("segments", [])
                   if s["end"] >= lo and s["start"] <= hi)
    return d.get("title", ""), text or "（该时间窗口无字幕）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    claims = _load_claims()
    defaults = {ex_id for ex_id, _ in _template_defaults()}
    targets = [c for c in claims
               if c.get("anti_hallucination") == "FLAGGED"
               and c.get("type") in P1_TYPES
               and defaults & set(c.get("exercises") or [])]

    lines: list[str] = []
    lines.append("# FLAGGED 预核材料（claims vs transcript 原文）")
    lines.append("")
    lines.append(f"> 生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}｜基线 commit：`{_git_short()}`")
    lines.append(f"> 范围：模板动作 × P1 类型 × anti_hallucination=FLAGGED，共 {len(targets)} 条")
    lines.append(f"> 原文窗口：claim 时间戳前后各 {WINDOW_PAD:.0f}s")
    lines.append("")

    for i, c in enumerate(targets, 1):
        ts = c.get("ts") or []
        title, original = _transcript_window(c.get("blogger", ""), c.get("video", ""), ts)
        link = f"https://www.bilibili.com/video/{c.get('video')}?t={int(ts[0]) if ts else 0}"
        lines.append(f"## {i}. `{c['id']}`（{c.get('blogger')}｜{c.get('type')}｜"
                     f"动作：{'、'.join(c.get('exercises') or [])}）")
        lines.append("")
        lines.append(f"- 视频：{title or c.get('video')}（[跳转]({link})）")
        lines.append(f"- **claim**：{c.get('claim')}")
        lines.append(f"- **transcript 原文**：{original}")
        lines.append("- **预核结论**：（待填：✅ 与原文一致 / ⚠️ 有夸饰或偏差 / ❌ 原文无据）")
        lines.append("")

    text = "\n".join(lines) + "\n"
    if args.out:
        (ROOT / args.out).write_text(text, encoding="utf-8")
        print(f"已写入 {ROOT / args.out}（{len(targets)} 条）")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
