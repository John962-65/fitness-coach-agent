"""视频 → 文字稿流水线（R4 一手素材，设计书 19.2 ②"拿字幕"）

从 B 站 / 抖音拿视频内容，产出 distill.py 可用的文字稿 JSON（本地私有，不进 git）：
  sources/transcripts/<博主>/<视频id>.json
  字段：{"video", "blogger", "title", "url", "platform", "fetched_at",
         "source": "bilibili_subs" | "whisper-<模型>", "segments": [{"start","end","text"}]}

获取路径（按优先级自动降级）：
  1. B 站字幕：登录 cookie 后可拿 CC / AI 字幕，最准（ts 为全片绝对秒）
  2. 音频 → faster-whisper 本地转写（兜底；合集长视频建议用 --sections 截取时间窗，
     产出的 ts 仍换算回全片绝对时间，claim 可直接定位回原片）

用法：
  # B 站单视频：先试字幕，拿不到再转写。长视频用 --sections 截前 N 分钟
  python3 tools/fetch_transcript.py \
      --url "https://www.bilibili.com/video/BV17ooLBUEqS" \
      --blogger 谭成义 --sections 0-1800

  # B 站无浏览器登录：终端出二维码，手机 B 站 App 扫码，cookie 自动存 sources/cookies/bilibili.txt
  python3 tools/fetch_transcript.py --bili-qr-login

  # B 站空间批量枚举（需 cookie；先 --list-only 看清单再 --yes 逐个抓）
  python3 tools/fetch_transcript.py --space 521903482 --blogger 谭成义 \
      --cookie-file sources/cookies/bilibili.txt --list-only
  python3 tools/fetch_transcript.py --space 521903482 --blogger 谭成义 \
      --cookie-file sources/cookies/bilibili.txt --yes --limit 5

  # 抖音：单视频分享链 / 主页作品（f2 走 cookie，未登录 cookie 不稳定）
  python3 tools/fetch_transcript.py --url "https://v.douyin.com/xxxx/" \
      --blogger 谭成义 --cookie-file sources/cookies/douyin.txt
  python3 tools/fetch_transcript.py --douyin-user MS4wLjABAAAA.... \
      --blogger 谭成义 --cookie-file sources/cookies/douyin.txt --limit 10

拿到文字稿后接提炼（draft claims 待人工审核，不直接进知识库）：
  python3 tools/distill.py sources/transcripts/谭成义/BVxxxx.json --blogger 谭成义
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRANSCRIPTS = ROOT / "sources" / "transcripts"
COOKIES_DIR = ROOT / "sources" / "cookies"
FETCH_LOG = ROOT / "sources" / "fetch_log.jsonl"

DEFAULT_WHISPER_MODEL = "small"


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------- cookie 工具 ----------

def cookies_to_header(cookie_file: Path) -> str:
    """Netscape cookies.txt → f2 需要的 "k=v; k2=v2" 头字符串"""
    pairs = []
    for line in cookie_file.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


# ---------- B 站二维码登录（无浏览器拿 cookie） ----------

def bili_qr_login(out_file: Path) -> None:
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

    import qrcode

    def _print_qr(qr_url: str) -> None:
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_url)
        qr.print_ascii(invert=True)

    # 二维码 3 分钟过期：过期自动换新码，最多 3 轮（约 9 分钟）
    for round_i in range(3):
        r = s.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                  timeout=15).json()
        qr_url, qrcode_key = r["data"]["url"], r["data"]["qrcode_key"]
        _print_qr(qr_url)
        log("↑ 用手机 B 站 App 扫码登录（3 分钟内有效，过期自动换新码）…")

        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(3)
            resp = s.get("https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                         params={"qrcode_key": qrcode_key}, timeout=15)
            p = resp.json()
            code = p["data"]["code"]
            if code == 86038:  # 过期 → 换新码
                log("（二维码已过期，换新码…）")
                break
            if code == 0:
                # 登录 cookie 在"确认登录"这次响应的 Set-Cookie 里；
                # 只看 session 罐会漏（实测只拿到匿名 cookie），两处合并
                cookies = dict(resp.cookies)
                cookies.update({k: v for k, v in s.cookies.get_dict().items()
                                if k not in cookies})
                if "SESSDATA" not in cookies:
                    sys.exit("❌ 登录响应里没有 SESSDATA（异常），未写任何文件")
                # 落盘前当场验证登录态
                nav = s.get("https://api.bilibili.com/x/web-interface/nav", timeout=15,
                            cookies={"SESSDATA": cookies["SESSDATA"]}).json()
                d = nav.get("data") or {}
                if not d.get("isLogin"):
                    sys.exit("❌ cookie 验证未通过（nav 未登录），未写任何文件")
                out_file.parent.mkdir(parents=True, exist_ok=True)
                exp = str(int(time.time() + 180 * 86400))  # 180 天，避免写成"立即过期"
                lines = ["# Netscape HTTP Cookie File"
                         "（fetch_transcript.py --bili-qr-login 生成）"]
                for k, v in cookies.items():
                    lines.append(f".bilibili.com\tTRUE\t/\tTRUE\t{exp}\t{k}\t{v}")
                out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                log(f"✅ 已验证登录：{d.get('uname', '?')}"
                    f"（{len(cookies)} 条 cookie），已存 {out_file}")
                return
        else:
            continue
    sys.exit("三轮二维码都没等到扫码。可改在自己 SSH 终端里重跑，"
             "或从 Windows 浏览器导出 cookies.txt 放 " + str(out_file))


# ---------- B 站 ----------

SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def srt_to_segments(srt_path: Path) -> list[dict]:
    """SRT → segments（秒；B 站字幕时间本就是全片绝对时间）"""
    text = srt_path.read_text(encoding="utf-8", errors="replace")
    out: list[dict] = []
    start = end = None
    buf: list[str] = []

    def flush() -> None:
        if start is not None and end is not None:
            t = " ".join(x.strip() for x in buf if x.strip())
            if t:
                out.append({"start": round(start, 2), "end": round(end, 2), "text": t})

    for line in text.splitlines():
        m = SRT_TIME.search(line)
        if m:
            flush()
            g = [int(x) for x in m.groups()]
            start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            buf = []
        elif line.strip() and not line.strip().isdigit():
            buf.append(line)
    flush()
    return out


def bili_subs_via_cli(url: str, cookie_file: Path | None, workdir: Path) -> tuple[str, list[dict]] | None:
    """用 yt-dlp CLI 拉字幕（Python API 与 CLI 行为不一致：CLI 实测稳定能拿到 ai-zh）"""
    import yt_dlp

    langs = "ai-zh,zh-Hans,zh-CN,zh"
    cmd = ["yt-dlp", "--skip-download", "--write-subs", "--sub-langs", langs,
           "--sub-format", "srt", "-o", str(workdir / "sub.%(ext)s")]
    if cookie_file and cookie_file.exists():
        cmd += ["--cookies", str(cookie_file)]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        log(f"（yt-dlp 拉字幕失败：{(proc.stderr or '').strip().splitlines()[-1:]}）")
        return None
    srts = sorted(workdir.glob("sub.*.srt"))
    if not srts:
        return None
    # 语言优先级：ai-zh > zh-Hans > zh-CN > zh（文件名 sub.<lang>.srt）
    order = {"ai-zh": 0, "zh-Hans": 1, "zh-CN": 2, "zh": 3}
    best = min(srts, key=lambda p: order.get(p.stem.split(".")[-1], 9))
    lang = best.stem.split(".")[-1]
    return lang, srt_to_segments(best)

def ydl_opts(cookie_file: Path | None, extra: dict | None = None) -> dict:
    import yt_dlp

    yt_dlp.utils.bug_reports_message = lambda *a, **k: ""  # 静音弃用告警
    opts: dict = {"quiet": True, "no_warnings": True, "noprogress": True}
    if cookie_file and cookie_file.exists():
        opts["cookiefile"] = str(cookie_file)
    if extra:
        opts.update(extra)
    return opts


def bili_subs_to_segments(sub_url: str) -> list[dict]:
    """B 站字幕接口返回 {body:[{from,to,content}]}，直接映射成 segments（绝对秒）"""
    import requests

    data = requests.get(sub_url, timeout=30,
                        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"}).json()
    body = data.get("body") or []
    return [{"start": round(b["from"], 2), "end": round(b["to"], 2),
             "text": re.sub(r"\s+", " ", b["content"]).strip()} for b in body]


def fetch_bilibili(url: str, blogger: str, cookie_file: Path | None,
                   sections: str | None, whisper_model: str,
                   keep_audio: bool) -> dict:
    import yt_dlp

    meta = {}
    with yt_dlp.YoutubeDL(ydl_opts(cookie_file)) as ydl:
        info = ydl.extract_info(url, download=False)
        vid = info.get("id", "")
        title = info.get("title", "")
        duration = info.get("duration") or 0
        meta = {"video": vid, "title": title, "url": url,
                "uploader": info.get("uploader", ""), "duration": duration}

    workdir = Path(tempfile.mkdtemp(prefix="fetch_"))
    got = bili_subs_via_cli(url, cookie_file, workdir)
    if got:
        lang, segments = got
        log(f"✅ 拿到 B 站字幕（{lang}，{len(segments)} 段），无需转写")
        if sections:
            a, b = (float(x) for x in sections.split("-"))
            segments = [s for s in segments if s["end"] > a and s["start"] < b]
        return {"source": "bilibili_subs", "segments": segments, **meta}

    reason = "未登录（AI 字幕在登录墙后）" if not (cookie_file and cookie_file.exists()) \
        else "该视频没有可用的中文字幕"
    log(f"⚠️ 拿不到字幕（{reason}），降级为音频 → faster-whisper（{whisper_model}）")

    if sections:
        log("（B 站分段需整段音频流才能裁剪：先下完整音频，再 ffmpeg 本地截取）")
    dl_opts = ydl_opts(cookie_file, {
        "format": "ba/b",
        "outtmpl": str(workdir / "audio.%(ext)s"),
    })
    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        ydl.download([url])
    audio = next(workdir.glob("audio.*"))
    if sections:
        a, b = (float(x) for x in sections.split("-"))
        cut = workdir / "clip.m4a"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(a), "-to", str(b),
                        "-i", str(audio), "-c", "copy", str(cut)], check=True)
        audio = cut
    offset = float(sections.split("-")[0]) if sections else 0.0
    segments = whisper_transcribe(audio, whisper_model, offset)
    out_audio = ROOT / "sources" / "frames" / "audio"
    if keep_audio:
        out_audio.mkdir(parents=True, exist_ok=True)
        audio.replace(out_audio / f"{meta['video']}{audio.suffix}")
    return {"source": f"whisper-{whisper_model}", "segments": segments, **meta}


def bili_space_list(uid: str, cookie_file: Path | None, with_titles: bool = True) -> list[dict]:
    import yt_dlp

    url = f"https://space.bilibili.com/{uid}/video"
    opts = ydl_opts(cookie_file, {"extract_flat": True, "playlistend": 100})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    items = [{"id": e.get("id", ""), "title": e.get("title", "")}
             for e in (info.get("entries") or []) if e.get("id")]
    # flat 枚举拿不到标题（实测为空）——用 view API 逐个补
    if with_titles and any(not it["title"] for it in items):
        import requests

        cookies = {}
        if cookie_file and cookie_file.exists():
            for line in cookie_file.read_text().splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                t = line.split("\t")
                if len(t) == 7:
                    cookies[t[5]] = t[6]
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0",
                          "Referer": "https://space.bilibili.com/"})
        for it in items:
            if it["title"]:
                continue
            try:
                v = s.get("https://api.bilibili.com/x/web-interface/view",
                          params={"bvid": it["id"]}, cookies=cookies, timeout=15).json()
                d = v.get("data") or {}
                it["title"] = d.get("title", "")
                it["duration"] = d.get("duration", 0)
                it["desc"] = (d.get("desc") or "")[:80]
            except Exception:
                pass
            time.sleep(0.25)
    return items


# ---------- 抖音（f2） ----------

def f2_download(url: str, cookie_header: str, outdir: Path, mode: str,
                max_counts: int) -> list[Path]:
    cmd = ["f2", "dy", "-M", mode, "-u", url, "-p", str(outdir),
           "--folderize", "false", "-m", "false", "-v", "false", "-d", "true",
           "-o", str(max_counts), "-n", "{aweme_id}"]
    if cookie_header:
        cmd += ["-k", cookie_header]
    log(f"$ {' '.join(c for c in cmd if c != cookie_header)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-8:])
    if proc.returncode != 0:
        raise RuntimeError(f"f2 失败（退出码 {proc.returncode}）：\n{tail}")
    videos = sorted(outdir.glob("*.mp4"))
    if not videos:
        raise RuntimeError(f"f2 没有产出视频文件：\n{tail}")
    log(tail)
    return videos


def fetch_douyin(url: str, blogger: str, cookie_file: Path | None,
                 max_counts: int, whisper_model: str) -> list[dict]:
    cookie_header = cookies_to_header(cookie_file) if cookie_file and cookie_file.exists() else ""
    if not cookie_header:
        log("⚠️ 抖音未提供 cookie：可能仅部分视频可用且不稳定（f2 未登录限制）")
    mode = "post" if "/user/" in url else "one"
    workdir = Path(tempfile.mkdtemp(prefix="douyin_"))
    try:
        videos = f2_download(url, cookie_header, workdir, mode, max_counts)
    except Exception as e:
        raise RuntimeError(
            f"抖音拉取失败。f2 需要**登录 cookie**才能稳定下载：\n"
            f"  1. 浏览器登录 www.douyin.com 后导出 cookies.txt（Get cookies.txt 扩展）\n"
            f"  2. 传 --cookie-file sources/cookies/douyin.txt 重试\n{e}") from e
    results = []
    for mp4 in videos:
        vid = mp4.stem
        log(f"→ 转写 {vid}（{mp4.stat().st_size // 1024}KB）")
        segments = whisper_transcribe(mp4, whisper_model, 0.0)
        results.append({"video": vid, "title": vid, "url": url,
                        "uploader": blogger, "duration": 0,
                        "source": f"whisper-{whisper_model}", "segments": segments})
    return results


# ---------- whisper ----------

def whisper_transcribe(audio: Path, model_size: str, offset: float) -> list[dict]:
    from faster_whisper import WhisperModel

    log(f"⏳ faster-whisper/{model_size} 转写中（CPU，中文，VAD 开）…")
    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8",
                         cpu_threads=min(10, os.cpu_count() or 4))
    segments, info = model.transcribe(str(audio), language="zh", vad_filter=True,
                                      beam_size=1)
    out = [{"start": round(offset + s.start, 1), "end": round(offset + s.end, 1),
            "text": s.text.strip()}
           for s in segments if s.text.strip()]
    log(f"✅ 转写完成：{info.duration:.0f}s 音频 → {len(out)} 段，"
        f"耗时 {time.time() - t0:.0f}s")
    return out


# ---------- 落盘 ----------

def write_transcript(blogger: str, data: dict) -> Path:
    outdir = TRANSCRIPTS / blogger
    outdir.mkdir(parents=True, exist_ok=True)
    data = {"blogger": blogger, **data}  # distill.py 必需字段
    out = outdir / f"{data['video']}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    with FETCH_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "at": dt.datetime.now().isoformat(timespec="seconds"),
            "blogger": blogger, "video": data["video"],
            "platform": data.get("platform", "?"), "source": data["source"],
            "segments": len(data["segments"]), "out": str(out.relative_to(ROOT)),
        }, ensure_ascii=False) + "\n")
    log(f"💾 文字稿已存 {out.relative_to(ROOT)}（{len(data['segments'])} 段）")
    return out


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("用法")[0])
    ap.add_argument("--url", help="B 站视频 URL/BV 号，或抖音分享链")
    ap.add_argument("--space", help="B 站空间 uid（批量枚举）")
    ap.add_argument("--douyin-user", help="抖音主页 sec_uid 或主页链接（批量）")
    ap.add_argument("--blogger", default="谭成义")
    ap.add_argument("--cookie-file", type=Path, help="Netscape cookies.txt")
    ap.add_argument("--bili-qr-login", action="store_true",
                    help="B 站扫码登录，cookie 存 sources/cookies/bilibili.txt")
    ap.add_argument("--sections", help="只取一段时间窗，如 0-1800（秒，全片绝对时间）")
    ap.add_argument("--whisper-model", default=DEFAULT_WHISPER_MODEL,
                    help="tiny/base/small/medium（默认 small）")
    ap.add_argument("--limit", type=int, default=10, help="批量模式最多处理几个")
    ap.add_argument("--list-only", action="store_true",
                    help="批量模式只列清单不下载")
    ap.add_argument("--yes", action="store_true", help="批量模式确认逐个抓取")
    ap.add_argument("--keep-audio", action="store_true", help="保留音频到 sources/frames/audio")
    args = ap.parse_args()

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)

    if args.bili_qr_login:
        bili_qr_login(COOKIES_DIR / "bilibili.txt")
        return 0

    # --- 批量枚举 ---
    if args.space:
        try:
            items = bili_space_list(args.space, args.cookie_file)
        except Exception as e:
            sys.exit(f"空间枚举失败：{e}\n"
                     "（B 站风控要求登录：先跑 --bili-qr-login 生成 cookie，"
                     "再用 --cookie-file sources/cookies/bilibili.txt 重试）")
        log(f"B 站空间 {args.space} 共取到 {len(items)} 个视频：")
        for it in items[:args.limit]:
            dur = it.get("duration")
            dtxt = f" | {dur // 60}分{dur % 60:02d}秒" if dur else ""
            log(f"  {it['id']} | {it['title'][:40]}{dtxt}")
        if not args.yes:
            log("（确认后加 --yes --limit N 逐个抓取）")
            return 0
        out = []
        for it in items[:args.limit]:
            try:
                data = fetch_bilibili(f"https://www.bilibili.com/video/{it['id']}",
                                      args.blogger, args.cookie_file, args.sections,
                                      args.whisper_model, args.keep_audio)
                data["platform"] = "bilibili"
                out.append(write_transcript(args.blogger, data))
            except Exception as e:
                log(f"❌ {it['id']} 失败：{e}")
        return 0 if out else 1

    if args.douyin_user:
        u = args.douyin_user
        if not u.startswith("http"):
            u = f"https://www.douyin.com/user/{u}"
        header = cookies_to_header(args.cookie_file) if args.cookie_file and args.cookie_file.exists() else ""
        workdir = Path(tempfile.mkdtemp(prefix="douyin_"))
        videos = f2_download(u, header, workdir, "post", args.limit)
        n = 0
        for mp4 in videos:
            segments = whisper_transcribe(mp4, args.whisper_model, 0.0)
            data = {"video": mp4.stem, "title": mp4.stem, "url": u,
                    "uploader": args.blogger, "duration": 0,
                    "source": f"whisper-{args.whisper_model}", "segments": segments,
                    "platform": "douyin"}
            write_transcript(args.blogger, data)
            n += 1
        return 0 if n else 1

    # --- 单视频 ---
    if not args.url:
        ap.print_help()
        return 2
    url = args.url
    if re.fullmatch(r"(BV[\w]+|av\d+)", url):
        url = f"https://www.bilibili.com/video/{url}"
    if "bilibili.com" in url or url.startswith("BV"):
        data = fetch_bilibili(url, args.blogger, args.cookie_file, args.sections,
                              args.whisper_model, args.keep_audio)
        data["platform"] = "bilibili"
        write_transcript(args.blogger, data)
    elif "douyin.com" in url:
        for data in fetch_douyin(url, args.blogger, args.cookie_file,
                                 args.limit, args.whisper_model):
            data["platform"] = "douyin"
            write_transcript(args.blogger, data)
    else:
        sys.exit(f"无法识别平台：{url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
