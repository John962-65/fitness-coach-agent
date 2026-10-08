"""已审核观点条目（claims/）的运行时读取（设计书 19.1/19.2/21.2）

定位：把"博主在视频里怎么讲的"接到教练的回答里——
- 动作 YAML 的 setup/cues/errors/self_check/tactile_hack/cautions 字段存的是
  观点条目 id，本模块负责把 id 解析成可读的要点文本（带出处）；
- 审核纪律：只有 status=approved 的条目可被引用；draft 条目只报数量、
  不给内容（审完之前，教练不得把具体说法安在博主名下）。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .claim_review import is_publishable

CLAIMS_ROOT = Path(__file__).resolve().parent.parent / "claims"

# 动作 YAML 里存放观点条目 id 的教学字段（21.2 ③a 的映射关系）
COACHING_FIELDS = ("setup", "cues", "errors", "self_check", "tactile_hack",
                   "cautions", "programming")
FIELD_LABEL = {
    "setup": "准备",
    "cues": "发力提示",
    "errors": "常见错误",
    "self_check": "自检方法",
    "tactile_hack": "无教练时的替代",
    "cautions": "禁忌与劝阻",
    "programming": "组次参考（以计划模板为准）",
}


class ClaimStore:
    def __init__(self, root: Path = CLAIMS_ROOT) -> None:
        self.root = root
        self._by_id: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        for path in sorted(self.root.glob("*.yaml")):
            if path.name == "conflicts.yaml":
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
            if not isinstance(data, list):
                continue
            for c in data:
                if isinstance(c, dict) and c.get("id"):
                    if c["id"] in self._by_id:
                        raise ValueError(f"重复的观点 ID：{c['id']}")
                    self._by_id[c["id"]] = c

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, claim_id: str) -> dict | None:
        return self._by_id.get(claim_id)

    @staticmethod
    def source_link(claim: dict) -> str:
        """出处：博主 + 视频 + 起点秒数（可点回原文片段，设计书 18.4）"""
        video = claim.get("video", "")
        ts = claim.get("ts") or []
        start = int(ts[0]) if ts else 0
        who = claim.get("speaker") or "发言者待确认"
        return f"{who} {video}@{start:>4}s · bilibili.com/video/{video}?t={start}"

    def format_coaching(self, ex_yaml: dict) -> str:
        """把一个动作 YAML 的教学字段渲染成给 LLM 的要点文本。

        每条 approved 条目一行，带出处；draft 只统计数量。
        字段里的值若不是已知条目 id（人工手写的文本），原样展示。
        """
        lines: list[str] = []
        draft_count = 0
        for field in COACHING_FIELDS:
            refs = ex_yaml.get(field) or []
            if not refs:
                continue
            items = []
            for ref in refs:
                claim = self.get(str(ref))
                if claim is None:
                    if str(ref).startswith(("ksw-", "tcy-", "cs-")):
                        draft_count += 1
                    else:
                        items.append(f"· 通用教学提示（非博主引用）：{ref}")
                elif is_publishable(claim):
                    items.append(f"· {claim['claim']}（出处：{self.source_link(claim)}）")
                else:
                    draft_count += 1
            if items:
                lines.append(f"{FIELD_LABEL.get(field, field)}：")
                lines.extend(items)
        if draft_count:
            lines.append(f"（另有 {draft_count} 条博主素材待人工审核，"
                         "审核通过前不得引用、不得点名博主）")
        return "\n".join(lines)


# 模块级共享实例（与 exercises.library 一致；加载失败要在测试里立刻暴露）
claim_store = ClaimStore()
