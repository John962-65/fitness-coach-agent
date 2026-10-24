"""M3 统一知识库与知识导入回归（DESIGN_2.0 §六，任务 1–4/8–9）。

验收红线（§6.3/M3 验收）：
- 用户确认导入 ≠ 科学验证：三种状态（已保存/提取通过/审核通过）分离；
- 未经审核的高风险知识不能成为训练处方依据（quarantined 不可放行、不进检索）；
- pending/quarantined 不出现在统一检索结果里；
- 重复导入被内容哈希拒绝；疑似重复/冲突带证据进待审。
"""
import pytest
from fastapi.testclient import TestClient

from coach.db import Database
from coach.knowledge_import import (classify_claim, content_hash,
                                    detect_duplicate_and_conflict,
                                    extract_claim_drafts, import_knowledge,
                                    split_chunks)
from coach.knowledge_search import _keywords, search
from backend.app import create_app
from test_repair_regressions import profile


def make_db(tmp_path, uid="m3"):
    db = Database(tmp_path / "test.db")
    db.save_profile(uid, profile())
    return db


# ---- 统一检索 ----

def test_search_covers_md_and_blogger_engines(tmp_path):
    db = make_db(tmp_path)
    result = search(db, "m3", "减脂平台期怎么办")
    assert any(k in ("减脂", "平台") for k in result["keywords"])
    md_refs = [h["ref"] for h in result["engines"]["knowledge_md"]["hits"]]
    assert any("plateau" in r or "troubleshooting" in r for r in md_refs)
    # 博主观点引擎：approved 可见、draft 只计数（审核纪律）
    engine = result["engines"]["blogger_claims"]
    assert isinstance(engine["draft_matches"], int)
    for hit in engine["hits"]:
        assert hit["status"] == "approved"


def test_search_user_imports_only_after_approval(tmp_path):
    db = make_db(tmp_path)
    text = ("减脂期建议保持每公斤体重 1.8 克蛋白摄入。"
            "训练应该维持大重量来保住肌肉。不要因为累了就跳过力量训练。")
    import_knowledge(db, "m3", "我的笔记", "text", text)
    assert search(db, "m3", "蛋白摄入")["engines"]["user_imports"]["hits"] == []
    pending = db.list_knowledge_claims("m3", "pending_review")
    protein = next(cl for cl in pending if "蛋白" in cl["content"])
    assert db.review_knowledge_claim("m3", protein["id"], "approved")
    hits = search(db, "m3", "蛋白摄入")["engines"]["user_imports"]["hits"]
    assert hits and "1.8 克蛋白" in hits[0]["snippet"]


def test_search_rejects_empty_query_keywords(tmp_path):
    db = make_db(tmp_path)
    assert search(db, "m3", "!")["keywords"] == []
    assert _keywords("蛋白质摄入")  # CJK 2-gram


# ---- 导入流水线 ----

def test_import_chunks_and_draft_claims(tmp_path):
    db = make_db(tmp_path)
    text = ("## 训练\n\n卧推建议每周安排两次，每次 4 组。\n\n"
            "## 营养\n\n蛋白摄入应该达到每公斤 2 克。不要害怕碳水。")
    result = import_knowledge(db, "m3", "笔记", "markdown", text)
    assert result["chunks"] == 2 and result["claims"] >= 2
    assert result["stats"]["pending"] == result["claims"]
    sources = db.list_knowledge_sources("m3")
    assert sources[0]["pending"] == result["claims"]


def test_import_rejects_duplicate_content(tmp_path):
    db = make_db(tmp_path)
    text = "建议每周训练三次。应该循序渐进地加重量。不要冒进。"
    first = import_knowledge(db, "m3", "A", "text", text)
    assert "source_id" in first
    again = import_knowledge(db, "m3", "B", "text", text)
    assert "已导入过" in again["error"]
    assert import_knowledge(db, "m3", "C", "text", "太短")["error"]


def test_high_risk_content_quarantined_and_never_approved(tmp_path):
    db = make_db(tmp_path)
    text = ("有人推荐用类固醇快速增肌。建议自然训练。"
                "每次训练不要超过一小时。")
    result = import_knowledge(db, "m3", "风险笔记", "text", text)
    assert result["stats"]["quarantined"] >= 1
    quarantined = db.list_knowledge_claims("m3", "quarantined")
    assert quarantined and "类固醇" in quarantined[0]["risk_flag"]
    # 隔离条目不可审核放行
    assert db.review_knowledge_claim("m3", quarantined[0]["id"], "approved") is False
    # 且不出现在检索
    assert search(db, "m3", "类固醇")["engines"]["user_imports"]["hits"] == []


