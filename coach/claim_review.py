"""素材的双层审核契约：来源与适用性分别签核，正文变化使签核失效。"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone

REVIEW_STAGES = ("source", "applicability")
_CONTENT_FIELDS = ("claim", "blogger", "speaker", "video", "ts", "type", "exercises",
                   "applies_to", "evidence", "provenance")


def content_fingerprint(claim: dict) -> str:
    payload = {key: claim.get(key) for key in _CONTENT_FIELDS}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def source_issues(claim: dict) -> list[str]:
    problems = []
    if not re.fullmatch(r"BV[0-9A-Za-z]{10}", str(claim.get("video", ""))):
        problems.append("缺少可核对的 B 站视频 ID")
    ts = claim.get("ts")
    if not (isinstance(ts, list) and len(ts) == 2
            and all(isinstance(t, (int, float)) and not isinstance(t, bool)
                    and math.isfinite(t) for t in ts) and 0 <= ts[0] < ts[1]):
        problems.append("缺少有效的起止时间")
    speaker = str(claim.get("speaker") or "").strip()
    if not speaker or any(s in speaker for s in ("待确认", "未知", "不确定", "语境归因")):
        problems.append("发言者尚未确认")
    if claim.get("provenance") not in ("transcript", "article"):
        problems.append("不是已定位的一手来源")
    if not str(claim.get("claim") or "").strip():
        problems.append("观点正文为空")
    return problems


def review_issues(claim: dict) -> list[str]:
    problems = source_issues(claim)
    fingerprint = content_fingerprint(claim)
    reviews = claim.get("reviews") or {}
    for stage in REVIEW_STAGES:
        entry = reviews.get(stage) or {}
        if not (entry.get("status") == "approved" and entry.get("by")
                and entry.get("note") and entry.get("at")):
            problems.append(f"{stage} 审核未完成")
        elif entry.get("fingerprint") != fingerprint:
            problems.append(f"{stage} 审核已因内容变化失效")
    return problems


def is_publishable(claim: dict) -> bool:
    return claim.get("status") == "approved" and not review_issues(claim)


def record_review(claim: dict, stage: str, reviewer: str, note: str) -> None:
    """仅供显式人工审核操作调用；不把自动预审记为人工批准。"""
    if stage not in REVIEW_STAGES or not reviewer.strip() or not note.strip():
        raise ValueError("必须指定 source/applicability、审核者及审核依据")
    issues = source_issues(claim)
    if issues:
        raise ValueError("；".join(issues))
    claim.setdefault("reviews", {})[stage] = {
        "status": "approved", "by": reviewer.strip(), "note": note.strip(),
        "at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": content_fingerprint(claim),
    }
    claim["status"] = "approved" if not review_issues(claim) else "draft"


def invalidate_review(claim: dict) -> None:
    """保留旧签核供追溯，但正文修改后不得继续发布。"""
    claim["status"] = "draft"
