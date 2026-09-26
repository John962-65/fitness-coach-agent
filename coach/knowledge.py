"""知识库加载器：L1 常驻原则层 / L2 索引层 / L3 按需全文

- L1：00_principles 全文摘要，常驻 system prompt（教练的"世界观"）
- L2：全部知识文件的索引（topic + triggers），常驻 system prompt
- L3：LLM 通过 load_knowledge 工具按需加载全文
"""
from __future__ import annotations

import re
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parent.parent / "knowledge"


def _parse_front_matter(text: str) -> dict[str, str]:
    """极简 front-matter 解析（避免引入 pyyaml 依赖）"""
    meta: dict[str, str] = {}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end == -1:
        return meta
    for line in text[3:end].strip().splitlines():
        m = re.match(r"^(\w+):\s*(.*)$", line.strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


class KnowledgeBase:
    def __init__(self, root: Path = KNOWLEDGE_ROOT) -> None:
        self.root = root
        self._files: dict[str, dict] = {}  # 相对路径 -> {meta, 摘要}
        self._scan()

    def _scan(self) -> None:
        for path in sorted(self.root.rglob("*.md")):
            if path.name in ("CHANGELOG.md", "index.md"):
                continue
            rel = path.relative_to(self.root).as_posix()
            text = path.read_text(encoding="utf-8")
            meta = _parse_front_matter(text)
            self._files[rel] = {"meta": meta, "text": text}

    @property
    def l1_principles(self) -> str:
        """L1：原则层全文（约几千字，常驻）"""
        parts = []
        for rel, item in self._files.items():
            if rel.startswith("00_principles/"):
                parts.append(item["text"])
        return "\n\n---\n\n".join(parts)

    @property
    def l2_index(self) -> str:
        """L2：知识索引清单（标题 + 触发词，常驻）"""
        lines = []
        for rel, item in self._files.items():
            topic = item["meta"].get("topic", rel)
            triggers = item["meta"].get("triggers", "")
            lines.append(f"- `{rel}`：{topic}（触发词：{triggers}）")
        return "\n".join(lines)

    def load(self, rel_path: str) -> str:
        """L3：按需加载全文"""
        if not rel_path or not rel_path.strip():
            return "错误：未提供知识文件路径。请从索引中选择一个文件加载。"
        item = self._files.get(rel_path)
        if item is None:
            # 模糊匹配：允许 LLM 只给文件名
            for rel, it in self._files.items():
                if rel.endswith(rel_path) or rel_path in rel:
                    return it["text"]
            return f"错误：知识文件不存在：{rel_path}"
        return item["text"]


# LLM 工具定义（OpenAI function calling 格式）
LOAD_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "load_knowledge",
        "description": (
            "按需加载知识库文件全文。先查看系统提示中的知识索引，"
            "当用户问题需要专业知识支撑时调用此工具加载对应文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "知识文件的相对路径，如 30_nutrition/slow_cut_protocol.md",
                }
            },
            "required": ["path"],
        },
    },
}
