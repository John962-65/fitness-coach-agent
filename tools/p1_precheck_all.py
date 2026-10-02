"""全量 P1 claims transcript 对照分流（24.1 配套，flagged_precheck 的推广）

> 对 P1 范围全部 claims 计算 claim 与 transcript 原文窗口的字符 bigram
> 重合度（Dice 系数），按分数分三档：
>   高（>=HI）：大概率与原文一致，人工抽查即可
>   中（LO–HI）：建议人工/AI 精读
>   低（<LO）或无 transcript：优先精读
> ASR 常见错字先做归一化（宽脚链→髋铰链 等），避免误伤正确还原的 claim。
> 分数只是分流工具，不作 approve/reject 依据。

用法：
  python3 tools/p1_precheck_all.py                        # 只看统计
  python3 tools/p1_precheck_all.py --out precheck_all.md  # 全量报告（低分带原文）
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.flagged_precheck import WINDOW_PAD, TRANSCRIPTS  # noqa: E402
from tools.p1_backlog import P1_TYPES, _load_claims, _template_defaults  # noqa: E402

HI, LO = 0.60, 0.35

# ASR 高频错字归一化（比对前统一，两边都替换）
ASR_FIX = [
    ("宽脚链", "髋铰链"), ("国绳肌", "腘绳肌"), ("罗马连音", "罗马尼亚"),
    ("罗马连英", "罗马尼亚"), ("罗马连", "罗马尼亚"), ("钢弦", "钢线"),
    ("持妆面", "矢状面"), ("夹背", "胛背"),
]


def _git_short() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _norm(text: str) -> str:
    text = re.sub(r"[\s，。！？、；：""''（）()【】\[\]…—\-·,.!?;:'\"]", "", text or "")
    for a, b in ASR_FIX:
        text = text.replace(a, b)
    return text


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) > 1 else set()


def _window(blogger: str, video: str, ts: list) -> str | None:
    f = TRANSCRIPTS / blogger / f"{video}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    lo = (ts[0] if ts else 0) - WINDOW_PAD
    hi = (ts[-1] if ts else 0) + WINDOW_PAD
    return "".join(s["text"] for s in d.get("segments", [])
                   if s["end"] >= lo and s["start"] <= hi)


def _score(claim: str, window: str) -> float:
    """claim 侧包含率：claim 的 bigram 有多少能在原文窗口中找到。
    不用 Dice——窗口 ±15s 引入大量旁白会稀释分母，对浓缩改写的 claim 不公平。"""
    a, b = _bigrams(_norm(claim)), _bigrams(_norm(window))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--detail-top", type=int, default=40,
                    help="报告中附原文窗口的最低分条数")
    args = ap.parse_args()

    claims = _load_claims()
    defaults = {e for e, _ in _template_defaults()}
    p1 = [c for c in claims
          if c.get("type") in P1_TYPES and defaults & set(c.get("exercises") or [])]

    rows = []
    for c in p1:
        ts = c.get("ts") or []
        w = _window(c.get("blogger", ""), c.get("video", ""), ts)
        score = _score(c.get("claim", ""), w) if w else -1.0
        rows.append({"c": c, "ts": ts, "window": w, "score": score})

    hi = [r for r in rows if r["score"] >= HI]
    mid = [r for r in rows if LO <= r["score"] < HI]
    low = [r for r in rows if 0 <= r["score"] < LO]
    none = [r for r in rows if r["score"] < 0]

    stat = (f"总 {len(rows)}｜高 {len(hi)}（≥{HI}）｜中 {len(mid)}｜"
            f"低 {len(low)}（<{LO}）｜无 transcript {len(none)}")
    print(stat)

    if not args.out:
        return 0

    rows.sort(key=lambda r: r["score"])
    lines = ["# 全量 P1 claims transcript 对照分流报告", "",
             f"> 生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}｜基线 commit：`{_git_short()}`",
             f"> {stat}｜窗口 ±{WINDOW_PAD:.0f}s｜ASR 错字已归一化 {len(ASR_FIX)} 组",
             "> 分档：高=大概率一致（抽查）；中=建议精读；低/无 transcript=优先精读",
             ""]
    lines.append("## 低分/无 transcript 明细（按分数升序，前 %d 条附原文）" % len(low + none))
    lines.append("")
    for i, r in enumerate(low + none):
        c, ts = r["c"], r["ts"]
        link = f"https://www.bilibili.com/video/{c.get('video')}?t={int(ts[0]) if ts else 0}"
        lines.append(f"### `{c['id']}`（{c.get('blogger')}｜{c.get('type')}｜"
                     f"{'、'.join(c.get('exercises') or [])}｜score={r['score']:.2f}）")
        lines.append(f"- claim：{c.get('claim')}")
        lines.append(f"- 视频：[跳转]({link})")
        if i < args.detail_top and r["window"]:
            lines.append(f"- 原文窗口：{r['window']}")
        lines.append("")
    text = "\n".join(lines) + "\n"
    (ROOT / args.out).write_text(text, encoding="utf-8")
    print(f"已写入 {ROOT / args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
