"""补全 Q8 画面核对清单：10-08 版每视频只列前 4 条，本脚本列全 31 条（2026-10-09）。

只读素材、生成清单；不修改 claims、不代替发起人做归属确认（任务书 §3）。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools._p1_batch2_20261008 import PUBDATE, claim_text, context_before
from tools._card_batch_20261008 import load_all_claims, transcript_segments

OUT = ROOT / "sources" / "review_packet" / "p1_speaker_sheet_20261009.md"
TARGETS = [("lying_leg_curl", "俯身/俯卧腿弯举"),
           ("standing_calf_raise", "站姿提踵")]


def main() -> int:
    claims = load_all_claims()
    transcripts = transcript_segments()
    lines = ["# P1 待画面确认发言者清单·全量版（2026-10-09）", "",
             "> 补全 10-08 版：原清单每个视频只列前 4 条，本版列全全部待确认条目，"
             "每条带跳转点与前 18 秒交接词线索。", "",
             "> 语境线索只是辅助，按任务书 §3 不能代替对照画面确认；"
             "归属确认由发起人逐条给出，Zcode 不代签。", ""]
    total = 0
    for ex, cn in TARGETS:
        every = [c for c in claims.values() if ex in (c.get("exercises") or [])]
        sel = [c for c in every
               if not str(c.get("speaker") or "").strip()
               or any(m in str(c.get("speaker"))
                      for m in ("待确认", "未知", "不确定", "语境归因"))]
        total += len(sel)
        lines.append(f"## {cn}（`{ex}`）· 已挂 {len(every)} 条，待确认 {len(sel)} 条")
        lines.append("")
        by_video: dict[str, list] = {}
        for c in sel:
            by_video.setdefault(c["video"], []).append(c)
        for video, items in sorted(by_video.items(), key=lambda kv: -len(kv[1])):
            bloggers = "、".join(sorted({str(i.get("blogger")) for i in items}))
            date = PUBDATE.get(video, "发布日期未核对")
            lines.append(f"### {video}（{len(items)} 条）｜记录归属：{bloggers}｜发布：{date}")
            lines.append("")
            for c in sorted(items, key=lambda i: i["ts"][0]):
                lines.append(f"- [ ] [{c['id']}] type={c.get('type')} "
                             f"t={int(c['ts'][0])} "
                             f"https://www.bilibili.com/video/{video}"
                             f"?t={int(c['ts'][0])}")
                lines.append(f"  - 说法：{claim_text(c)[:70]}")
                ctx = context_before(transcripts.get(video, []), c["ts"][0])
                if ctx:
                    lines.append(f"  - 前文线索：{ctx}")
            lines.append("")
    lines.append(f"合计待确认 {total} 条。确认方式：逐条勾选或在回复里直接说"
                 f"「全部按记录归属确认」/指出需要改归属的条目 id。")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {OUT}｜待确认 {total} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
