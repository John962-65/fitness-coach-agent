"""M3 统一知识检索服务（DESIGN_2.0 §6.5，任务 1–3）。

一个入口检索四类知识源，每条命中带来源、可信状态与适用信息：
- knowledge_md：knowledge/*.md（provenance 来自 front-matter）
- blogger_claims：claims/*.yaml 博主观点（approved 可引用；draft 只报数量）
- coach_cards：已审核教练卡（运行时可用才命中；私有卡库缺失时如实跳过）
- user_imports：用户导入并审核通过的观点（pending/quarantined 不进结果）

不做向量检索（§10.3：向量不是首个版本的阻塞依赖）；关键词命中 +
元数据（状态/来源）过滤即本轮范围。高风险隔离内容永远不会出现在结果里。
"""
from __future__ import annotations

import re
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).resolve().parent.parent / "knowledge"


def _keywords(query: str) -> list[str]:
    """查询词切分：CJK 2-gram + 西文词，去停用词。"""
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", str(query or ""))
    words = [w for w in text.split() if len(w) >= 2]
    grams = []
    for w in words:
        if re.fullmatch(r"[\u4e00-\u9fff]+", w):
            grams += [w[i:i + 2] for i in range(len(w) - 1)] or [w]
        else:
            grams.append(w.lower())
    return list(dict.fromkeys(grams))[:8]


def _iter_md_files():
    if not KNOWLEDGE_ROOT.exists():
        return
    for path in sorted(KNOWLEDGE_ROOT.rglob("*.md")):
        if path.name in ("index.md", "CHANGELOG.md"):
            continue
        yield path


def _front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def _search_md(keywords: list[str], limit: int) -> list[dict]:
    matches = []
    for path in _iter_md_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        matched = [k for k in keywords if k in text]
        if not matched:
            continue
        snippet = ""
        for line in text.splitlines():
            if any(k in line for k in keywords) and len(line.strip()) > 8:
                snippet = line.strip()[:120]
                break
        meta = _front_matter(text)
        matches.append((len(matched), {
            "engine": "knowledge_md",
            "ref": str(path.relative_to(KNOWLEDGE_ROOT)),
            "title": meta.get("title") or path.stem,
            "snippet": snippet or text.strip()[:100],
            "provenance": meta.get("provenance", "general"),
            "status": "published",
        }))
    # 命中关键词多的排前（多主题文件不淹没精确命中）
    matches.sort(key=lambda x: -x[0])
    return [hit for _, hit in matches[:limit]]


def _search_blogger_claims(keywords: list[str], limit: int) -> tuple[list[dict], int]:
    """approved 命中给内容；draft 命中只计数（审前不得给出具体说法）。"""
    from .claims import claim_store
    from .claim_review import is_publishable
    hits, draft_count = [], 0
    for cid, claim in claim_store._by_id.items():  # noqa: SLF001 共享只读索引
        text = str(claim.get("claim") or "")
        if not any(k in text or k in cid for k in keywords):
            continue
        if is_publishable(claim):
            hits.append({
                "engine": "blogger_claims",
                "ref": cid,
                "title": f"{claim.get('speaker') or '发言者待确认'}·{text[:40]}",
                "snippet": text[:140],
                "provenance": "blogger_video",
                "status": "approved",
            })
            if len(hits) >= limit:
                break
        else:
            draft_count += 1
    return hits, draft_count


def _search_cards(keywords: list[str], limit: int) -> list[dict]:
    try:
        from .cards import approved_cards, runtime_usable
    except Exception:
        return []
    hits = []
    try:
        cards = approved_cards()
    except Exception:
        return []
    for card_id, card in cards.items():
        body = str(card.get("summary") or "") + str(card.get("title") or "")
        points = card.get("points") or []
        if isinstance(points, list):
            body += "".join(str(p.get("point") or "") for p in points
                            if isinstance(p, dict))
        if not any(k in body for k in keywords):
            continue
        if not runtime_usable(card):
            continue
        hits.append({
            "engine": "coach_cards",
            "ref": card_id,
            "title": str(card.get("title") or card_id),
            "snippet": str(card.get("summary") or "")[:140],
            "provenance": "reviewed_card",
            "status": "approved",
        })
        if len(hits) >= limit:
            break
    return hits


def search(db, user_id: str | None, query: str, limit_per_engine: int = 5) -> dict:
    """统一检索入口。quarantined/pending 永不进结果（§6.3 审核边界）。"""
    keywords = _keywords(query)
    if not keywords:
        return {"keywords": [], "engines": {}}
    md_hits = _search_md(keywords, limit_per_engine)
    claim_hits, draft_count = _search_blogger_claims(keywords, limit_per_engine)
    card_hits = _search_cards(keywords, limit_per_engine)
    user_hits = db.search_user_knowledge(user_id, keywords, limit_per_engine) \
        if user_id else []
    engines = {
        "knowledge_md": {"hits": md_hits},
        "blogger_claims": {"hits": claim_hits, "draft_matches": draft_count,
                           "note": "另有草稿素材命中，审核通过前不展示内容"},
        "coach_cards": {"hits": card_hits},
        "user_imports": {"hits": [
            {"engine": "user_imports", "ref": f"claim:{h['id']}",
             "title": h["source_title"], "snippet": h["content"][:140],
             "provenance": "user_import_approved", "status": "approved"}
            for h in user_hits]},
    }
    return {"keywords": keywords, "engines": engines}
