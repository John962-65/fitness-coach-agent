"""claims 人工审核工具（设计书 19.2 ④ / 21.3）——CLI 版

审核界面在终端完成（发起人浏览器连不到本机端口）；每条 claim 给出：
  原文片段（segment_text_at）+ 视频跳转链接（bilibili.com/video/BV?t=秒）+ 可选关键帧

用法：
  python3 tools/review_ui.py --list [--flagged-only] [--video BV1xx]
  python3 tools/review_ui.py --show tcy-0001
  python3 tools/review_ui.py --approve tcy-0001 --stage source --speaker 已确认发言者 --by 实际审核者 --note 核对依据
  python3 tools/review_ui.py --approve tcy-0001 --stage applicability --by 实际审核者 --note 适用条件
  python3 tools/review_ui.py --reject tcy-0001 --note "不是他的观点"
  python3 tools/review_ui.py --edit tcy-0001 --claim "修正后的表述"
  python3 tools/review_ui.py --keyframes tcy-0001     # 下载片段并截 3 帧（sources/frames/）
  python3 tools/review_ui.py --apply                  # 已审核条目挂到动作库字段（21.2 ③a）

来源与适用性两步都通过且内容未变化后，才进入 approved 并允许点名引用。
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
from coach.claim_review import invalidate_review, is_publishable, record_review, review_issues

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
    if claim.get("speaker"):
        # 多人出镜/AI 字幕不分说话人的视频：归属待审核时确认
        print(f"    说话人：{claim['speaker']}")
    if claim.get("exercises"):
        print(f"    动作：{'、'.join(claim['exercises'])}")
    print(f"    原文：{transcript_excerpt(claim)[:160]}")
    print(f"    门槛：{'可引用' if is_publishable(claim) else '；'.join(review_issues(claim))}")
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
    """同步本来源的有效引用；撤销/变更后清除旧引用，不影响其他来源。"""
    claims = load_all(blogger_file)
    owned = {c["id"] for c in claims}
    usable = [c for c in claims if is_publishable(c)]
    n = 0
    for path in sorted((ROOT / "exercises").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        changed = False
        for field in set(TYPE_TO_FIELD.values()):
            current = data.get(field) or []
            wanted = [c["id"] for c in usable if data["id"] in (c.get("exercises") or [])
                      and TYPE_TO_FIELD.get(c["type"]) == field]
            updated = list(dict.fromkeys([r for r in current if r not in owned] + wanted))
            if updated != current:
                data[field] = updated
                changed = True
        if changed:
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                            encoding="utf-8")
            n += 1
    print(f"已同步 {n} 个动作的双层审核有效引用；草稿和失效审核不可引用")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blogger", choices=list(BLOGGER_FILE.values()), default="谭成义")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--flagged-only", action="store_true")
    ap.add_argument("--video", default="")
    ap.add_argument("--exercise", default="",
                    help="只列出与该动作相关的条目（先审当前计划用到的动作："
                         "cue/error/self_check 优先，anecdote 可批量跳过）")
    ap.add_argument("--types", default="",
                    help="只列出指定类型（逗号分隔，如 cue,error,self_check）")
    ap.add_argument("--show", default="")
    ap.add_argument("--approve", default="")
    ap.add_argument("--reject", default="")
    ap.add_argument("--edit", default="")
    ap.add_argument("--claim", default="")
    ap.add_argument("--exercise-ids", default=None, help="与 --edit 配合修正动作映射，逗号分隔；空字符串清除映射")
    ap.add_argument("--note", default="")
    ap.add_argument("--by", default="", help="实际审核者，不自动代填")
    ap.add_argument("--stage", choices=["source", "applicability"])
    ap.add_argument("--speaker", default="", help="对照原片确认的发言者")
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
        if args.speaker and args.speaker != c.get("speaker"):
            c["speaker"] = args.speaker
            invalidate_review(c)
        if args.stage == "source" and transcript_excerpt(c).startswith("（"):
            sys.exit("本地缺少对应原文，不能签核来源；先导入或修正时间窗")
        try:
            record_review(c, args.stage, args.by, args.note)
        except ValueError as e:
            sys.exit(str(e))
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
        if not args.claim and args.exercise_ids is None and not args.speaker:
            sys.exit("--edit 需要 --claim / --exercise-ids / --speaker 至少一项")
        if args.claim:
            c["claim"] = args.claim
        if args.exercise_ids is not None:
            from coach.exercises import library
            ids = [s.strip() for s in args.exercise_ids.split(",") if s.strip()]
            if any(library.get(eid) is None for eid in ids):
                sys.exit("包含动作库不存在的 ID；不能把未知变式强行归类")
            c["exercises"] = ids
        if args.speaker:
            c["speaker"] = args.speaker
        invalidate_review(c)
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
    type_filter = {t.strip() for t in args.types.split(",") if t.strip()}
    shown = 0
    for c in claims:
        if args.flagged_only and c.get("anti_hallucination") != "FLAGGED":
            continue
        if args.video and c.get("video") != args.video:
            continue
        if args.exercise and args.exercise not in (c.get("exercises") or []):
            continue
        if type_filter and c.get("type") not in type_filter:
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
