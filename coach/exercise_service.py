"""M5.2 P0-1：统一动作服务——系统内置(exercises/*.yaml) + 用户自定义(SQLite)。

两种来源同一套数据结构与接口，但访问范围明确隔离：
- 内置动作所有用户可见（scope=builtin）；
- 用户自定义仅本人可见（scope=user），绝不写入 exercises/ 目录
  （部署只读、更新丢数据、跨用户泄漏三类问题从根上消除）。
"""
from __future__ import annotations

from .exercises import library


def _norm(text: str) -> str:
    return "".join(str(text).split()).lower()


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
