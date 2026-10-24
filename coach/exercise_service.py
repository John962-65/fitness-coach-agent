"""M5.2 P0-1：统一动作服务——系统内置(exercises/*.yaml) + 用户自定义(SQLite)。

两种来源同一套数据结构与接口，但访问范围明确隔离：
- 内置动作所有用户可见（scope=builtin）；
- 用户自定义仅本人可见（scope=user），绝不写入 exercises/ 目录
  （部署只读、更新丢数据、跨用户泄漏三类问题从根上消除）。

M6.2：动作教学文档——exercises/*.yaml 的 knowledge_refs 指向 knowledge/ 下
的人工整理教学 md；此处解析 frontmatter（来源/整理时间）与正文，供动作详情
页"教学"标签渲染。内容与展示分离：本模块只读文件与元数据，不做任何改写。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .exercises import library

KNOWLEDGE_DIR = (Path(__file__).resolve().parent.parent / "knowledge").resolve()


def _norm(text: str) -> str:
    return "".join(str(text).split()).lower()


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """拆出 `---\\n yaml \\n---` 头与正文；无头时返回空元数据。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4:].lstrip("\n")


def teaching_for(ex_id: str) -> list[dict]:
    """动作关联的教学文档（含来源元数据）。

    安全校验：ref 必须解析到 knowledge/ 目录内且以 .md 结尾，
    目录穿越/错配/文件缺失一律跳过——宁可没有内容也不给错内容。
    """
    ex = library.get(ex_id)
    refs = (ex.get("knowledge_refs") or []) if ex else []
    out: list[dict] = []
    for rel in refs:
        if not isinstance(rel, str) or not rel.endswith(".md"):
            continue
        p = (KNOWLEDGE_DIR / rel).resolve()
        if not p.is_relative_to(KNOWLEDGE_DIR) or not p.is_file():
            continue
        meta, body = _split_frontmatter(p.read_text(encoding="utf-8"))
        source = meta.get("source") or []
        out.append({
            "path": rel,
            "topic": meta.get("topic") or p.stem,
            "source": source if isinstance(source, list) else [str(source)],
            "provenance": str(meta.get("provenance") or ""),
            "updated": str(meta.get("updated") or ""),
            "markdown": body,
        })
    return out


def list_exercises(db, user_id: str | None) -> list[dict]:
    """内置 +（有 user_id 时）该用户自定义；scope 标注来源。"""
    out = []
    for doc in library.all():
        d = dict(doc)
        d["scope"] = "builtin"
        out.append(d)
    if user_id:
        out.extend(db.get_custom_exercises(user_id))
    return out


def get_exercise(db, user_id: str | None, ex_id: str) -> dict | None:
    ex = library.get(ex_id)
    if ex:
        return {**ex, "scope": "builtin"}
    if user_id:
        custom = db.get_custom_exercise(user_id, ex_id)
        if custom:
            return custom
    return None


def resolve(db, user_id: str | None, text: str) -> tuple[str | None, str, str]:
    """用户叫法 → (ex_id, 官方名, 匹配方式)。先内置精确，后本人自定义精确别名。"""
    t = _norm(text)
    if not t:
        return None, "", ""
    ex = library.get(t)
    if ex:
        return t, ex["name"], "builtin_exact"
    ex_id, official, via = library.normalize(t)
    if ex_id and via == "exact":
        return ex_id, official, "builtin_exact"
    if user_id:
        for doc in db.get_custom_exercises(user_id):
            if t == _norm(doc.get("name") or "") or t in {
                    _norm(a) for a in (doc.get("aliases") or [])}:
                return doc["id"], doc["name"], "custom_exact"
    return None, "", ""


def alias_conflicts(db, user_id: str, name: str,
                    aliases: list[str]) -> list[str]:
    """自定义动作与内置库/本人已有自定义的名称冲突（同 user 同 id 由 UNIQUE 兜底）。"""
    wanted = {_norm(x) for x in [name, *aliases] if _norm(x)}
    hits = []
    for a, _aid in library._alias.items():  # noqa: SLF001 只读索引
        if a in wanted:
            hits.append(a)
    for doc in db.get_custom_exercises(user_id):
        for a in [doc.get("name"), *(doc.get("aliases") or [])]:
            if _norm(a) in wanted:
                hits.append(str(a))
    return sorted(set(hits))
