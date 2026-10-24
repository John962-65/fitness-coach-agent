"""M3.2 视频导入流水线（DESIGN_2.0 §7.4/§十三 任务 5-7、10-13）。

上传视频 →（用户字幕 or 本地 faster-whisper 转写）→ **确定性动作候选**
（转写句对动作库精确/别名匹配，带证据句与时间戳）→ 用户确认：
- link：关联既有动作（生成封面帧与演示片段，失败不阻塞关联）；
- new：新动作候选提案（exercise_proposals，等发起人批准，绝不自动写
  exercises/ 库——沿用"新动作必须用户确认+人工审核"纪律）；
- reject：忽略。
无法可靠识别时如实呈现，不强行匹配（§7.4 ⑫）。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


# ---- 字幕解析 ----

def parse_srt(text: str) -> list[dict]:
    """SRT/VTT → [{start, end, text}]；坏行剔除。"""
    cues = []
    block_text: list[str] = []
    times: tuple[float, float] | None = None
    time_re = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})")

    def _flush() -> None:
        nonlocal times, block_text
        if times and block_text:
            cues.append({"start": times[0], "end": times[1],
                         "text": " ".join(block_text).strip()[:300]})
        times, block_text = None, []

    for line in str(text or "").splitlines():
        m = time_re.search(line)
        if m:
            _flush()
            g = [int(x) for x in m.groups()]
            times = (g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                     g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000)
            continue
        if not line.strip() or re.fullmatch(r"\d+", line.strip()) \
                or line.strip().upper() in ("WEBVTT",):
            if not line.strip():
                _flush()
            continue
        if times:
            block_text.append(line.strip())
    _flush()
    return cues


# ---- 本地转写（faster-whisper；无字幕时兜底）----

def transcribe_audio(video_path: str) -> list[dict]:
    """抽音频 → faster-whisper（small/int8，CPU）→ [{start,end,text}]。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("未安装 faster-whisper，无法本地转写；请附带字幕文件") from e
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(video_path, vad_filter=True)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments if s.text.strip()]


# ---- 确定性动作候选 ----

def detect_exercise_candidates(transcript: list[dict],
                               max_candidates: int = 8) -> list[dict]:
    """转写句 → 动作库匹配。规则（§7.4 ②-③）：

    取句中包含的最长别名作为候选（match=alias）——不复用打卡归一的
    变体否决（"与肩同宽"的"宽"会误杀自然教学语句）；候选本就需要
    用户确认，宽松召回+人工确认比漏报更符合"错误识别允许纠正"。
    每个动作取最早出现的一句；句子太短不猜。
    """
    from .exercises import library
    candidates: dict[str, dict] = {}
    for cue in transcript:
        text = str(cue.get("text") or "").strip()
        if len(text) < 6:
            continue
        subs = [(len(a), aid) for a, aid in library._alias.items() if a in text]
        if not subs:
            continue
        _, ex_id = max(subs, key=lambda x: (x[0], x[1]))
        official = library.get(ex_id)["name"]
        entry = {
            "exercise_id": ex_id, "name": official, "match": "alias",
            "sentence": text, "start": float(cue.get("start") or 0),
            "end": float(cue.get("end") or 0), "status": "pending",
        }
        existing = candidates.get(ex_id)
        if existing is None or entry["start"] < existing["start"]:
            candidates[ex_id] = entry
    ranked = sorted(candidates.values(), key=lambda c: c["start"])
    return ranked[:max_candidates]


# ---- 封面帧 / 演示片段（ffmpeg；失败返回 None，不阻塞关联）----

def _ffmpeg(args: list[str]) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        return subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
            check=True, capture_output=True, timeout=120).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def make_cover(video_path: str, ts: float, out_path: str) -> str | None:
    ok = _ffmpeg(["-ss", f"{max(0.0, ts):.2f}", "-i", video_path,
                  "-frames:v", "1", "-q:v", "3", out_path])
    return out_path if ok and Path(out_path).exists() else None


def make_clip(video_path: str, start: float, end: float, out_path: str,
              max_seconds: float = 20.0) -> str | None:
    dur = min(max_seconds, max(1.0, end - start))
    begin = max(0.0, start - 3.0)
    ok = _ffmpeg(["-ss", f"{begin:.2f}", "-i", video_path,
                  "-t", f"{dur:.2f}", "-c", "copy", out_path])
    return out_path if ok and Path(out_path).exists() else None


# ---- 处理一个视频资产（worker 内执行）----

def process_asset(db, asset_id: int, video_path: str, subtitle_path: str | None) -> None:
    """字幕优先；否则本地转写。完成→候选；失败→如实记录 error。"""
    transcript: list[dict] = []
    error: str | None = None
    if subtitle_path:
        try:
            transcript = parse_srt(Path(subtitle_path).read_text(encoding="utf-8"))
            if not transcript:
                error = "字幕文件里没有可识别的台词"
        except OSError as e:
            error = f"字幕读取失败：{e}"
    else:
        try:
            transcript = transcribe_audio(video_path)
        except Exception as e:  # noqa: BLE001 转写失败要如实落状态
            error = f"本地转写失败：{e}"
    if error:
        db.update_media_asset(asset_id, status="failed", error=error)
        return
    candidates = detect_exercise_candidates(transcript)
    db.update_media_asset(asset_id, status="ready",
                          transcript=transcript, candidates=candidates)
