"""Q19 主题采集扫描（发起人 2026-10-11 选「继续采集」，2026-10-11）。

免费步骤，不调用任何 LLM：
1. 对三个空间尚未抓取字幕的视频逐个拉 B 站字幕（并发 1、限速、幂等可续传）；
2. 对全部本地字幕扫描「平台期」与「停训复训」关键词，命中窗口记入 hits。
提炼需要额度（collection_batch_20261009 已 6/6 用尽），本脚本不做提炼。
"""
from __future__ import annotations

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

RUNS = ROOT / "sources" / "maintenance" / "runs"
HITS = RUNS / "q19_theme_scan_hits.json"
STATUS = RUNS / "q19_theme_scan_status.jsonl"
LOG = RUNS / "q19_theme_scan.log"

THEMES = {
    "平台期": re.compile(r"平台期|不掉秤|体重不降|减不下去|瘦不下来"),
    "停训复训": re.compile(r"停训|复训|中断.{0,6}训练|好久没练|休息.{0,4}(一|两|几)个?(月|周|星期)"),
}


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


def load_hits() -> dict:
    if HITS.exists():
        return json.loads(HITS.read_text(encoding="utf-8"))
    return {k: [] for k in THEMES}


def scan_local(blogger: str, bv: str, hits: dict) -> int:
    """对本地已有字幕做关键词扫描，返回本次新增命中数。"""
    p = FT_ROOT / "sources" / "transcripts" / blogger / f"{bv}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    segs = data.get("segments", [])
    new = 0
    seen = {(h["video"], h["t"]) for h in hits["平台期"] + hits["停训复训"]}
    for i, s in enumerate(segs):
        t = s.get("text", "")
        for name, pat in THEMES.items():
            if pat.search(t):
                key = (bv, int(s.get("start", 0)))
                if key in seen:
                    continue
                win = "".join(x.get("text", "") for x in segs[max(0, i - 2):i + 3])
                hits[name].append({"blogger": blogger, "video": bv,
                                   "t": int(s.get("start", 0)), "window": win[:150]})
                new += 1
    return new


def fetch_and_scan(blogger: str, bv: str, cookie: Path, hits: dict) -> None:
    url = f"https://www.bilibili.com/video/{bv}"
    workdir = Path(tempfile.mkdtemp(prefix="sweep_q19_"))
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
    n = scan_local(blogger, bv, hits)
    with open(STATUS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"video": bv, "blogger": blogger, "result": "fetched",
                            "segments": len(segments), "theme_hits": n},
                           ensure_ascii=False) + "\n")
    log(f"{blogger}/{bv} ✅ {len(segments)} 段，主题命中 {n}")


def main() -> int:
    cookie = ROOT / "sources" / "cookies" / "bilibili.txt"
    hits = load_hits()
    # 先扫本地存量（含此前已抓但未提炼的）
    local_new = 0
    for blogger in ("凯圣王", "谭成义", "陈石"):
        for bv in space_videos(blogger):
            if already_fetched(blogger, bv):
                local_new += scan_local(blogger, bv, hits)
    log(f"本地存量扫描完成，新增命中 {local_new}")

    todo = []
    for blogger in ("凯圣王", "谭成义", "陈石"):
        for bv in space_videos(blogger):
            if not already_fetched(blogger, bv):
                todo.append((blogger, bv))
    log(f"开始抓取未抓视频：{len(todo)} 个")
    n = fails = 0
    for b, bv in todo:
        n += 1
        try:
            fetch_and_scan(b, bv, cookie, hits)
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
        time.sleep(1.5)
    HITS.write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, hs in hits.items():
        vids = sorted({h["video"] for h in hs})
        log(f"汇总[{name}]：{len(hs)} 处 / {len(vids)} 个视频")
    log("本轮结束")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
