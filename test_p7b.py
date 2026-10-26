"""P7-B：本地模式的权限硬化测试（越权矩阵）。

本应用当前为「本机/受控局域网单用户模式」：uid 由客户端声明，服务端
只做存在性检查与逐查询 user_id 过滤；统一访问令牌（API_ACCESS_TOKEN）
是网络层边界。这些测试固定「用户 A 不能通过改 URL 读到用户 B 的任何
数据」这一承诺；互联网多用户模式的身份方案见 docs/p7b-identity-and-access.md。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.plan import generate_plan
from coach.rehab import restriction_service, symptom_service
from test_repair_regressions import profile


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p7b.db")
    with TestClient(app) as c:
        db = app.state.db
        for uid in ("a", "b"):
            db.save_profile(uid, profile())
            db.create_plan(uid, generate_plan(profile()))
        # a 的数据：训练 / 恢复 / 身体 / 症状 / 限制 / 尝试 / 洞察
        logs = [{"type": "weight_reps", "weight_kg": 60, "reps": 10}] * 3
        c.post("/api/users/a/checkins", json={
            "type": "training", "data": {
                "exercises": [{"name": "杠铃平板卧推",
                               "exercise_id": "barbell_bench_press",
                               "set_logs": logs}],
                "session_meta": {"mode": "free",
                                 "local_date": "2026-10-25"}}})
        c.post("/api/users/a/recovery-checkins", json={"data": {
            "local_date": "2026-10-26", "fatigue": 3, "sleep_hours": 7}})
        c.post("/api/users/a/body-measurements", json={
            "measured_at": "2026-10-26T08:00:00", "local_date": "2026-10-26",
            "weight_kg": 75.0, "source": "user"})
        symptom_service.report_episode(db, "a", {
            "body_region": "shoulder", "description": "肩部酸痛两天",
            "onset_at": "2026-10-25"})
        restriction_service.create_restriction(db, "a", {
            "source_type": "user_reported", "source_evidence": "肩痛",
            "restriction_description": "暂不做杠铃卧推",
            "affected_activities": {"regions": [],
                                    "movements": ["barbell_bench_press"]}})
        c.post("/api/users/a/trials", json={
            "change_desc": "卧推加重一档", "reason": "测试",
            "observe": "完成次数", "stop_rule": "3 次训练"})
        c.post("/api/users/a/experts/analysis", json={
            "specialist": "training_science", "params": {
                "checkin_id": 1}})
        yield c, db


def test_b_cannot_read_any_of_a_data(client):
    c, db = client
    b_reads_a = [
        ("训练统计", "/api/users/a/exercise-stats/barbell_bench_press"),
        ("训练事实", "/api/users/a/training-facts"),
        ("进阶候选", "/api/users/a/training-progression/barbell_bench_press"),
        ("洞察列表", "/api/users/a/expert-insights"),
        ("任务列表", "/api/users/a/experts/tasks"),
        ("个人尝试", "/api/users/a/trials"),
        ("训练限制", "/api/users/a/training-restrictions"),
        ("症状事件", "/api/users/a/symptom-episodes"),
        ("周期统计", "/api/users/a/period-summary"),
    ]
    for label, path in b_reads_a:
        resp = c.get(path.replace("/api/users/a/", "/api/users/b/"))
        if resp.status_code != 200:
            continue
        # 200 只允许是"b 自己的数据"（b 的计划也含同名动作，名称不构成泄露）；
        # 关键判据：b 的训练/洞察视图不含 a 的记录内容
        if label in ("训练统计", "训练事实", "周期统计"):
            assert "2026-10-25" not in resp.text or \
                label == "周期统计" and '"checkin_id"' not in resp.text, \
                f"{label} 泄露了 a 的记录"
        if label == "进阶候选":
            prog = resp.json()
            assert prog["context"]["recent_sessions"] == []
            assert prog["context"]["last_actual_performance"] is None
    # 逐域精确断言：b 的视图里没有 a 的记录
    assert all(t["change_desc"] != "卧推加重一档"
               for t in c.get("/api/users/b/trials").json()["trials"])
    assert c.get("/api/users/b/training-restrictions").json() == [] or all(
        "杠铃卧推" not in str(r) for r in
        c.get("/api/users/b/training-restrictions").json())
    a_insights = c.get("/api/users/a/expert-insights").json()["insights"]
    b_insights = c.get("/api/users/b/expert-insights").json()["insights"]
    assert a_insights and not b_insights


def test_b_cannot_touch_a_resources_by_id(client):
    c, db = client
    # a 的洞察：b 不能查看 / 标记已读 / 忽略 / 重新分析
    insight_id = c.get("/api/users/a/expert-insights").json()["insights"][0]["id"]
    for path in (f"/api/users/b/expert-insights/{insight_id}",
                 f"/api/users/b/expert-insights/{insight_id}/view",
                 f"/api/users/b/expert-insights/{insight_id}/dismiss",
                 f"/api/users/b/expert-insights/{insight_id}/regenerate"):
        resp = c.post(path, json={}) if path.endswith(
            ("view", "dismiss", "regenerate")) else c.get(path)
        assert resp.status_code in (404, 422), path
    # b 不能结束 a 的尝试
    a_trial = c.get("/api/users/a/trials").json()["trials"][0]["id"]
    resp = c.post(f"/api/users/b/trials/{a_trial}/end", json={
        "outcome": "x", "decision": "stop"})
    assert resp.status_code == 404
    # b 不能确认 a 的提案（提案按用户隔离）
    a_change = c.post("/api/users/a/changes", json={
        "target": "plan",
        "operations": [{"op": "rename_day", "day": "周一", "new_name": "推日"}],
        "reason": "重命名", "base_version": {"plan_id": 1, "plan_version": 1}})
    assert a_change.status_code == 200
    a_pid = a_change.json()["proposal_id"]
    resp = c.post(f"/api/users/b/changes/{a_pid}/confirm",
                  json={"message": "确认"})
    assert resp.status_code in (404, 422)
    # b 不能读写 a 的纠错
    resp = c.post("/api/users/b/checkins/1/correct", json={
        "expected_revision": 0, "data": {}, "reason": "x", "evidence": "y"})
    assert resp.status_code in (404, 422)  # 拒绝即可（用户隔离由 user_id 过滤保证）


def test_export_is_strictly_own_data(client):
    c, db = client
    export = c.post("/api/users/a/export",
                    json={"format": "json", "confirm": True}).json()
    assert export["exported_for"] == "a"
    text = __import__("json").dumps(export)
    # b 的档案字段不会出现在 a 的导出里
    assert '"user_id": "b"' not in text
    b_export = c.post("/api/users/b/export",
                      json={"format": "json", "confirm": True}).json()
    assert b_export["exported_for"] == "b"
    assert not b_export["user_data"]["checkins"]


def test_access_token_boundary(tmp_path):
    """统一令牌是网络边界：配置后无令牌请求一律 401（/api/health 除外）。"""
    app = create_app(db_path=tmp_path / "p7b-token.db",
                     access_token="secret-token")
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/users/a/profile").status_code == 401
    assert c.get("/api/users/a/profile",
                 headers={"X-Access-Token": "wrong"}).status_code == 401
    db = app.state.db
    db.save_profile("a", profile())
    ok = c.get("/api/users/a/profile",
               headers={"X-Access-Token": "secret-token"})
    assert ok.status_code == 200


def test_account_deletion_removes_user_data(client):
    """数据自主：删除账户后该用户数据不可再读（P7-B 最小闭环）。"""
    c, db = client
    if not hasattr(db, "delete_user"):
        pytest.skip("delete_user 尚未实现")
    resp = c.delete("/api/users/a/account?confirm=DELETE")
    assert resp.status_code == 200
    assert c.get("/api/users/a/profile").status_code == 404
