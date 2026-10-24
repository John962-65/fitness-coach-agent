"""M3 知识导入流水线（DESIGN_2.0 §6.3，任务 4/8/9）。

导入 → 分段（KnowledgeChunk）→ 观点提取（KnowledgeClaim）→ 重复/冲突检测
→ 待审核 → 用户审核。三个状态明确分离（§6.3）：
- 资料已保存（source.status=saved）≠ 内容提取通过 ≠ 专业知识审核通过。

本轮提取为**确定性规则草稿**（句子切分 + 启发式分类），不调真实 LLM：
提取结果全部 pending_review，以用户逐条审核为准；高风险内容（药物/极端
手段等关键词）直接 quarantined，审核端点拒绝放行——未经审核的高风险知识
不能成为训练处方依据（M3 验收红线）。
"""
from __future__ import annotations

import difflib
import hashlib
import re

# 高风险关键词：命中即隔离（与出卡线"从严剔除"口径一致，可扩展）
RISK_KEYWORDS = (
    "类固醇", "激素", "禁药", "兴奋剂", "利尿剂", "脱水剂", "克仑特罗",
    "瘦肉精", "极端断食", "断食三天", "只喝水", "催吐", "泻药",
    "处方药", "注射", "胰岛素",
)

# 观点句启发式：含主张/建议/禁止/数据信号之一的句子才算候选
_CLAIM_SIGNAL = re.compile(
    r"建议|应该|应当|必须|不要|别|切忌|最好|可以|能够|研究|表明|实验|"
    r"数据|显示|证明|原因|因为|关键是|核心是|原则|每公斤|分钟|组|次|%"
)

_TYPE_KEYWORDS = {
    "nutrition": ("蛋白", "热量", "卡路里", "碳水", "脂肪", "饮食", "进食",
                  "餐", "补剂", "肌酸", "营养", "水"),
    "cue": ("发力", "感觉", "肌肉收缩", "顶峰", "控制", "节奏", "呼吸"),
    "method": ("组数", "次数", "训练", "计划", "分化", "周期", "容量", "强度",
               "休息", "动作"),
    "principle": ("原则", "机制", "原理", "适应", "恢复", "渐进"),
}


def content_hash(content: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", "", content).encode("utf-8")).hexdigest()[:32]


def extract_pdf_text(data: bytes) -> str:
    """PDF 文本提取（pymupdf）。失败抛 ValueError，由调用方如实返回。"""
    try:
        import fitz  # pymupdf
    except ImportError as e:
        raise ValueError("服务器未安装 pymupdf，暂不支持 PDF 导入") from e
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except Exception as e:  # noqa: BLE001 解析失败统一如实上报
        raise ValueError(f"PDF 解析失败：{e}") from e


def split_chunks(content: str, max_chunks: int = 60) -> list[str]:
    """按空行切分段落（独立标题行并入下一段）；超长段落按句号再切。"""
    raw = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    paras: list[str] = []
    for p in raw:
        if re.fullmatch(r"#{1,3}\s.{0,28}", p) and paras is not None:
            paras.append(p)  # 标题占位,稍后并入
            continue
        if paras and re.fullmatch(r"#{1,3}\s.{0,28}", paras[-1]):
            paras[-1] = paras[-1] + "\n" + p
        else:
            paras.append(p)
    chunks: list[str] = []
    for para in paras:
        if len(para) > 1200:
            sentences = re.split(r"(?<=[。！？])", para)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) > 1200 and buf:
                    chunks.append(buf)
                    buf = s
                else:
                    buf += s
            if buf:
                chunks.append(buf)
        else:
            chunks.append(para)
    return chunks[:max_chunks]


def classify_claim(sentence: str) -> str:
    for ctype, words in _TYPE_KEYWORDS.items():
        if any(w in sentence for w in words):
            return ctype
    return "other"


def extract_claim_drafts(content: str, max_claims: int = 20) -> list[dict]:
    """规则提取观点草稿：句子含主张信号 → 候选（全部待用户审核）。"""
    sentences = [s.strip() for s in re.split(r"[。！？\n]+", content) if s.strip()]
    drafts = []
    seen = set()
    for s in sentences:
        risk = next((kw for kw in RISK_KEYWORDS if kw in s), None)
        # 风险句优先拦截（隔离），不要求"像建议句"；普通句需通过信号过滤
        if risk:
            if 6 <= len(s) <= 300 and s[:40] not in seen:
                seen.add(s[:40])
                drafts.append({"content": s, "claim_type": classify_claim(s),
                               "risk_flag": risk})
            continue
        if len(s) < 8 or len(s) > 300 or not _CLAIM_SIGNAL.search(s):
            continue
        if s[:40] in seen:
            continue
        seen.add(s[:40])
        drafts.append({"content": s, "claim_type": classify_claim(s),
                       "risk_flag": None})
        if len(drafts) >= max_claims:
            break
    return drafts


