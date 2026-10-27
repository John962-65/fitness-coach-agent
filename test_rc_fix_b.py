"""RC-FIX-B：账户删除闭环、媒体/子表/日志与客户端清理。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach import account_deletion
from test_repair_regressions import profile


def _app(tmp_path):
    app = create_app(db_path=tmp_path / "rcfixb.db")
    c = TestClient(app)
    return c, app.state.db, tmp_path


def _seed(db, tmp_path, uid="u"):
    db.save_profile(uid, profile())
    media = tmp_path / "media" / uid
    media.mkdir(parents=True)
    video = media / "v1.mp4"
    video.write_bytes(b"video")
    cover = media / "cover.jpg"
    cover.write_bytes(b"cover")
    asset = db.add_media_asset(uid, "视频", str(video), None)
    db.update_media_asset(asset, status="ready")
    db.add_exercise_media_link(uid, "barbell_bench_press", asset, "句子",
                               0, 1, str(cover), None)
    ma = db.add_motion_analysis(uid, "barbell_back_squat", "side",
                                str(media / "motion.mp4"))
    db.finish_motion_analysis(ma, "ready", result={"supported": True})
    db.upsert_motion_tech_profile(uid, ma, "barbell_back_squat", {
        "model_version": "motion-1", "video_quality": {},
        "motion_observations": [], "phase_timestamps": []})
    src = db.add_knowledge_source(uid, "资料", "text", "raw", "hash-" + uid)
    db.add_knowledge_chunk(src, 0, "用户导入的资料正文")
    db.add_knowledge_claim(uid, src, None, "观点", "other", "pending_review")
    task = db.create_expert_task(uid, "training_science",
                                 "post-workout-review", "UserRequested",
                                 {"checkin_id": 1})
    db.insert_expert_insight({
        "id": "ins-" + uid, "user_id": uid, "task_id": task["id"],
        "specialist": "training_science", "insight_type": "post-workout-review",
        "title": "标题", "summary": "摘要", "findings": [],
        "evidence_refs": [], "facts_snapshot": {}, "knowledge_refs": [],
        "options": [], "limitations": [], "confidence": "low",
        "confidence_basis": "test", "generated_at": "2026-10-27T00:00:00",
        "expires_at": "2099-01-01T00:00:00", "source_revision": {},
        "input_refs": {}})
    db.add_message(uid, "user", "私聊内容")
    db.add_consultation(uid, "问题", ["training_science"], [])
    # 可直接归属的日志
    (tmp_path / "unmatched_exercises.jsonl").write_text(
        json.dumps({"user": uid, "name": "某动作"}) + "\n" +
        json.dumps({"user": "other", "name": "保留"}) + "\n")
    (tmp_path / "knowledge_loads.jsonl").write_text(
        json.dumps({"user_id": uid, "path": "x"}) + "\n" +
        json.dumps({"user_id": "other", "path": "y"}) + "\n")
    return {"video": video, "cover": cover, "src": src, "task": task["id"],
            "asset": asset, "motion": ma}


def test_account_deletion_removes_db_media_children_and_logs(tmp_path):
    c, db, tmp = _app(tmp_path)
    seeded = _seed(db, tmp)
    _seed(db, tmp, uid="keep")
    r = c.delete("/api/users/u/account?confirm=DELETE")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["deleted"] is True and out["complete"] is True
    assert out["rows"].get("knowledge_chunks", 0) >= 1
    assert out["rows"].get("expert_task_events", 0) >= 1
    assert out["media_files_removed"] >= 2
    assert not seeded["video"].exists() and not seeded["cover"].exists()
    assert not (tmp / "media" / "u").exists()
    # 删除后 API 不再返回个人数据
    for path in ("/api/users/u/profile", "/api/users/u/checkins",
                 "/api/users/u/training-facts", "/api/users/u/trials",
                 "/api/users/u/expert-insights", "/api/users/u/training-restrictions",
                 "/api/users/u/symptom-episodes"):
        assert c.get(path).status_code == 404, path
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM knowledge_chunks WHERE source_id=?",
        (seeded["src"],)).fetchone()["c"] == 0
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM expert_task_events WHERE task_id=?",
        (seeded["task"],)).fetchone()["c"] == 0
    # 日志过滤只删 u
    unmatched = (tmp / "unmatched_exercises.jsonl").read_text()
    assert '"user": "u"' not in unmatched and '"user": "other"' in unmatched
    loads = (tmp / "knowledge_loads.jsonl").read_text()
    assert '"user_id": "u"' not in loads and '"user_id": "other"' in loads
    # 另一个用户完整保留
    assert c.get("/api/users/keep/profile").status_code == 200
    assert (tmp / "media" / "keep").exists()
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM knowledge_chunks WHERE source_id=("
        "SELECT id FROM knowledge_sources WHERE user_id='keep')").fetchone()["c"] == 1
    assert out["backup_retention_days"] >= 0
    assert out["backup_notice"]


def test_deletion_refuses_non_media_paths_and_reports_incomplete(tmp_path):
    c, db, tmp = _app(tmp_path)
    db.save_profile("u", profile())
    outside = tmp / "outside.txt"
    outside.write_text("must stay")
    db.add_media_asset("u", "外部", str(outside), None)
    r = c.delete("/api/users/u/account?confirm=DELETE")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["deleted"] is True
    assert out["complete"] is False
    assert str(outside) in out["outside_media_not_deleted"]
    assert outside.exists()
    assert out["outside_media_not_deleted"]


def test_deletion_failure_before_db_keeps_user_and_files(tmp_path, monkeypatch):
    c, db, tmp = _app(tmp_path)
    seeded = _seed(db, tmp)
    original = account_deletion._move_to_trash

    def fail(*args, **kwargs):
        raise OSError("simulated media move failure")
    monkeypatch.setattr(account_deletion, "_move_to_trash", fail)
    with pytest.raises(OSError):
        account_deletion.delete_account(db, "u")
    assert db.get_existing_profile("u")
    assert seeded["video"].exists()


def test_late_file_cleanup_failure_reports_incomplete(tmp_path, monkeypatch):
    c, db, tmp = _app(tmp_path)
    _seed(db, tmp)
    original = account_deletion.shutil.rmtree

    def fail(*args, **kwargs):
        raise OSError("simulated rmtree failure")
    monkeypatch.setattr(account_deletion.shutil, "rmtree", fail)
    out = account_deletion.delete_account(db, "u")
    assert out["deleted"] is True and out["complete"] is False
    assert out["cleanup_errors"]
    assert out["trash_path"]
