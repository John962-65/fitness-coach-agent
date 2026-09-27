"""观点条目提炼流水线（设计书 19.2 ③ + 21.2 ③a/③b）

读视频文字稿 → LLM 提炼观点条目（claim）→ 反幻觉校验 → 写 claims/<博主>.yaml（draft）。

用法：
  python3 tools/distill.py sources/transcripts/谭成义/BV1xx.json --blogger 谭成义
  python3 tools/distill.py <transcript.json> --blogger 谭成义 --dry-run   # 只打印不落盘

依赖一手文字稿（sources/transcripts/，本地私有）。没有文字稿时本脚本无法运行——
试点当前阻塞在"拿字幕"这步（见 sources/manifest/谭成义.yaml 头部说明）。

claim schema 见 claims/tcy.yaml。反幻觉校验（19.2 ③末）：单独一次 LLM 调用判断
"该时间段原文是否支持这条 claim"，判为不支持的标红，审核时重点看。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")  # 同 eval/runner.py：工具入口自己加载 key

from coach.exercises import library as exercise_lib  # noqa: E402
from coach.llm import LLMClient  # noqa: E402

CLAIM_TYPES = {"principle", "method", "cue", "error", "self_check",
               "nutrition", "anecdote"}
EVIDENCE_TYPES = {"blogger_experience", "cites_research", "consensus"}
BLOGGER_FILE = {"凯圣王": "ksw", "谭成义": "tcy", "陈石": "cs"}


# ---------- 确定性部分（可单测） ----------

def load_transcript(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("video", "blogger", "segments"):
        if key not in data:
            raise ValueError(f"文字稿缺字段 {key}: {path}")
    if not isinstance(data["segments"], list):
        raise ValueError(f"segments 必须是列表: {path}")
    return data


def segment_text_at(segments: list[dict], start: float, end: float) -> str:
    """取出 [start, end] 时间窗内的原文（反幻觉校验的证据上下文）"""
    parts = []
    for seg in segments:
        s, e = seg.get("start", 0), seg.get("end", 0)
        # 时间窗有重叠即纳入
        if s < end and e > start:
            parts.append(seg.get("text", ""))
    return " ".join(parts).strip()


def validate_claim(claim: dict) -> list[str]:
    """校验单条 claim 的 schema。返回错误列表（空=合法）。"""
    errors = []
    if not claim.get("claim"):
        errors.append("缺 claim 正文")
    ts = claim.get("ts")
    if not (isinstance(ts, list) and len(ts) == 2
            and all(isinstance(x, (int, float)) for x in ts)):
        errors.append("ts 必须是 [start, end] 数值对（无时间戳的条目应丢弃）")
    if claim.get("type") not in CLAIM_TYPES:
        errors.append(f"type 非法: {claim.get('type')!r}")
    if claim.get("evidence") not in EVIDENCE_TYPES:
        errors.append(f"evidence 非法: {claim.get('evidence')!r}")
    for ex in claim.get("exercises") or []:
        if not exercise_lib.get(ex):
            errors.append(f"exercises 引用了动作库不存在的 id: {ex!r}")
    return errors


def claims_to_yaml(claims: list[dict]) -> str:
    return yaml.safe_dump(claims, allow_unicode=True, sort_keys=False)


# ---------- LLM 部分 ----------

EXTRACT_PROMPT = """你是健身内容整理助手。下面是一段博主视频的文字稿（带时间戳）。
请提炼出其中"可引用的观点条目"（教学要点/原则/方法/常见错误/自检/营养/个人经验）。

要求：
- 每条必须带时间戳 ts=[start, end]（取自文字稿），没有依据的不要编
- exercises 用给定的动作库 id（从下方列表里选，没有就留空）
- type 取值：principle/method/cue/error/self_check/nutrition/anecdote
- evidence 取值：blogger_experience/cites_research/consensus
- 只输出 JSON 数组，不要解释

动作库 id 列表：{exercise_ids}

文字稿（博主：{blogger}，视频：{video}）：
{transcript}

输出 JSON 数组，每个元素形如：
{{"claim": "...", "ts": [192.0, 201.5], "type": "cue",
  "exercises": ["barbell_back_squat"], "evidence": "blogger_experience"}}
