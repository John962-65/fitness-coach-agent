"""RC-FIX-A：完整备份/恢复、关系、幂等与安全状态。"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.data_transfer import import_service
from coach.plan import generate_plan
from coach.rehab import restriction_service, symptom_service
from test_repair_regressions import profile

TODAY = date.today().isoformat()


def _new_app(tmp_path):
    app = create_app(db_path=tmp_path / "rcfixa.db")
    c = TestClient(app)
    db = app.state.db
    return c, db


def _seed_source(c, db):
    p = profile()
    p["basic"]["age"] = 31
    p["basic"]["weight_kg"] = 76
    db.save_profile("u", p)
    plan1 = generate_plan(p)
    db.create_plan("u", plan1)
    plan2 = json.loads(json.dumps(plan1))
    plan2["notes"] = list(plan2.get("notes") or []) + ["RC-FIX-A v2"]
    db.create_plan("u", plan2)
    plan_rec = db.get_active_plan_record("u")

    logs = [{"type": "weight_reps", "weight_kg": 60, "reps": 8,
             "rpe": 7}] * 3
    cid1 = db.record_checkin("u", "training", {
        "exercises": [{"name": "杠铃平板卧推",
                       "exercise_id": "barbell_bench_press",
                       "set_logs": logs}],
        "session_meta": {"mode": "free",
                         "local_date": (date.today() - timedelta(days=5)).isoformat()}})
    cid2 = db.record_checkin("u", "training", {
        "exercises": [{"name": "杠铃深蹲", "exercise_id": "barbell_back_squat",
                       "set_logs": logs}],
        "session_meta": {"mode": "free",
                         "local_date": (date.today() - timedelta(days=3)).isoformat()}})
    cid3 = db.record_checkin("u", "training", {
        "exercises": [{"name": "杠铃划船", "exercise_id": "barbell_row",
                       "set_logs": logs}],
        "session_meta": {"mode": "free", "local_date": TODAY}})
    db.revise_checkin("u", cid1, 0, {
        "exercises": [{"name": "杠铃平板卧推",
                       "exercise_id": "barbell_bench_press",
                       "set_logs": logs + [{"type": "weight_reps",
                                            "weight_kg": 62.5, "reps": 6}]}],
        "session_meta": {"mode": "free",
                         "local_date": (date.today() - timedelta(days=5)).isoformat()}},
        "补记一组", "用户确认补记 62.5kg×6")

    mid = db.create_body_measurement("u", {
        "measured_at": f"{TODAY}T08:00:00", "local_date": TODAY,
        "weight_kg": 76.0, "measurement_method": "home_scale"})
    db.revise_body_measurement("u", mid, 0, {"weight_kg": 75.6},
                               "体重复测", "用户确认 75.6kg")
    rid, _ = db.upsert_recovery_checkin("u", {
        "local_date": TODAY, "recorded_at": f"{TODAY}T07:30:00",
        "sleep_hours": 7, "fatigue": 3})
    db.upsert_recovery_checkin("u", {
        "local_date": TODAY, "recorded_at": f"{TODAY}T08:00:00",
        "sleep_hours": 7.5, "fatigue": 2,
        "reason": "更新睡眠", "evidence": "用户确认睡 7.5 小时"})

    sym = symptom_service.report_episode(db, "u", {
        "body_region": "shoulder", "side": "right",
        "onset_at": TODAY, "description": "肩部酸痛，推举时明显",
        "severity": 3})
    symptom_id = sym["episode_id"]
    restriction_service.create_restriction(db, "u", {
        "source_type": "professional",
        "source_evidence": "医生要求暂不进行杠铃卧推",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [], "movements": ["barbell_bench_press"]},
        "related_episode_id": symptom_id})

    db.save_training_template("u", "模板A", {"days": []})
    db.save_training_template("u", "模板B", {"days": [1]})
    food_id = db.add_custom_food("u", {
        "name": "测试蛋白粉", "category": "supplement",
        "energy_kcal": 120, "protein_g": 24, "reference_amount": 30,
        "reference_unit": "g"})
    assert food_id
    db.save_meal("u", TODAY, "lunch", [
        {"food_id": food_id, "name": "测试蛋白粉", "amount": 30, "unit": "g",
         "energy_kcal": 120, "protein_g": 24}], "")
    db.save_recipe("u", "测试食谱", [
        {"food_id": food_id, "amount": 30, "unit": "g"}])
    db.add_user_equipment("u", "barbell", {"name": "杠铃",
                                           "category": "free_weight"})
    db.add_user_equipment("u", "bench", {"name": "卧推凳",
                                         "category": "bench"})
    db.create_training_location("u", {
        "name": "家", "kind": "home", "required_equipment": ["bench"],
        "optional_equipment": []})
    db.create_training_location("u", {
        "name": "健身房", "kind": "gym",
        "required_equipment": ["barbell", "bench"], "optional_equipment": []})
    src = db.add_knowledge_source("u", "审计资料", "text", "origin",
                                  "hash-rc-fix-a")
    db.add_knowledge_chunk(src, 0, "用户导入的个人资料正文")
    db.add_knowledge_claim("u", src, None, "这是一条待审核观点", "other",
                           "pending_review")
    db.add_consultation("u", "咨询问题", ["training_science"], [])
    trial_id = db.start_personal_trial(
        "u", "卧推小幅加重", "RC-FIX-A", "观察完成次数", "3 次或 14 天",
        review_days=14, exercise_id="barbell_bench_press",
        plan_id=plan_rec["id"], plan_version=plan_rec["version"],
        chosen_target=json.dumps({"sets": 3, "reps": "8", "weight_kg": 62.5}),
        observation_metric="target-completion", observation_window_days=14,
        min_sessions=3,
        baseline_source_revisions=json.dumps({
            "checkins": {str(cid1): 1, str(cid2): 0},
            "plan": {"plan_id": plan_rec["id"],
                     "plan_version": plan_rec["version"]}}))
    media_dir = Path(db.path.parent) / "media" / "u"
    media_dir.mkdir(parents=True)
    video = media_dir / "v1.mp4"
    video.write_bytes(b"rc-fix-a-video")
    db.add_media_asset("u", "测试视频", str(video), None)
    return {"symptom_id": symptom_id, "trial_id": trial_id,
            "checkin_ids": [cid1, cid2, cid3], "plan_id": plan_rec["id"],
            "food_id": food_id}


def _export(c, uid="u"):
    r = c.post(f"/api/users/{uid}/export",
               json={"format": "json", "confirm": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_restore_preserves_relationships_and_is_idempotent(tmp_path):
    c, db = _new_app(tmp_path)
    seeded = _seed_source(c, db)
    export = _export(c)
    assert set(export["user_data"]) >= {
        "plans", "checkins", "checkin_revisions", "personal_trials",
        "training_templates", "recipes", "body_measurements",
        "body_measurement_revisions", "recovery_checkins",
        "recovery_revisions", "symptom_episodes", "symptom_observations",
        "training_restrictions", "training_restriction_revisions",
        "training_locations", "user_equipment", "custom_foods", "meals",
        "training_approach", "approach_revisions", "nutrition_targets",
        "user_exercise", "knowledge_sources",
    }
    db.get_profile("v")  # 默认档案（未建档）
    preview = c.post("/api/users/v/import/preview", json=export)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["profile_restore_default"] is True
    assert body["counts"]["plans"]["to_insert"] == 2
    assert body["counts"]["checkins"]["to_insert"] == 3
    assert body["counts"]["personal_trials"]["to_insert"] == 1
    assert body["counts"]["training_templates"]["to_insert"] == 2
    assert body["counts"]["recipes"]["to_insert"] == 1
    assert body["counts"]["training_locations"]["to_insert"] == 2
    assert body["counts"]["user_equipment"]["to_insert"] == 2
    assert body["counts"]["symptom_observations"]["total"] == 1
    assert body["safety_review"]["requires_accept_safety_import"] is True

    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "archive"
    assert out["activated_plan"] is None
    assert db.get_active_plan_record("v") is None

    # 计划与检查记录
    plans = db.conn.execute(
        "SELECT * FROM plans WHERE user_id='v' ORDER BY version").fetchall()
    assert len(plans) == 2
    imported_plan_ids = {p["id"] for p in plans}
    sessions = db.conn.execute(
        "SELECT * FROM checkins WHERE user_id='v' ORDER BY id").fetchall()
    assert len(sessions) == 3
    imported_checkin_ids = {s["id"] for s in sessions}
    revs = db.conn.execute(
        "SELECT * FROM checkin_revisions WHERE user_id='v'").fetchall()
    assert len(revs) == 1 and revs[0]["checkin_id"] in imported_checkin_ids

    # 症状→观察→限制关联
    symptoms = db.conn.execute(
        "SELECT * FROM symptom_episodes WHERE user_id='v'").fetchall()
    observations = db.conn.execute(
        "SELECT * FROM symptom_observations WHERE user_id='v'").fetchall()
    restrictions = db.conn.execute(
        "SELECT * FROM training_restrictions WHERE user_id='v'").fetchall()
    assert len(symptoms) == 1 and len(observations) == 1
    assert observations[0]["episode_id"] == symptoms[0]["id"]
    assert any(x["source_type"] == "professional" and x["status"] == "active"
               for x in restrictions)
    prof = next(x for x in restrictions if x["source_type"] == "professional")
    assert prof["related_episode_id"] == symptoms[0]["id"]

    # 尝试：计划/打卡引用改写
    trial = db.conn.execute(
        "SELECT * FROM personal_trials WHERE user_id='v'").fetchone()
    assert trial["plan_id"] is not None and int(trial["plan_id"]) in imported_plan_ids
    bsr = json.loads(trial["baseline_source_revisions"])
    assert set(map(int, bsr["checkins"])) <= imported_checkin_ids
    assert int(bsr["plan"]["plan_id"]) in imported_plan_ids

    # 身体/恢复修订
    body_revs = db.conn.execute(
        "SELECT * FROM body_measurement_revisions WHERE user_id='v'").fetchall()
    recovery_revs = db.conn.execute(
        "SELECT * FROM recovery_revisions WHERE user_id='v'").fetchall()
    assert len(body_revs) == 1 and len(recovery_revs) == 1
    body_ids = {r["id"] for r in db.conn.execute(
        "SELECT id FROM body_measurements WHERE user_id='v'").fetchall()}
    rec_ids = {r["id"] for r in db.conn.execute(
        "SELECT id FROM recovery_checkins WHERE user_id='v'").fetchall()}
    assert body_revs[0]["measurement_id"] in body_ids
    assert recovery_revs[0]["recovery_id"] in rec_ids

    # 自定义食物→餐次/食谱映射
    foods = db.conn.execute(
        "SELECT id FROM foods WHERE user_id='v'").fetchall()
    assert len(foods) == 1
    food_id = foods[0]["id"]
    meal = db.conn.execute(
        "SELECT items FROM meal_entries WHERE user_id='v'").fetchone()
    assert json.loads(meal["items"])[0]["food_id"] == food_id
    recipe = db.conn.execute(
        "SELECT items FROM nutrition_recipes WHERE user_id='v'").fetchone()
    assert json.loads(recipe["items"])[0]["food_id"] == food_id

    # 模板/器械/地点
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM training_templates WHERE user_id='v'"
    ).fetchone()["c"] == 2
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM user_equipment WHERE user_id='v'"
    ).fetchone()["c"] == 2
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM training_locations WHERE user_id='v'"
    ).fetchone()["c"] == 2
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM knowledge_chunks WHERE source_id IN"
        " (SELECT id FROM knowledge_sources WHERE user_id='v')"
    ).fetchone()["c"] == 1
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM knowledge_claims WHERE user_id='v'"
    ).fetchone()["c"] == 1
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM agent_consultations WHERE user_id='v'"
    ).fetchone()["c"] == 1

    # 重复导入：不新增、不重复、不重复解除
    before = {t: db.conn.execute(
        f"SELECT COUNT(*) c FROM {t} WHERE user_id='v'").fetchone()["c"]
        for t in ("plans", "checkins", "checkin_revisions", "personal_trials",
                  "training_templates", "nutrition_recipes", "user_equipment",
                  "training_locations", "symptom_episodes",
                  "symptom_observations", "training_restrictions",
                  "body_measurements", "recovery_checkins")}
    r2 = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True})
    assert r2.status_code == 200, r2.text
    again = r2.json()["inserted"]
    for key in ("plans", "checkins", "checkin_revisions", "trials",
                "templates", "recipes", "equipment", "locations",
                "symptoms", "observations", "restrictions", "body", "recovery"):
        assert again[key] == 0, (key, again)
    after = {t: db.conn.execute(
        f"SELECT COUNT(*) c FROM {t} WHERE user_id='v'").fetchone()["c"]
        for t in before}
    assert before == after
    still_active = db.conn.execute(
        "SELECT COUNT(*) c FROM training_restrictions"
        " WHERE user_id='v' AND status='active'").fetchone()["c"]
    assert still_active >= 1
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM training_restrictions WHERE user_id='v'"
        " AND source_type='professional' AND status='active'").fetchone()["c"] == 1


def test_activation_is_blocked_by_imported_restriction(tmp_path):
    c, db = _new_app(tmp_path)
    _seed_source(c, db)
    export = _export(c)
    db.get_profile("v")
    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True,
        "activate_plan": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "archive"
    assert out["activated_plan"] is None
    assert out["activation_blocked"]
    assert db.get_active_plan_record("v") is None


def test_active_plan_restores_only_when_safe_and_explicit(tmp_path):
    c, db = _new_app(tmp_path)
    p = profile()
    db.save_profile("u", p)
    db.create_plan("u", generate_plan(p))
    plan2 = generate_plan(p)
    plan2["notes"] = list(plan2.get("notes") or []) + ["v2"]
    db.create_plan("u", plan2)
    export = _export(c)
    assert [x["version"] for x in export["user_data"]["plans"]] == [1, 2]
    db.get_profile("v")
    preview = c.post("/api/users/v/import/preview", json=export).json()
    assert preview["can_activate_plan"] is True
    assert preview["source_active_plan_version"] == 2
    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True,
        "activate_plan": True})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "executable"
    assert out["activated_plan"]["version"] == 2
    active = db.get_active_plan_record("v")
    assert active["version"] == 2
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM plans WHERE user_id='v'").fetchone()["c"] == 2
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM plans WHERE user_id='v' AND active=1"
    ).fetchone()["c"] == 1


def test_professional_lift_without_evidence_stays_active(tmp_path):
    c, db = _new_app(tmp_path)
    p = profile()
    db.save_profile("u", p)
    rid = restriction_service.create_restriction(db, "u", {
        "source_type": "professional",
        "source_evidence": "医生要求暂不卧推",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [], "movements": ["barbell_bench_press"]}})
    # 直接构造“已解除但没有可信依据”的源记录
    rid = rid["id"] if isinstance(rid, dict) else rid
    db.revise_restriction("u", rid, 0, {"status": "lifted",
                                        "lift_evidence": ""},
                          "源备份状态", "")
    export = _export(c)
    db.get_profile("v")
    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True})
    assert r.status_code == 200, r.text
    restrictions = db.conn.execute(
        "SELECT * FROM training_restrictions WHERE user_id='v'").fetchall()
    assert len(restrictions) == 1
    assert restrictions[0]["status"] == "active"
    assert r.json()["needs_review"]


def test_import_rollback_keeps_target_unchanged(tmp_path, monkeypatch):
    c, db = _new_app(tmp_path)
    _seed_source(c, db)
    export = _export(c)
    db.get_profile("v")
    before_profile = db.get_existing_profile("v")
    original = import_service._insert_row

    def boom(conn, table, row, user_id, omit=("id",), overrides=None):
        if table == "checkins":
            raise RuntimeError("injected mid-transaction failure")
        return original(conn, table, row, user_id, omit=omit,
                        overrides=overrides)

    monkeypatch.setattr(import_service, "_insert_row", boom)
    with pytest.raises(RuntimeError):
        import_service.apply_import(
            db, "v", export, restore_profile=True,
            accept_safety_import=True)
    assert db.get_existing_profile("v") == before_profile
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM plans WHERE user_id='v'").fetchone()["c"] == 0
    assert db.conn.execute(
        "SELECT COUNT(*) c FROM checkins WHERE user_id='v'").fetchone()["c"] == 0


def test_media_manifest_hash_is_required_for_integrity(tmp_path):
    c, db = _new_app(tmp_path)
    _seed_source(c, db)
    export = _export(c)
    assert export["media_manifest"]
    db.get_profile("v")
    # 正常文件：通过
    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True,
        "require_media_integrity": True})
    assert r.status_code == 200, r.text
    assert r.json()["media_report"]["ok"]
    # 篡改文件：拒绝且不写入
    path = Path(export["media_manifest"][0]["file_ref"])
    path.write_bytes(b"tampered-after-export")
    r2 = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "require_media_integrity": True})
    assert r2.status_code == 422
    assert "媒体完整性" in r2.json()["detail"]["error"]


def test_professional_lift_with_evidence_is_imported_lifted(tmp_path):
    c, db = _new_app(tmp_path)
    p = profile()
    db.save_profile("u", p)
    rid = restriction_service.create_restriction(db, "u", {
        "source_type": "professional",
        "source_evidence": "医生要求暂不卧推",
        "restriction_description": "暂不做杠铃卧推",
        "affected_activities": {"regions": [], "movements": ["barbell_bench_press"]}})
    rid = rid["id"] if isinstance(rid, dict) else rid
    db.revise_restriction("u", rid, 0, {
        "status": "lifted",
        "lift_evidence": "复诊医生书面说明：可恢复卧推，从轻负荷逐步增加（2026-10-20）",
    }, "专业复诊解除", "复诊记录")
    export = _export(c)
    db.get_profile("v")
    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True,
        "restore_profile": True, "accept_safety_import": True})
    assert r.status_code == 200, r.text
    rows = db.conn.execute(
        "SELECT * FROM training_restrictions WHERE user_id='v'").fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "lifted"
    revs = db.conn.execute(
        "SELECT * FROM training_restriction_revisions WHERE user_id='v'").fetchall()
    assert len(revs) == 1


def test_profile_safety_fields_are_not_trusted_by_default(tmp_path):
    c, db = _new_app(tmp_path)
    p = profile()
    p["conditions"]["health_screen"]["clearance"] = "医生允许正常力量训练"
    db.save_profile("u", p)
    db.create_plan("u", generate_plan(p))
    export = _export(c)
    db.get_profile("v")
    r = c.post("/api/users/v/import/apply", json={
        "backup": export, "confirmed": True, "restore_profile": True})
    assert r.status_code == 200, r.text
    profile_v = db.get_existing_profile("v")
    assert "未核验" in profile_v["conditions"]["health_screen"]["clearance"]
    assert profile_v.get("imported_safety_review") is True
    assert "医疗筛查" in "；".join(r.json()["warnings"])
