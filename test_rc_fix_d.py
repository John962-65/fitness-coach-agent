"""RC-FIX-D：P2 安全收尾（确认引用、导入来源、资源上限、CSV 注入）。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.data_transfer import import_service
from coach.knowledge_import import MAX_PDF_BYTES, extract_pdf_text
from test_repair_regressions import profile


def _app(tmp_path):
    app = create_app(db_path=tmp_path / "rcfixd.db")
    return TestClient(app), app.state.db


def _plan(db, uid="u"):
    from coach.plan import generate_plan
    p = profile()
    db.save_profile(uid, p)
    db.create_plan(uid, generate_plan(p))
    return db.get_active_plan_record(uid)


def test_bare_confirmation_does_not_apply_pending_proposal(tmp_path):
    c, db = _app(tmp_path)
    plan = _plan(db)
    day = plan["content"]["schedule"][0]["day"]
    r = c.post("/api/users/u/changes/ai", json={
        "target": "plan",
        "operations": [{"op": "rename_day", "day": day, "new_name": "推日"}],
        "reason": "用户想把训练日名称改清楚",
        "base_version": {"plan_id": plan["id"], "plan_version": plan["version"]}})
    assert r.status_code == 200, r.text
    pid = r.json()["proposal_id"]
    bare = c.post(f"/api/users/u/changes/{pid}/confirm",
                  json={"message": "好的"})
    assert bare.status_code == 200
    assert bare.json()["status"] == "pending"
    assert bare.json()["decision"] == "unclear"
    assert c.get("/api/users/u/plan").json()["version"] == plan["version"]
    # 明确引用 ID 才执行
    ok = c.post(f"/api/users/u/changes/{pid}/confirm",
                json={"message": f"确认采用提案 {pid}"})
    assert ok.status_code == 200 and ok.json()["status"] == "applied"
    assert c.get("/api/users/u/plan").json()["version"] == plan["version"] + 1


def test_import_rejects_unknown_restriction_source():
    with pytest.raises(ValueError, match="source_type"):
        import_service._validate_rows({"training_restrictions": [{
            "source_type": "admin_override", "status": "active",
            "restriction_description": "x"}]})


def test_import_json_complexity_and_size_limits(monkeypatch):
    nested = {}
    cur = nested
    for _ in range(45):
        cur["x"] = {}
        cur = cur["x"]
    payload = {"schema_version": "fcs-export-v1", "user_data": nested}
    with pytest.raises(ValueError, match="嵌套过深"):
        import_service._validate_payload(payload)
    monkeypatch.setattr(import_service, "MAX_IMPORT_BYTES", 64)
    with pytest.raises(ValueError, match="超过导入上限"):
        import_service._validate_payload({
            "schema_version": "fcs-export-v1",
            "user_data": {"x": "a" * 200}})


def test_pdf_and_subtitle_size_limits(tmp_path):
    with pytest.raises(ValueError, match="MB 上限"):
        extract_pdf_text(b"x" * (MAX_PDF_BYTES + 1))
    c, db = _app(tmp_path)
    db.save_profile("u", profile())
    video = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
    subtitle = b"1\n00:00:00,000 --> 00:00:01,000\n" + b"x" * (2 * 1024 * 1024 + 1)
    r = c.post("/api/users/u/media/videos", files={
        "video": ("v.mp4", video, "video/mp4"),
        "subtitle": ("s.srt", subtitle, "text/plain"),
    })
    assert r.status_code == 422
    assert "大小限制" in r.text


def test_csv_export_neutralizes_formula_injection(tmp_path):
    c, db = _app(tmp_path)
    db.save_profile("u", profile())
    db.record_checkin("u", "training", {
        "exercises": [{
            "name": "=HYPERLINK(\"http://evil\")",
            "exercise_id": "barbell_bench_press",
            "set_logs": [{"type": "weight_reps", "weight_kg": 60, "reps": 8}],
        }],
        "session_meta": {"mode": "free", "local_date": "2026-10-27"}})
    r = c.post("/api/users/u/export", json={"format": "csv", "confirm": True})
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    text = zf.read("training_sets.csv").decode()
    assert "'=HYPERLINK" in text
    assert "\n=HYPERLINK" not in text
