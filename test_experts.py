"""P0 专家平台回归：任务调度 / 洞察生命周期 / 证据校验 / 失效 / 确认协议。

覆盖 2.0 §2 P0 验收的完整链路：
WorkoutSaved → 确定性训练科学分析 → ExpertInsight（可追溯）→ 用户查看/忽略/
重新分析；修改计划必须经统一修改协议确认；纠错与计划变更触发失效；
用户隔离；幂等；恢复；失败不阻塞打卡。
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.changes import submit_manual
from coach.db import Database
from coach.experts import (evidence_validator, insight_service,
                           recommendation_service, task_dispatcher)
from coach.plan import generate_plan
from test_repair_regressions import profile

BENCH = "barbell_bench_press"


# ---- 种子工具 ----

def make_db(tmp_path, uid="exp") -> Database:
    db = Database(tmp_path / "test.db")
    db.save_profile(uid, profile())
    db.create_plan(uid, generate_plan(profile()))
    return db


def bench_entry(weight: float, reps: int = 5, sets: int = 3, rpe=None) -> dict:
    logs = [{"type": "weight_reps", "weight_kg": weight, "reps": reps,
             "rpe": rpe, "warmup": False} for _ in range(sets)]
    return {"name": "杠铃平板卧推", "exercise_id": BENCH, "set_logs": logs}


def save_session(db, uid, local_date: str, weight: float, reps=5, sets=3,
                 rpe=None) -> int:
    """历史会话（session_meta.local_date 定日期，绕开 created_at=now）。"""
    return db.record_checkin(uid, "training", {
        "exercises": [bench_entry(weight, reps, sets, rpe)],
        "raw": f"test {local_date}",
        "session_meta": {"session_id": f"s-{local_date}", "mode": "free",
                         "local_date": local_date}})


def seed_progressive(uid, db, weeks=5, start_weight=60.0) -> int:
    """weeks 次递增卧推（每次 +2.5kg），返回最后一次 checkin_id。"""
    last = None
    for i in range(weeks):
        d = (date.today() - timedelta(days=7 * (weeks - i))).isoformat()
        last = save_session(db, uid, d, start_weight + 2.5 * i)
    return last


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "api.db")
    with TestClient(app) as c:
        app.state.db.save_profile("u1", profile())
        app.state.db.create_plan("u1", generate_plan(profile()))
        app.state.db.save_profile("u2", profile())
        yield c, app.state.db


# ---- 端到端：WorkoutSaved → 训练科学分析 → 可追溯洞察 ----

def test_post_workout_review_end_to_end(tmp_path):
    db = make_db(tmp_path)
    last = seed_progressive("exp", db)
    created = task_dispatcher.on_event(db, "exp", "WorkoutSaved",
                                       {"checkin_id": last})
    # P2：训练保存同时通知训练科学与恢复顾问；无恢复记录时恢复侧如实失败
    assert len(created) == 2
    task = next(t for t in created if t["specialist"] == "training_science")
    assert task["status"] == "ready" and task["insight_id"]
    recovery_task = next(t for t in created if t["specialist"] == "recovery")
    assert recovery_task["status"] == "failed"  # 无恢复记录：如实失败不伪造
    insights = insight_service.list_insights(db, "exp")
    assert len(insights) == 1
    ins = insight_service.get_insight(db, "exp", insights[0]["id"])  # 详情含完整载荷
    # 可追溯：发现引用的 fact_id 全部在事实快照内；source_ids 指向真实打卡
    snap_ids = {f["fact_id"] for f in ins["facts_snapshot"]["facts"]}
    assert ins["evidence_refs"] and set(ins["evidence_refs"]) <= snap_ids
    for f in ins["findings"]:
        assert set(f["fact_ids"]) <= snap_ids
        assert f["source_ids"] and f["evidence"] == "verified"
    # 方案纪律：永远有「延续当前安排」；递增趋势给出加重的参考方向
    titles = [o["option_id"] for o in ins["options"]]
    assert "keep-current" in titles
    assert "try-heavier" in titles
    # 置信度：5 次会话、无纠错、间隔 7 天 → high，且 basis 写明规则
    assert ins["confidence"] == "high"
    assert "置信度规则" in ins["confidence_basis"]
    # 趋势为上行（数值来自事实，不是编造）
    assert any("上行" in f["text"] for f in ins["findings"])


def test_first_workout_low_confidence_no_trend(tmp_path):
    db = make_db(tmp_path)
    cid = save_session(db, "exp", date.today().isoformat(), 60)
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": cid})
    ins = insight_service.get_insight(
        db, "exp", insight_service.list_insights(db, "exp")[0]["id"])
    assert ins["confidence"] == "low"
    assert [o["option_id"] for o in ins["options"]] == ["keep-current"]
    assert any("首次" in f["text"] or "不足" in f["text"] for f in ins["findings"])


def test_api_save_workout_triggers_insight_today_visible(client):
    c, _ = client
    payload = {"type": "training", "data": {
        "exercises": [bench_entry(70, 5, 3, rpe=8)],
        "session_meta": {"mode": "free", "local_date": date.today().isoformat()}}}
    resp = c.post("/api/users/u1/checkins", json=payload)
    assert resp.status_code == 200
    listed = c.get("/api/users/u1/expert-insights").json()["insights"]
    assert len(listed) == 1 and listed[0]["status"] == "ready"
    assert listed[0]["specialist"] == "training_science"
    tasks = c.get("/api/users/u1/experts/tasks").json()["tasks"]
    ts = next(t for t in tasks if t["specialist"] == "training_science")
    assert ts["status"] == "ready" and ts["trigger_source"] == "WorkoutSaved"


def test_event_idempotent_same_checkin_not_reanalyzed(tmp_path):
    db = make_db(tmp_path)
    last = seed_progressive("exp", db, weeks=3)
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    tasks = db.list_expert_tasks("exp")
    # dedup_key 唯一约束：同一事件重放不重复分析（每顾问各一条）
    assert len(tasks) == 2
    assert len({t["specialist"] for t in tasks}) == 2
    assert len(db.list_expert_insights("exp")) == 1


# ---- 洞察生命周期：已读 / 忽略 / 重新分析 / 到期 ----

def test_view_dismiss_regenerate(tmp_path):
    db = make_db(tmp_path)
    last = seed_progressive("exp", db, weeks=3)
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    first = insight_service.list_insights(db, "exp")[0]
    # 已读
    viewed = insight_service.mark_viewed(db, "exp", first["id"])
    assert viewed["status"] == "viewed" and viewed["read_at"]
    # 重新分析（UserRequested 不受 proactive 开关限制）
    result = insight_service.regenerate(db, "exp", first["id"])
    assert result["task"]["status"] == "ready"
    assert result["insight"]["id"] != first["id"]
    # 旧的仍是 viewed 历史，不删除
    statuses = {i["id"]: i["status"] for i in insight_service.list_insights(db, "exp")}
    assert statuses[first["id"]] == "viewed"
    # 忽略
    dismissed = insight_service.dismiss(db, "exp", result["insight"]["id"])
    assert dismissed["status"] == "dismissed"
    # dismissed 不能重复忽略
    with pytest.raises(ValueError):
        insight_service.dismiss(db, "exp", result["insight"]["id"])


def test_expired_by_expiry_date(tmp_path):
    db = make_db(tmp_path)
    last = seed_progressive("exp", db, weeks=2)
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    ins = db.get_expert_insight("exp", db.list_expert_insights("exp")[0]["id"])
    db.conn.execute(
        "UPDATE expert_insights SET expires_at=? WHERE id=?",
        ((date.today() - timedelta(days=1)).isoformat(), ins["id"]))
    db.conn.commit()
    fresh = insight_service.get_insight(db, "exp", ins["id"])
    assert fresh["status"] == "expired"


# ---- 失效：纠错 / 计划变更（懒判定，读取时必然生效） ----

def test_checkin_correction_invalidates_insight(client):
    c, db = client
    for i, w in enumerate((60, 62.5, 65)):
        save_session(db, "u1", (date.today() - timedelta(days=7 * (3 - i))).isoformat(), w)
    last = save_session(db, "u1", date.today().isoformat(), 67.5)
    resp = c.post("/api/users/u1/checkins", json={
        "type": "training",
        "data": {"exercises": [bench_entry(67.5, 5, 3)],
                 "session_meta": {"mode": "free", "local_date": date.today().isoformat()}}})
    assert resp.status_code == 200
    ins = c.get("/api/users/u1/expert-insights").json()["insights"][0]
    # 纠错该洞察引用的训练记录
    cur = c.get(f"/api/users/u1/checkins?limit=1").json()["checkins"][0]
    target = cur if cur["data"]["exercises"] else None
    assert target is not None
    revised = c.post(f"/api/users/u1/checkins/{target['id']}/correct", json={
        "expected_revision": target["revision"],
        "data": {**target["data"], "exercises": [bench_entry(50, 5, 3)]},
        "reason": "记错重量", "evidence": "用户说其实举的是 50kg"})
    assert revised.status_code == 200
    stale = c.get(f"/api/users/u1/expert-insights/{ins['id']}").json()
    assert stale["status"] == "invalidated"
    assert "纠错" in stale["status_reason"]


def test_plan_change_invalidates_insight(tmp_path):
    db = make_db(tmp_path)
    last = seed_progressive("exp", db, weeks=3)
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    ins = insight_service.list_insights(db, "exp")[0]
    assert ins["source_revision"]["plan_version"] is not None
    day = db.get_active_plan("exp")["schedule"][0]["day"]
    rec = db.get_active_plan_record("exp")
    submit_manual(db, "exp", "plan",
                  [{"op": "add_exercise", "day": day, "exercise": "plank",
                    "sets": 3, "reps": "30秒"}],
                  "加核心", {"plan_id": rec["id"], "plan_version": rec["version"]})
    fresh = insight_service.get_insight(db, "exp", ins["id"])
    assert fresh["status"] == "invalidated"
    assert "计划已更新" in fresh["status_reason"]


# ---- 任务系统：取消 / 恢复 / 频率限制 / 主动分析开关 ----

def test_cancel_pending_task(tmp_path):
    db = make_db(tmp_path)
    last = save_session(db, "exp", date.today().isoformat(), 60)
    task = task_dispatcher.enqueue(db, "exp", "training_science",
                                   "post-workout-review", "UserRequested",
                                   {"checkin_id": last})
    assert task["status"] == "pending"
    db.update_expert_task("exp", task["id"], status="cancelled",
                          event="cancelled", event_detail="test")
    results = task_dispatcher.run_pending(db, "exp")
    assert all(r.get("skipped") or r["task"]["status"] != "ready"
               for r in results if r["task"]["id"] == task["id"]) or not any(
        r["task"]["id"] == task["id"] for r in results)


def test_recovery_stale_running_tasks(tmp_path):
    db = make_db(tmp_path)
    last = save_session(db, "exp", date.today().isoformat(), 60)
    task = task_dispatcher.enqueue(db, "exp", "training_science",
                                   "post-workout-review", "UserRequested",
                                   {"checkin_id": last})
    stale = (date.today() - timedelta(days=1)).isoformat()
    db.conn.execute(
        "UPDATE expert_tasks SET status='running', heartbeat_at=? WHERE id=?",
        (stale, task["id"]))
    db.conn.commit()
    task_dispatcher.recover_stale(db)
    assert db.get_expert_task("exp", task["id"])["status"] == "pending"
    # 重试次数用尽 → failed(INTERRUPTED)
    db.conn.execute(
        "UPDATE expert_tasks SET status='running', heartbeat_at=?, retry_count=max_retries"
        " WHERE id=?", (stale, task["id"]))
    db.conn.commit()
    task_dispatcher.recover_stale(db)
    failed = db.get_expert_task("exp", task["id"])
    assert failed["status"] == "failed" and failed["error_code"] == "INTERRUPTED"


def test_proactive_off_blocks_events_but_not_user_requests(tmp_path):
    db = make_db(tmp_path)
    db.save_expert_settings("exp", False, 0)
    last = save_session(db, "exp", date.today().isoformat(), 60)
    created = task_dispatcher.on_event(db, "exp", "WorkoutSaved",
                                       {"checkin_id": last})
    assert created == [] and db.list_expert_tasks("exp") == []
    # 用户主动请求不受开关限制
    task = task_dispatcher.enqueue(db, "exp", "training_science",
                                   "post-workout-review", "UserRequested",
                                   {"checkin_id": last})
    assert task and task["status"] == "pending"


def test_frequency_limit_skips_rapid_duplicates(tmp_path):
    db = make_db(tmp_path)
    db.save_expert_settings("exp", True, 60)
    last = save_session(db, "exp", date.today().isoformat(), 60)
    first = task_dispatcher.enqueue(db, "exp", "training_science",
                                    "post-workout-review", "UserRequested",
                                    {"checkin_id": last})
    assert first["status"] == "pending"
    again = task_dispatcher.enqueue(db, "exp", "training_science",
                                    "post-workout-review", "UserRequested",
                                    {"checkin_id": last})
    assert again is None  # 60 分钟内同类任务仍在队列 → 频率限制拦截
    task_dispatcher.run_task(db, first)  # 执行完（ready）后不再占用队列
    third = task_dispatcher.enqueue(db, "exp", "training_science",
                                    "post-workout-review", "UserRequested",
                                    {"checkin_id": last})
    assert third and third["status"] == "pending"


# ---- 确认协议：方案 → pending 提案 → 用户确认才生效 ----

def test_option_to_proposal_requires_confirmation(tmp_path):
    db = make_db(tmp_path)
    day = db.get_active_plan("exp")["schedule"][0]["day"]
    rec = db.get_active_plan_record("exp")
    # 卧推在计划内在册（加重方案才能生成提案提示）
    submit_manual(db, "exp", "plan",
                  [{"op": "add_exercise", "day": day, "exercise": "卧推",
                    "sets": 3, "reps": 5, "weight_kg": 60}],
                  "加卧推", {"plan_id": rec["id"], "plan_version": rec["version"]})
    last = seed_progressive("exp", db, weeks=4)
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    ins = insight_service.get_insight(
        db, "exp", insight_service.list_insights(db, "exp")[0]["id"])
    heavier = next(o for o in ins["options"] if o["option_id"] == "try-heavier")
    assert heavier["action"] == "proposal" and heavier["proposal_hint"]
    staged = recommendation_service.stage_option_proposal(
        db, "exp", ins["id"], "try-heavier")
    assert staged["proposal"]["status"] == "pending"
    # 提案未确认前计划不变
    assert db.get_active_plan_record("exp")["version"] == rec["version"] + 1
    from coach.changes import confirm_proposal
    result = confirm_proposal(db, "exp", staged["proposal"]["proposal_id"],
                              "确认按这个方案加重")
    assert result["status"] == "applied" and result["plan_version"] > rec["version"] + 1
    entry = next(e for d in db.get_active_plan("exp")["schedule"]
                 for e in d["exercises"] if e["exercise_id"] == BENCH)
    assert entry["weight_kg"] == heavier["proposal_hint"]["operations"][0]["weight_kg"]
    # 方案里没有提案提示的（keep-current）不能转提案
    with pytest.raises(ValueError):
        recommendation_service.stage_option_proposal(db, "exp", ins["id"],
                                                     "keep-current")


# ---- 失败处理：专家异常不阻塞打卡；输入问题不重试 ----

def test_analyzer_failure_does_not_block_checkin(client, monkeypatch):
    c, db = client
    import coach.experts.training_science as ts

    def boom(analyzer_db, user_id, refs):
        raise RuntimeError("analysis exploded")

    monkeypatch.setattr(ts, "analyze_post_workout", boom)
    resp = c.post("/api/users/u1/checkins", json={
        "type": "training",
        "data": {"exercises": [bench_entry(70)],
                 "session_meta": {"mode": "free", "local_date": date.today().isoformat()}}})
    assert resp.status_code == 200  # 打卡主流程不受专家失败影响
    task = next(t for t in db.list_expert_tasks("u1")
                if t["specialist"] == "training_science")
    assert task["status"] == "pending"  # 可重试失败：留在队列
    assert task["retry_count"] == 1
    # 重试用尽 → failed 留痕
    task_dispatcher.run_pending(db, "u1")
    task_dispatcher.run_pending(db, "u1")
    task = db.get_expert_task("u1", task["id"])
    assert task["status"] == "failed" and task["error_code"] == "EXECUTION_ERROR"
    events = db.expert_task_events(task["id"])
    assert any(e["event"] == "retry" for e in events)


def test_missing_checkin_fails_without_retry(tmp_path):
    db = make_db(tmp_path)
    task = task_dispatcher.enqueue(db, "exp", "training_science",
                                   "post-workout-review", "UserRequested",
                                   {"checkin_id": 9999})
    result = task_dispatcher.run_task(db, task)
    assert result["task"]["status"] == "failed"
    assert result["task"]["error_code"] == "INPUT_INVALID"


# ---- 用户隔离 ----

def test_user_isolation(client):
    c, db = client
    save_session(db, "u1", date.today().isoformat(), 70)
    resp = c.post("/api/users/u1/checkins", json={
        "type": "training",
        "data": {"exercises": [bench_entry(70)],
                 "session_meta": {"mode": "free", "local_date": date.today().isoformat()}}})
    assert resp.status_code == 200
    ins = c.get("/api/users/u1/expert-insights").json()["insights"]
    assert ins
    # 用户 B 看不到 A 的洞察/任务（404 / 空列表）
    assert c.get(f"/api/users/u2/expert-insights/{ins[0]['id']}").status_code == 404
    assert c.get("/api/users/u2/expert-insights").json()["insights"] == []
    assert c.get("/api/users/u2/experts/tasks").json()["tasks"] == []
    task_id = db.list_expert_tasks("u1")[0]["id"]
    assert c.get(f"/api/users/u2/experts/tasks/{task_id}").status_code == 404
    assert c.post(f"/api/users/u2/expert-insights/{ins[0]['id']}/dismiss").status_code == 404


# ---- 证据校验：编造引用被剔除 ----

def test_evidence_validator_drops_fabricated_refs(tmp_path):
    db = make_db(tmp_path)
    payload = {
        "facts_snapshot": {"facts": [{"fact_id": "volume-bench-1"}]},
        "findings": [
            {"finding_id": "f1", "text": "真事实", "fact_ids": ["volume-bench-1"],
             "source_ids": []},
            {"finding_id": "f2", "text": "编造引用", "fact_ids": ["nope-123"],
             "source_ids": ["checkin:99999:revision:0"]},
        ],
        "evidence_refs": ["volume-bench-1", "nope-123"],
    }
    cleaned = evidence_validator.validate_evidence(payload, db, "exp")
    assert cleaned["findings"][0]["evidence"] == "verified"
    f2 = cleaned["findings"][1]
    assert f2["fact_ids"] == [] and f2["source_ids"] == []
    assert f2["evidence"] == "unverified"
    assert cleaned["evidence_refs"] == ["volume-bench-1"]
    report = cleaned["evidence_report"]
    assert report["dropped_fact_refs"] == 1 and report["dropped_source_refs"] == 1


def test_confidence_downgrades_with_corrections(tmp_path):
    db = make_db(tmp_path)
    last = seed_progressive("exp", db, weeks=4)
    # 纠错中间一条记录 → corrected>0 → high 降 medium
    mid = db.conn.execute(
        "SELECT id FROM checkins WHERE user_id='exp' AND type='training'"
        " ORDER BY id LIMIT 1 OFFSET 1").fetchone()["id"]
    original = db.get_checkin("exp", mid)
    db.revise_checkin("exp", mid, original["revision"], original["data"],
                      "修正", "记错了")
    task_dispatcher.on_event(db, "exp", "WorkoutSaved", {"checkin_id": last})
    ins = insight_service.list_insights(db, "exp")[0]
    assert ins["confidence"] == "medium"
    assert "纠错" in ins["confidence_basis"]


def test_overview_lists_registry_and_settings(client):
    c, _ = client
    body = c.get("/api/users/u1/experts/overview").json()
    labels = {s["specialist"]: s for s in body["specialists"]}
    assert set(labels) == {"training_science", "nutrition", "recovery",
                           "rehabilitation", "movement", "collaboration"}
    assert labels["training_science"]["workbench"] == "ready"
    assert labels["nutrition"]["workbench"] == "ready"          # P1 已上线
    assert labels["recovery"]["workbench"] == "ready"           # P2 已上线
    assert labels["rehabilitation"]["workbench"] == "ready"        # P3 已上线
    assert labels["movement"]["workbench"] == "ready"             # P4 已上线
    assert labels["collaboration"]["workbench"] == "ready"        # P6 已上线
    assert body["settings"]["proactive_enabled"] is True
    # 关闭主动分析
    resp = c.post("/api/users/u1/experts/settings",
                  json={"proactive_enabled": False, "min_interval_minutes": 0})
    assert resp.json()["proactive_enabled"] is False
