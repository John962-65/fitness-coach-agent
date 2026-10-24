"""M6.2：动作教学文档——knowledge_refs 解析、路径安全与 API 集成。"""
from __future__ import annotations

import pytest

from coach import exercise_service as svc


def test_teaching_parses_frontmatter_and_body():
    docs = svc.teaching_for("barbell_bench_press")
    assert len(docs) == 1
    d = docs[0]
    assert d["path"] == "20_exercises/chest/bench_press_technique.md"
    assert d["topic"] == "卧推技术细节"
    assert "谭成义-胸部教学" in d["source"]
    assert d["provenance"] == "general"
    assert d["updated"]
    # 正文：frontmatter 已剥离，核心内容保留
    assert d["markdown"].startswith("# ")
    assert "把自己推离杠铃" in d["markdown"]
    assert "topic:" not in d["markdown"]


def test_teaching_empty_for_exercise_without_refs():
    assert svc.teaching_for("leg_press") == []
    assert svc.teaching_for("nonexistent_exercise") == []


def test_teaching_blocks_path_escape_and_bad_refs(monkeypatch):
    malicious = [
        "../../../etc/passwd.md",        # 目录穿越
        "../../backend/app.py",          # 非 md
        "20_exercises/不存在.md",         # 缺文件
        "20_exercises/leg/squat_technique.md",  # 合法
        42,                              # 类型错误
    ]
    monkeypatch.setattr(svc.library, "get",
                        lambda _id: {"id": "fake", "knowledge_refs": malicious})
    docs = svc.teaching_for("fake")
    assert [d["path"] for d in docs] == ["20_exercises/leg/squat_technique.md"]


def test_teaching_multiple_refs_keep_order(monkeypatch):
    monkeypatch.setattr(svc.library, "get", lambda _id: {"id": "fake", "knowledge_refs": [
        "20_exercises/back/rowing_variations.md",
        "20_exercises/back/lat_activation.md"]})
    docs = svc.teaching_for("fake")
    assert [d["topic"] for d in docs] == ["划船类动作变式", "背阔肌发力模式"]


def test_all_knowledge_refs_in_repo_resolve():
    """仓库级不变量：每个 exercises/*.yaml 的 knowledge_refs 都必须指向真实文件
    （含子目录）。错链会让教学内容静默消失（teaching=[]），这里显式拦截。"""
    bad = []
    for ex in svc.library.all():
        for rel in ex.get("knowledge_refs") or []:
            p = (svc.KNOWLEDGE_DIR / rel).resolve()
            if not p.is_relative_to(svc.KNOWLEDGE_DIR) or not p.is_file():
                bad.append((ex["id"], rel))
    assert bad == []

# API 集成断言见 test_api.py::test_exercise_detail_includes_teaching（client fixture 在彼处定义）
