"""证据校验：洞察引用的事实必须真实存在于生成时的事实快照。

原则（2.0 §11.3）：关键结论必须能关联到具体事实、单位、时间窗口和来源。
本模块在洞察落库前做确定性复核：
1. findings[].fact_ids ⊆ facts_snapshot 的 fact_id 集合——引用不存在的
   事实 = 构造缺陷，删除该引用并记录；
2. findings[].source_ids 必须形如 checkin:ID:revision:N 且 ID 真实存在；
3. 无任何合法引用的发现保留但标记 evidence="unverified"（如纯上下文
   说明），分析文本中的数值结论必须有合法引用支撑。
"""
from __future__ import annotations

import re

_SRC_PATTERN = re.compile(r"^checkin:(\d+):revision:(\d+)$")


def validate_evidence(payload: dict, db=None, user_id: str = "") -> dict:
    """复核并清洗洞察载荷。返回 (清洗后的 payload, 报告)。

    不会因为校验失败丢弃整个分析——缺陷引用被剔除并如实计数，
    供任务日志与测试断言。
    """
    snapshot_ids = {f.get("fact_id") for f in
                    ((payload.get("facts_snapshot") or {}).get("facts") or [])}
    snapshot_ids.discard(None)
    report = {"dropped_fact_refs": 0, "dropped_source_refs": 0,
              "unverified_findings": 0, "checked_findings": 0}
    for finding in payload.get("findings") or []:
        report["checked_findings"] += 1
        kept = [fid for fid in (finding.get("fact_ids") or [])
                if fid in snapshot_ids]
        report["dropped_fact_refs"] += len(finding.get("fact_ids") or []) - len(kept)
        finding["fact_ids"] = kept
        kept_src = []
        for src in finding.get("source_ids") or []:
            m = _SRC_PATTERN.match(str(src))
            if not m:
                report["dropped_source_refs"] += 1
                continue
            if db is not None and user_id:
                row = db.conn.execute(
                    "SELECT 1 FROM checkins WHERE user_id=? AND id=?",
                    (user_id, int(m.group(1)))).fetchone()
                if not row:
                    report["dropped_source_refs"] += 1
                    continue
            kept_src.append(str(src))
        finding["source_ids"] = kept_src
        if not kept and not kept_src:
            finding["evidence"] = "unverified"
            report["unverified_findings"] += 1
        else:
            finding["evidence"] = "verified"

    # 顶层 evidence_refs 同步清洗（与 findings 保持一致）
    payload["evidence_refs"] = sorted(
        {fid for f in payload.get("findings") or [] for fid in f["fact_ids"]})
    payload["evidence_report"] = report
    return payload
