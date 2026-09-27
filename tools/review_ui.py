"""claims 人工审核工具（设计书 19.2 ④ / 21.3）——CLI 版

审核界面在终端完成（发起人浏览器连不到本机端口）；每条 claim 给出：
  原文片段（segment_text_at）+ 视频跳转链接（bilibili.com/video/BV?t=秒）+ 可选关键帧

用法：
  python3 tools/review_ui.py --list [--flagged-only] [--video BV1xx]
  python3 tools/review_ui.py --show tcy-0001
  python3 tools/review_ui.py --approve tcy-0001 [--by 发起人]
  python3 tools/review_ui.py --reject tcy-0001 --note "不是他的观点"
  python3 tools/review_ui.py --edit tcy-0001 --claim "修正后的表述"
  python3 tools/review_ui.py --keyframes tcy-0001     # 下载片段并截 3 帧（sources/frames/）
  python3 tools/review_ui.py --apply                  # 已审核条目挂到动作库字段（21.2 ③a）

审核通过会把 status: draft → approved 并回填 reviewed；这是博主点名纪律的解锁条件。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.distill import segment_text_at  # noqa: E402

CLAIMS = ROOT / "claims"
TRANSCRIPTS = ROOT / "sources" / "transcripts"
BLOGGER_FILE = {"ksw": "凯圣王", "tcy": "谭成义", "cs": "陈石"}
# 21.2 ③a：claim type → 动作 YAML 字段
TYPE_TO_FIELD = {"cue": "cues", "method": "cues", "error": "errors",
                 "self_check": "self_check"}


def load_all(blogger_file: str) -> list[dict]:
    path = CLAIMS / f"{blogger_file}.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save_all(blogger_file: str, claims: list[dict]) -> None:
    path = CLAIMS / f"{blogger_file}.yaml"
    path.write_text(yaml.safe_dump(claims, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def find(claims: list[dict], cid: str) -> dict | None:
    return next((c for c in claims if c.get("id") == cid), None)


def transcript_excerpt(claim: dict) -> str:
    tf = TRANSCRIPTS / claim["blogger"] / f"{claim['video']}.json"
    if not tf.exists():
        return "（本地无文字稿）"
    data = json.loads(tf.read_text(encoding="utf-8"))
    return segment_text_at(data.get("segments") or [],
                           claim["ts"][0], claim["ts"][1]) or "（该时间窗无原文）"


def jump_url(claim: dict) -> str:
    return f"https://www.bilibili.com/video/{claim['video']}?t={int(claim['ts'][0])}"


def print_claim(claim: dict, idx: str = "") -> None:
    flag = {"pass": "✅", "FLAGGED": "🚩"}.get(claim.get("anti_hallucination"), "?")
    status = claim.get("status", "?")
    print(f"[{idx or claim['id']}] {flag} {status}｜{claim['type']}｜"
          f"{claim['video']} @ {claim['ts'][0]:.0f}-{claim['ts'][1]:.0f}s")
    print(f"    观点：{claim['claim']}")
    if claim.get("exercises"):
        print(f"    动作：{'、'.join(claim['exercises'])}")
    print(f"    原文：{transcript_excerpt(claim)[:160]}")
    print(f"    跳转：{jump_url(claim)}")


def keyframes(claim: dict, n: int = 3) -> None:
    """下载该时间点附近最短视频片段并截帧（21.3 坑1；仅本地保存）"""
    outdir = ROOT / "sources" / "frames" / claim["video"]
    outdir.mkdir(parents=True, exist_ok=True)
    mid = claim["ts"][0]
    with tempfile.TemporaryDirectory() as td:
        clip = Path(td) / "clip.mp4"
        dl = subprocess.run(
            ["yt-dlp", "-f", "worst", "--download-sections",
             f"*{max(0, mid - 5):.0f}-{mid + 5:.0f}", "-o", str(clip),
             "--no-part", f"https://www.bilibili.com/video/{claim['video']}"],
            capture_output=True, text=True, timeout=300)
        if not clip.exists():
            print(f"截帧失败：{(dl.stderr or '').strip().splitlines()[-1:]}")
            return
        for i in range(n):
            t = claim["ts"][0] + (claim["ts"][1] - claim["ts"][0]) * i / max(n - 1, 1)
            out = outdir / f"{claim['id']}_{i}.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.1f}",
                            "-i", str(clip), "-frames:v", "1", str(out)], check=False)
            if out.exists():
                print(f"🖼 {out.relative_to(ROOT)}")


def apply_to_exercises(blogger_file: str) -> None:
    """审核通过的条目按类型挂到动作 YAML 字段（21.2 ③a）"""
    claims = [c for c in load_all(blogger_file) if c.get("status") == "approved"]
    by_ex: dict[str, list[dict]] = {}
    for c in claims:
        for ex in c.get("exercises") or []:
            by_ex.setdefault(ex, []).append(c)
    n = 0
    for ex_id, cs in sorted(by_ex.items()):
        path = ROOT / "exercises" / f"{ex_id}.yaml"
        if not path.exists():
            print(f"⚠️ 动作库无 {ex_id}，跳过")
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        changed = False
        for c in cs:
            field = TYPE_TO_FIELD.get(c["type"])
            if not field:
                continue
            ref = c["id"]
            if ref not in (data.get(field) or []):
                data.setdefault(field, []).append(ref)
                changed = True
                n += 1
        if changed:
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
    print(f"已把 {n} 条 approved 条目的 id 挂到动作库字段")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blogger", choices=list(BLOGGER_FILE.values()), default="谭成义")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--flagged-only", action="store_true")
    ap.add_argument("--video", default="")
    ap.add_argument("--show", default="")
    ap.add_argument("--approve", default="")
    ap.add_argument("--reject", default="")
    ap.add_argument("--edit", default="")
    ap.add_argument("--claim", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--by", default="发起人")
    ap.add_argument("--keyframes", default="")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    bfile = next(k for k, v in BLOGGER_FILE.items() if v == args.blogger)
    claims = load_all(bfile)
    if args.apply:
        apply_to_exercises(bfile)
        return 0

    if args.approve:
        c = find(claims, args.approve)
        if not c:
            sys.exit(f"找不到 {args.approve}")
        c["status"] = "approved"
        c["reviewed"] = {"by": args.by, "date": date.today().isoformat(),
                         "against": f"{c['video']} 全片"}
        save_all(bfile, claims)
        print_claim(c)
        return 0
    if args.reject:
        c = find(claims, args.reject)
        if not c:
            sys.exit(f"找不到 {args.reject}")
        c["status"] = "rejected"
        c["reviewed"] = {"by": args.by, "date": date.today().isoformat(),
                         "against": args.note}
        save_all(bfile, claims)
        print(f"{args.reject} 已拒绝（{args.note}）")
        return 0
    if args.edit:
        c = find(claims, args.edit)
        if not c:
            sys.exit(f"找不到 {args.edit}")
        if not args.claim:
            sys.exit("--edit 需要同时给 --claim 新表述")
        c["claim"] = args.claim
        save_all(bfile, claims)
        print_claim(c)
        return 0
    if args.keyframes:
        c = find(claims, args.keyframes)
        if not c:
            sys.exit(f"找不到 {args.keyframes}")
        keyframes(c)
        return 0
    if args.show:
        c = find(claims, args.show)
        if not c:
            sys.exit(f"找不到 {args.show}")
        print_claim(c)
        return 0

    # --list（默认）
    shown = 0
    for c in claims:
        if args.flagged_only and c.get("anti_hallucination") != "FLAGGED":
            continue
        if args.video and c.get("video") != args.video:
            continue
        print_claim(c, str(shown))
        shown += 1
        if shown >= 40:
            print(f"（只显示前 40 条，共 {len(claims)} 条）")
            break
    if not shown:
        print("（没有匹配的条目）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