def _tokenize(text: str) -> set[str]:
    """CJK 连续段拆二元 shingle + 西文词：对标点/分段差异鲁棒。"""
    tokens: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.update(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    tokens.update(w.lower() for w in re.findall(r"[A-Za-z]{3,}", text))
    return tokens


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a[:160], b[:160]).ratio()


def detect_duplicate_and_conflict(draft: str, existing: list[dict],
                                  dup_threshold: float = 0.72,
                                  conflict_threshold: float = 0.5,
                                  max_compare: int = 200) -> tuple[dict | None, dict | None]:
    """与既有观点比对：高相似=疑似重复；中等相似且关键词域不同=疑似冲突。

    existing: [{ref, text, domain}]；先按 token 重叠预筛（≥2 个共享词），
    相似度只对预筛后的候选计算，避免全库 difflib。
    """
    tokens = _tokenize(draft)
    if not tokens:
        return None, None
    candidates = []
    for item in existing[:max_compare]:
        overlap = tokens & _tokenize(item["text"])
        if len(overlap) >= 2:
            candidates.append((item, len(overlap)))
    duplicate = conflict = None
    for item, _overlap in sorted(candidates, key=lambda x: -x[1])[:30]:
        ratio = _similarity(draft, item["text"])
        if ratio >= dup_threshold:
            duplicate = {"ref": item["ref"], "similarity": round(ratio, 2),
                         "text": item["text"][:120]}
            break  # 找到最相似的重复即停
        if conflict_threshold <= ratio < dup_threshold:
            same_domain = (classify_claim(draft) == classify_claim(item["text"])
                           or item.get("domain") == classify_claim(draft))
            if not same_domain and conflict is None:
                conflict = {"ref": item["ref"], "similarity": round(ratio, 2),
                            "text": item["text"][:120],
                            "note": "表述相近但归类不同，疑似口径分歧，审核时留意"}
    return duplicate, conflict


def _existing_corpus(db, user_id: str, keywords_of_interest: list[str],
                     cap: int = 200) -> list[dict]:
    """比对语料：博主 approved 观点（按关键词预筛）+ 该用户已 approved 导入。"""
    corpus: list[dict] = []
    try:
        from .claims import claim_store
        from .claim_review import is_publishable
        matched = 0
        for cid, claim in claim_store._by_id.items():  # noqa: SLF001
            text = str(claim.get("claim") or "")
            if not is_publishable(claim):
                continue
            if keywords_of_interest and not any(k in text for k in keywords_of_interest):
                continue
            corpus.append({"ref": f"blogger:{cid}", "text": text,
                           "domain": classify_claim(text)})
            matched += 1
            if matched >= cap:
                break
    except Exception:
        pass
    for text in db.approved_user_claim_texts(user_id, limit=100):
        corpus.append({"ref": "user_import", "text": text,
                       "domain": classify_claim(text)})
    return corpus


def import_knowledge(db, user_id: str, title: str, kind: str, content: str,
                     origin: str = "") -> dict:
    """导入主入口：保存→分段→提取草稿→重复/冲突检测→落待审/隔离。"""
    content = str(content or "").strip()
    if len(content) < 20:
        return {"error": "内容太短（至少 20 字）"}
    if kind not in ("text", "markdown", "pdf", "article"):
        return {"error": "kind 必须是 text/markdown/pdf/article"}
    chash = content_hash(content)
    existing_src = db.find_knowledge_source(user_id, chash)
    if existing_src:
        return {"error": f"相同内容已导入过（来源 #{existing_src['id']}"
                         f"「{existing_src['title']}」），不重复导入"}
    source_id = db.add_knowledge_source(user_id, title, kind, origin, chash)
    if source_id is None:
        return {"error": "相同内容已导入过"}

    chunks = split_chunks(content)
    for seq, chunk in enumerate(chunks):
        db.add_knowledge_chunk(source_id, seq, chunk)

    drafts = extract_claim_drafts(content)
    keywords = sorted({_tokenize(d["content"]).pop() if _tokenize(d["content"]) else ""
                       for d in drafts if _tokenize(d["content"])})[:6]
    corpus = _existing_corpus(db, user_id, [k for k in keywords if len(k) >= 2])

    stats = {"approved": 0, "pending": 0, "quarantined": 0, "duplicates": 0,
             "conflicts": 0}
    for d in drafts:
        duplicate, conflict = detect_duplicate_and_conflict(d["content"], corpus)
        import json as _json
        if d["risk_flag"]:
            status = "quarantined"
        else:
            status = "pending_review"
        db.add_knowledge_claim(
            user_id, source_id, None, d["content"], d["claim_type"], status,
            risk_flag=d["risk_flag"],
            duplicate_of=_json.dumps(duplicate, ensure_ascii=False) if duplicate else None,
            conflict_with=_json.dumps(conflict, ensure_ascii=False) if conflict else None)
        stats["quarantined" if status == "quarantined" else "pending"] += 1
        if duplicate:
            stats["duplicates"] += 1
        if conflict:
            stats["conflicts"] += 1
    return {"source_id": source_id, "chunks": len(chunks),
            "claims": len(drafts), "stats": stats}
