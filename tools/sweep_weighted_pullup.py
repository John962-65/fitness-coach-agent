"""负重引体全量字幕扫描（Q9 选项 a，2026-10-09）。

只做免费步骤：对未抓取字幕的视频逐个拉 B 站字幕（并发 1、限速），
命中「引体±负重/加重/腰带/配重/铁链」的窗口记录到 hits jsonl。
不提炼、不调用任何 LLM；无中文字幕的视频跳过并记录（不降级 whisper，省算力）。
幂等：已有字幕文件的视频自动跳过，可随时中断重跑。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from fetch_transcript import ROOT as FT_ROOT, bili_subs_via_cli, write_transcript  # noqa: E402

HITS = ROOT / "sources" / "maintenance" / "runs" / "sweep_weighted_pullup_hits.jsonl"
STATUS = ROOT / "sources" / "maintenance" / "runs" / "sweep_weighted_pullup_status.jsonl"
LOG = ROOT / "sources" / "maintenance" / "runs" / "sweep_weighted_pullup.log"

KEY = re.compile(r"引体")
WEIGHT = re.compile(r"负重|加重|配重|腰带|杠铃片|铁链|挂片")


def space_videos(blogger: str) -> list[str]:
    key = {"凯圣王": "ksw", "谭成义": "tcy", "陈石": "cs"}[blogger]
    txt = (ROOT / "sources" / "manifest" / f"{key}_space.txt").read_text(encoding="utf-8")
    return re.findall(r"(BV[0-9A-Za-z]{10})", txt)


def already_fetched(blogger: str, bv: str) -> bool:
    return (FT_ROOT / "sources" / "transcripts" / blogger / f"{bv}.json").exists()


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def scan(blogger: str, bv: str, cookie: Path) -> None:
    url = f"https://www.bilibili.com/video/{bv}"
    workdir = Path(tempfile.mkdtemp(prefix="sweep_"))
    got = bili_subs_via_cli(url, cookie, workdir)
    if not got:
        with open(STATUS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"video": bv, "blogger": blogger, "result": "no_subs"},
                               ensure_ascii=False) + "\n")
        log(f"{blogger}/{bv} 无中文字幕，跳过")
        return
    lang, segments = got
    data = {"source": f"bilibili_subs:{lang}", "segments": segments,
            "video": bv, "blogger": blogger, "url": url}
    write_transcript(blogger, data)
    hits = []
    for i, s in enumerate(segments):
        t = s.get("text", "")
        if KEY.search(t):
            win = "".join(x.get("text", "") for x in segments[max(0, i - 2):i + 3])
            if WEIGHT.search(win):
                hits.append({"t": int(s.get("start", 0)), "text": t[:60],
                             "window": win[:120]})
    if hits:
        with open(HITS, "a", encoding="utf-8") as f:
            for h in hits:
                f.write(json.dumps({"blogger": blogger, "video": bv, **h},
                                   ensure_ascii=False) + "\n")
        log(f"*** {blogger}/{bv} 命中 {len(hits)} 处（t={hits[0]['t']}）：{hits[0]['window'][:60]}")
    with open(STATUS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"video": bv, "blogger": blogger, "result": "fetched",
                            "segments": len(segments), "pullup_weight_hits": len(hits)},
                           ensure_ascii=False) + "\n")
    log(f"{blogger}/{bv} ✅ {len(segments)} 段，引体相关命中 {len(hits)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bloggers", nargs="+", default=["凯圣王", "谭成义"])
    ap.add_argument("--max", type=int, default=0, help="本轮最多处理几个（0=不限）")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--cookie", type=Path,
                    default=ROOT / "sources" / "cookies" / "bilibili.txt")
    args = ap.parse_args()

    todo = []
    for b in args.bloggers:
        for bv in space_videos(b):
            if not already_fetched(b, bv):
                todo.append((b, bv))
    log(f"扫描开始：{args.bloggers} 共待抓 {len(todo)} 个")
    n = fails = 0
    for b, bv in todo:
        if args.max and n >= args.max:
            log(f"达到本轮上限 {args.max}，检查点退出")
            break
        n += 1
        try:
            scan(b, bv, args.cookie)
            fails = 0
        except Exception as e:  # 风控/网络：退避后继续，连续失败即停
            fails += 1
            log(f"{b}/{bv} ❌ {str(e)[:100]}")
            with open(STATUS, "a", encoding="utf-8") as f:
                f.write(json.dumps({"video": bv, "blogger": b, "result": "error",
                                    "error": str(e)[:120]}, ensure_ascii=False) + "\n")
            if fails >= 6:
                log("连续 6 次失败，停止本轮（疑似风控），稍后重跑会续传")
                break
            time.sleep(20)
        time.sleep(args.sleep)
    log(f"本轮结束：处理 {n} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