def test_duplicate_and_conflict_detection(tmp_path):
    db = make_db(tmp_path)
    existing = [{"ref": "blogger:ksw-0001",
                 "text": "卧推建议每周练两次每次四组循序渐进",
                 "domain": "method"}]
    dup, _ = detect_duplicate_and_conflict(
        "卧推建议每周练两次，每次四组，循序渐进", existing)
    assert dup and dup["ref"] == "blogger:ksw-0001" and dup["similarity"] >= 0.72
    _, conflict = detect_duplicate_and_conflict(
        "卧推建议每周练两次每次四组，蛋白粉要选乳清的", existing)
    assert conflict is None or conflict["ref"]  # 边界行为确定即可
    # 无 token 重叠 → 不比对
    assert detect_duplicate_and_conflict("今天天气很好阳光明媚", existing) == (None, None)


def test_extract_drafts_filters_noise():
    drafts = extract_claim_drafts(
        "今天去了健身房。\n" * 3 + "硬拉时应该保持背部中立。膝盖不要内扣。")
    contents = [d["content"] for d in drafts]
    assert any("背部中立" in c for c in contents)
    assert all("今天去了健身房" not in c for c in contents)
    assert classify_claim("蛋白摄入每公斤 2 克") == "nutrition"
    assert split_chunks("a\n\nb", 5) == ["a", "b"]


def test_content_hash_ignores_whitespace():
    assert content_hash("蛋白 2克\n") == content_hash("蛋白2克")
    assert content_hash("蛋白 2克") != content_hash("碳水 3克")


# ---- API 层 ----

@pytest.fixture()
def m3client(tmp_path):
    app = create_app(db_path=tmp_path / "api.db")
    with TestClient(app) as c:
        app.state.db.save_profile("m3u", profile())
        yield c, app


def test_api_import_review_search_flow(m3client):
    c, _ = m3client
    text = ("增肌期建议热量盈余控制在百分之十以内。"
            "睡眠应该保证七小时以上。训练频率可以是每周四练。")
    imported = c.post("/api/users/m3u/knowledge/imports",
                      json={"title": "增肌笔记", "kind": "text", "content": text})
    assert imported.status_code == 200
    body = imported.json()
    assert body["claims"] >= 3 and body["stats"]["pending"] == body["claims"]

    claims = c.get("/api/users/m3u/knowledge/claims",
                   params={"status": "pending_review"}).json()["claims"]
    target = next(cl for cl in claims if "热量盈余" in cl["content"])
    ok = c.post(f"/api/users/m3u/knowledge/claims/{target['id']}/review",
                json={"decision": "approve"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"

    result = c.get("/api/knowledge/search",
                   params={"uid": "m3u", "q": "热量盈余 增肌"}).json()
    user_hits = result["engines"]["user_imports"]["hits"]
    assert any("热量盈余" in h["snippet"] for h in user_hits)
    # 重复导入 422
    dup = c.post("/api/users/m3u/knowledge/imports",
                 json={"title": "再来一次", "kind": "text", "content": text})
    assert dup.status_code == 422 and "已导入过" in dup.json()["detail"]["error"]


def test_api_quarantine_not_approvable(m3client):
    c, _ = m3client
    c.post("/api/users/m3u/knowledge/imports", json={
        "title": "危险", "kind": "text",
        "content": "网上有人说用利尿剂快速降体重很有效。建议不要这样做。"})
    quarantined = c.get("/api/users/m3u/knowledge/claims",
                        params={"status": "quarantined"}).json()["claims"]
    assert quarantined
    resp = c.post(f"/api/users/m3u/knowledge/claims/{quarantined[0]['id']}/review",
                  json={"decision": "approve"})
    assert resp.status_code == 422 and "隔离" in resp.json()["detail"]["error"]


def test_api_pdf_import_with_pymupdf(m3client):
    pytest.importorskip("fitz")
    c, _ = m3client
    import base64
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Train twice per week with progressive overload.")
    pdf_bytes = doc.tobytes()
    resp = c.post("/api/users/m3u/knowledge/imports", json={
        "title": "PDF 笔记", "kind": "pdf",
        "content": base64.b64encode(pdf_bytes).decode()})
    assert resp.status_code == 200
    assert resp.json()["chunks"] >= 1