"""

SUPPORT_PROMPT = """判断"原文片段"是否支持"待验证观点"。只回答"支持"或"不支持"，不要解释。

原文片段：{segment}

待验证观点：{claim}
"""


def extract_claims(transcript: dict, llm: LLMClient) -> list[dict]:
    seg_text = "\n".join(
        f"[{s.get('start')}-{s.get('end')}] {s.get('text','')}"
        for s in transcript["segments"])
    prompt = EXTRACT_PROMPT.format(
        exercise_ids=", ".join(sorted(exercise_lib._by_id)),
        blogger=transcript["blogger"], video=transcript["video"],
        transcript=seg_text)
    result = llm.chat([{"role": "user", "content": prompt}], temperature=0.2)
    return _parse_json_array(result["content"])


def supports_claim(claim_text: str, segment_text: str, llm: LLMClient) -> bool:
    if not segment_text:
        return False  # 没有对应原文 → 视为不支持（标红待审）
    prompt = SUPPORT_PROMPT.format(segment=segment_text, claim=claim_text)
    result = llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
    return "支持" in result["content"] and "不支持" not in result["content"]


def _parse_json_array(text: str) -> list[dict]:
    text = text.strip()
    # 容忍 ```json 包裹
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(text[start:end + 1])
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


# ---------- 编排 ----------

def distill(transcript_path: Path, blogger: str, llm: LLMClient,
            dry_run: bool = False, start: float | None = None,
            end: float | None = None, tag: str = "") -> dict:
    transcript = load_transcript(transcript_path)
    segments = transcript["segments"]
    if start is not None or end is not None:
        s0 = start if start is not None else 0.0
        e0 = end if end is not None else float("inf")
        segments = [s for s in segments
                    if s.get("end", 0) > s0 and s.get("start", 0) < e0]
    work = dict(transcript, segments=segments)
    raw = extract_claims(work, llm)
    claims, flagged = [], []
    for i, c in enumerate(raw):
        errors = validate_claim(c)
        if errors:
            flagged.append({"claim": c.get("claim", ""), "reason": "schema", "errors": errors})
            continue
        seg = segment_text_at(segments, c["ts"][0], c["ts"][1])
        supported = supports_claim(c["claim"], seg, llm)
        entry = {
            "id": (f"{BLOGGER_FILE.get(blogger, 'x')}-{transcript['video']}"
                   f"-{i + 1:04d}" + (f"-{tag}" if tag else "")),
            "blogger": blogger,
            "video": transcript["video"],
            "ts": c["ts"],
            "claim": c["claim"],
            "type": c["type"],
            "exercises": c.get("exercises") or [],
            "applies_to": c.get("applies_to") or {"level": [], "goal": [], "condition": []},
            "evidence": c["evidence"],
            "provenance": "transcript",
            "status": "draft",
            "anti_hallucination": "pass" if supported else "FLAGGED",
            "reviewed": {"by": "", "date": "", "against": ""},
        }
        claims.append(entry)
        if not supported:
            flagged.append({"claim": c["claim"], "reason": "anti_hallucination",
                            "segment": seg[:80]})

    out_path = ROOT / "claims" / f"{BLOGGER_FILE.get(blogger, blogger)}.yaml"
    if not dry_run and claims:
        existing = []
        if out_path.exists():
            loaded = yaml.safe_load(out_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded
        out_path.write_text(claims_to_yaml(existing + claims), encoding="utf-8")

    return {"extracted": len(raw), "valid": len(claims),
            "flagged": flagged, "out": str(out_path) if not dry_run else "(dry-run)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript", help="文字稿 JSON 路径")
    ap.add_argument("--blogger", required=True, choices=list(BLOGGER_FILE))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", type=float, default=None,
                    help="只提炼 [start,end) 时间窗（秒，长视频分段用）")
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--tag", default="",
                    help="窗口标记，写入 id 后缀避免多窗口冲突")
    args = ap.parse_args()

    llm = LLMClient()
    if llm.fake:
        print("⚠️ FAKE_LLM 模式：提炼结果为占位，仅验证流程，不能入库。")
    report = distill(Path(args.transcript), args.blogger, llm, args.dry_run,
                     start=args.start, end=args.end, tag=args.tag)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
