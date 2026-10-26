"""P7-C：设备数据只读文件导入回归。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from test_repair_regressions import profile

CSV = (
    "metric,value,unit,measured_at,source_platform,source_device,"
    "source_record_id,measurement_method\n"
    "weight,75.5,kg,2026-10-20T08:00:00,healthkit,Apple Watch,hk-1,scale\n"
    "weight,168.0,lb,2026-10-21T08:00:00,healthkit,Apple Watch,hk-2,scale\n"
    "sleep_hours,420,min,2026-10-21T23:30:00,healthkit,iPhone,hk-3,estimated\n"
    "steps,12345,count,2026-10-21T23:30:00,health_connect,Pixel,hc-1,estimated\n"
)


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p7c.db")
    with TestClient(app) as c:
        db = app.state.db
        db.save_profile("u", profile())
        yield c, db


def test_device_import_csv_roundtrip_units_and_dedupe(client):
    c, db = client
    preview = c.post("/api/users/u/device-import/preview",
                     json={"format": "csv", "content": CSV}).json()
    assert preview["rows_total"] == 4
    assert preview["rows_to_insert"] == 4
    assert preview["duplicates"] == 0
    assert preview["metrics"] == ["sleep_hours", "steps", "weight"]
    assert preview["requires_confirmation"] is True

    applied = c.post("/api/users/u/device-import/apply",
                     json={"format": "csv", "content": CSV,
                           "confirmed": True}).json()
    assert applied["inserted"] == 4
    records = c.get("/api/users/u/device-import/records?metric=weight") \
        .json()["records"]
    assert len(records) == 2
    # lb → kg 确定性换算
    assert {round(r["value"], 2) for r in records} == {75.5, 76.2}
    assert all(r["unit"] == "kg" for r in records)
    # min → h 换算
    sleep = c.get("/api/users/u/device-import/records?metric=sleep_hours") \
        .json()["records"]
    assert round(sleep[0]["value"], 2) == 7.0
    # 重复导入 → 全部去重
    again = c.post("/api/users/u/device-import/apply",
                   json={"format": "csv", "content": CSV,
                         "confirmed": True}).json()
    assert again["inserted"] == 0 and again["duplicates"] == 4


def test_device_import_rejects_unknown_metric_and_unit(client):
    c, db = client
    bad_metric = ("metric,value,unit,measured_at,source_platform,"
                  "source_record_id\n"
                  "blood_pressure,120,mmHg,2026-10-20T08:00:00,hk,hk-9\n")
    r = c.post("/api/users/u/device-import/preview",
               json={"format": "csv", "content": bad_metric})
    assert r.status_code == 422 and "白名单" in r.json()["detail"]["error"]
    bad_unit = ("metric,value,unit,measured_at,source_platform,"
                "source_record_id\n"
                "weight,75,stone,2026-10-20T08:00:00,hk,hk-9\n")
    r2 = c.post("/api/users/u/device-import/preview",
                json={"format": "csv", "content": bad_unit})
    assert r2.status_code == 422 and "单位" in r2.json()["detail"]["error"]


def test_device_import_isolated_from_manual_records(client):
    """设备数据独立存储：不与手动身体测量混算（防重复统计）。"""
    c, db = client
    c.post("/api/users/u/device-import/apply",
           json={"format": "csv", "content": CSV, "confirmed": True})
    c.post("/api/users/u/body-measurements", json={
        "measured_at": "2026-10-20T08:00:00", "local_date": "2026-10-20",
        "weight_kg": 74.0, "source": "user"})
    # 手动测量表只有 1 条（设备 75.5 不混入 body_measurements）
    rows = db.conn.execute(
        "SELECT COUNT(*) c FROM body_measurements WHERE user_id='u'"
    ).fetchone()["c"]
    assert rows == 1
    imported = c.get("/api/users/u/device-import/records").json()["records"]
    assert len(imported) == 4


def test_device_import_revoke_by_platform(client):
    c, db = client
    c.post("/api/users/u/device-import/apply",
           json={"format": "csv", "content": CSV, "confirmed": True})
    r = c.request("DELETE", "/api/users/u/device-import/records",
                  json={"source_platform": "healthkit"})
    assert r.json()["deleted"] == 3
    left = c.get("/api/users/u/device-import/records").json()["records"]
    assert len(left) == 1 and left[0]["source_platform"] == "health_connect"
