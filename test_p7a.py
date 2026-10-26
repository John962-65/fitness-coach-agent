"""P7-A：数据导出与备份导入回归。"""
from __future__ import annotations

import json
import zipfile
from datetime import date, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.plan import generate_plan
from coach.rehab import symptom_service
from test_repair_regressions import profile

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p7a.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        db.create_plan("u", generate_plan(profile()))
        yield c, db


def seed_full(c, db):
    logs = [{"type": "weight_reps", "weight_kg": 60, "reps": 12, "rpe": 7}] * 4
    c.post("/api/users/u/checkins", json={
        "type": "training", "data": {
            "exercises": [{"name": "杠铃平板卧推",
                           "exercise_id": "barbell_bench_press",
                           "set_logs": logs}],
            "session_meta": {"mode": "free",
                             "local_date": (date.today()
                                            - timedelta(days=2)).isoformat()}}})
    db.save_meal("u", TODAY, "lunch", [
        {"food_id": "bi-rice", "amount": 200, "unit": "克",
         "name": "米饭（熟）", "energy_kcal": 232, "protein_g": 5.4}], "")
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 3, "sleep_hours": 7}})
    assert c.post("/api/users/u/body-measurements", json={
        "measured_at": f"{TODAY}T08:00:00", "local_date": TODAY,
        "weight_kg": 75.2, "measurement_method": "home_scale",
        "source": "user"}).status_code == 200
    symptom_service.report_episode(db, "u", {
        "body_region": "shoulder", "description": "肩部酸痛两天",
        "onset_at": TODAY})


def test_export_requires_confirm_and_returns_verified_json(client):
    c, db = client
    seed_full(c, db)
    # 未确认 → 拒绝
    r0 = c.post("/api/users/u/export", json={"format": "json"})
    assert r0.status_code == 422 and "confirm" in r0.json()["detail"]["error"]
    r = c.post("/api/users/u/export", json={"format": "json", "confirm": True})
    assert r.status_code == 200
    export = r.json()
    assert export["schema_version"] == "fcs-export-v1"
    ud = export["user_data"]
    assert ud["checkins"] and ud["checkins"][0]["data"]["exercises"]
    assert ud["meals"] and ud["recovery_checkins"] and ud["body_measurements"]
    assert ud["symptom_episodes"]
    assert export["integrity_manifest"]["user_data"]
    assert "barbell_bench_press" in export["exercise_mapping"]
    assert "plan" in str(export["source_revisions"])


def test_export_csv_is_readable_zip(client):
    c, db = client
    seed_full(c, db)
    r = c.post("/api/users/u/export", json={"format": "csv", "confirm": True})
    assert r.status_code == 200
    zf = zipfile.ZipFile(BytesIO(r.content))
    names = zf.namelist()
    assert "training_sets.csv" in names and "integrity_manifest.json" in names
    sets_csv = zf.read("training_sets.csv").decode()
    assert "杠铃平板卧推" in sets_csv and "weight_kg" in sets_csv


def test_import_preview_detects_duplicates_and_rejects_tampering(client):
    c, db = client
    seed_full(c, db)
    export = c.post("/api/users/u/export",
                    json={"format": "json", "confirm": True}).json()
    # 完整性被改动 → 拒绝
    tampered = json.loads(json.dumps(export))
    tampered["user_data"]["checkins"] = []
    bad = c.post("/api/users/u/import/preview", json=tampered)
    assert bad.status_code == 422 and "完整性" in bad.json()["detail"]["error"]
    # 未知节 → 拒绝
    unknown = json.loads(json.dumps(export))
    unknown["unknown_section"] = {"evil": True}
    bad2 = c.post("/api/users/u/import/preview", json=unknown)
    assert bad2.status_code == 422 and "未知节" in bad2.json()["detail"]["error"]
    # 预览到另一个用户：识别动作映射（同名则无冲突）、计数
    db.save_profile("v", profile())
    preview = c.post("/api/users/v/import/preview", json=export)
    assert preview.status_code == 200
    body = preview.json()
    assert body["counts"]["checkins"]["to_insert"] == 1
    assert body["requires_confirmation"] is True
    # 重复预览（导入到自己）→ 全部识别为重复
    preview_self = c.post("/api/users/u/import/preview", json=export).json()
    assert preview_self["counts"]["checkins"]["duplicates"] == 1


def test_import_apply_roundtrip_rollback_and_isolation(client):
    c, db = client
    seed_full(c, db)
    export = c.post("/api/users/u/export",
                    json={"format": "json", "confirm": True}).json()
    db.save_profile("v", profile())
    # 未确认 → 拒绝
    r0 = c.post("/api/users/v/import/apply", json={"backup": export})
    assert r0.status_code == 422
    # 确认导入 → 数据一致
    r = c.post("/api/users/v/import/apply",
               json={"backup": export, "confirmed": True})
    assert r.status_code == 200, r.text
    assert r.json()["inserted"]["checkins"] == 1
    from coach.analytics.exercise_metrics import exercise_sessions
    sessions_v = exercise_sessions(db, "v", "barbell_bench_press")
    assert len(sessions_v) == 1
    assert sessions_v[0]["reps_total"] == 48
    # 计划版本导入为非激活：不改变 v 的当前生效版本
    assert db.get_active_plan_record("v") is None
    # 重复导入 → 幂等跳过
    again = c.post("/api/users/v/import/apply",
                   json={"backup": export, "confirmed": True}).json()
    assert again["inserted"]["checkins"] == 0
    # 用户隔离：v 导入的数据与 u 互不可见
    assert c.get("/api/users/v/expert-insights").status_code == 200
    mine = c.get("/api/users/u/checkins?limit=50").json()["checkins"]
    theirs = c.get("/api/users/v/checkins?limit=50").json()["checkins"]
    assert {x["id"] for x in mine}.isdisjoint({x["id"] for x in theirs})
    # 失败事务回滚：坏行导致中途异常，库中无残留
    bad = json.loads(json.dumps(export))
    bad["user_data"]["meals"] = [{"local_date": None, "meal_type": "lunch",
                                  "items": []}]
    bad["integrity_manifest"] = bad["integrity_manifest"]  # 完整性按坏数据重算
    from coach.data_transfer import export_service
    bad["integrity_manifest"] = export_service._integrity(bad)
    rb = c.post("/api/users/v/import/apply",
                json={"backup": bad, "confirmed": True})
    assert rb.status_code == 422
    assert "未写入任何数据" in rb.json()["detail"]["error"]
    leftovers = db.conn.execute(
        "SELECT COUNT(*) c FROM meal_entries WHERE user_id='v'"
        " AND local_date IS NULL").fetchone()["c"]
    assert leftovers == 0
