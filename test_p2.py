"""P2 回归：身体数据 / 恢复记录 / 确定性分析 / 训练前简报 / 联动 / 迁移。

覆盖任务书三场景：
A. 身体数据管理（记录→趋势→编辑→修订保留→旧分析失效→新分析用新数据）
B. 恢复顾问独立工作（连续记录→训练→洞察→工作台数据，全程无聊天）
C. 营养×身体×恢复联合观察（各专家只用对应领域有效数据，不编造）
"""
import json
import pytest
from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.body import measurement_service, trend_service
from coach.db import Database
from coach.experts import insight_service, task_dispatcher
from coach.recovery import checkin_service, recovery_analysis
from test_repair_regressions import profile

TODAY = date.today().isoformat()
D = lambda n: (date.today() - timedelta(days=n)).isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p2.db")
    with TestClient(app) as c:
        app.state.db.save_profile("u", profile())
        app.state.db.save_profile("other", profile())
        yield c, app.state.db


# ---- 场景 A：身体数据管理 ----

def test_body_record_trend_edit_revision_invalidation(client):
    c, db = client
    # 记录三次体重与腰围（API + 旧接口转发两条路径）
    for i, (w, waist) in enumerate([(74.8, 82), (74.2, 81.5), (73.6, 81.0)]):
        resp = c.post("/api/users/u/body-measurements", json={
            "data": {"weight_kg": w, "waist_cm": waist, "local_date": D(10 - i * 5),
                     "measurement_method": "home_scale", "device_source": "家用秤A"}})
        assert resp.status_code == 200
    # 旧接口（checkins body 类型）同样进入测量表（单一权威存储）
    legacy = c.post("/api/users/u/checkins", json={
        "type": "body", "data": {"weight_kg": 73.0, "note": "顺手记一次"}})
    assert legacy.status_code == 200
    rows = db.list_body_measurements("u")
    assert len(rows) == 4 and all(m["migrated_from"] is None for m in rows[:3])
    assert legacy.json()["id"] == rows[0]["id"]  # 返回测量 id

    # 趋势：74.8(D10)→…→73.6(D0)→73.0(今天 legacy)，首末 -1.8
    trend = c.get("/api/users/u/body-trend",
                  params={"metric": "weight_kg", "days": 30}).json()
    assert trend["change"]["delta"] == pytest.approx(-1.8, abs=0.01)
    waist_trend = c.get("/api/users/u/body-trend",
                        params={"metric": "waist_cm", "days": 30}).json()
    assert waist_trend["change"]["delta"] == pytest.approx(-1.0, abs=0.01)

    # 编辑第二次（D5 那条）→ 修订保留 + 统计更新
    target = next(m for m in rows if m["local_date"] == D(5))
    resp = c.patch(f"/api/users/u/body-measurements/{target['id']}", json={
        "expected_revision": target["revision"],
        "data": {"weight_kg": 75.0, "waist_cm": 82.5, "local_date": target["local_date"],
                 "measurement_method": "home_scale"},
        "reason": "记错了", "evidence": "用户说其实是 75kg"})
    assert resp.status_code == 200 and resp.json()["weight_kg"] == 75.0
    revisions = c.get(f"/api/users/u/body-measurements/{target['id']}/revisions").json()
    assert revisions["revisions"][0]["revision"] == 1
    # 趋势用新值：74.8(D10) → 75.0(D5 修订) → 73.6(D0) → 73.0(legacy)
    trend2 = c.get("/api/users/u/body-trend",
                   params={"metric": "weight_kg", "days": 30}).json()
    assert trend2["change"]["first"] == pytest.approx(74.8)
    assert trend2["change"]["delta"] == pytest.approx(73.0 - 74.8, abs=0.01)
    assert 75.0 in [p["value"] for p in trend2["points"]]  # 修订值在序列中
    # 修订错版本号拒绝
    bad = c.patch(f"/api/users/u/body-measurements/{target['id']}", json={
        "expected_revision": 0, "data": {"weight_kg": 70},
        "reason": "x", "evidence": "y"})
    assert bad.status_code == 422 and "已被修订" in bad.json()["detail"]["error"]

    # 汇总：编辑后均值/变化反映新值；来源可比性说明存在
    summary = c.get("/api/users/u/body-summary", params={"days": 30}).json()
    weight_avg = next(f for f in summary["facts"] if f["metric"] == "weight_kg-avg")
    assert weight_avg["value"] == pytest.approx((74.8 + 75.0 + 73.6 + 73.0) / 4, abs=0.01)
    assert any("不默认可比" in lim or "波动" in lim for lim in summary["limitations"])

    # 校验纪律：无指标拒绝；成分数据必须带方法；越界拒绝
    assert c.post("/api/users/u/body-measurements",
                  json={"data": {"notes": "只有备注"}}).status_code == 422
    assert c.post("/api/users/u/body-measurements", json={
        "data": {"body_fat_percent": 20}}).status_code == 422  # 缺方法
    assert c.post("/api/users/u/body-measurements", json={
        "data": {"weight_kg": 900, "measurement_method": "home_scale"}}).status_code == 422


def test_body_migration_and_user_isolation(tmp_path):
    db = Database(tmp_path / "mig.db")
    db.save_profile("a", profile())
    db.save_profile("b", profile())
    # 历史遗留：两条旧 body 打卡（其一无法解析也应保留不丢）。
    # 用 add_checkin 直插（模拟 P2 之前写入路径；record_checkin 现已拦截转发）
    db.add_checkin("a", "body", {"weight_kg": 76.0, "waist_cm": 83})
    db.add_checkin("a", "body", {"raw": "纯文本旧记录"})
    assert measurement_service.migrate_legacy_body_checkins(db) == 1  # 可解析的迁移
    assert measurement_service.migrate_legacy_body_checkins(db) == 0  # 幂等
    rows = db.list_body_measurements("a")
    # 1 条迁移 + record_checkin 转发产生的?—— record_checkin 未调用，只有迁移 1 条
    assert len(rows) == 1
    assert rows[0]["migrated_from"].startswith("checkin:")
    assert rows[0]["weight_kg"] == 76.0
    # 原行保留且带标记；无法解析的原样保留不打标
    marker_row = db.conn.execute(
        "SELECT data FROM checkins WHERE type='body' AND data LIKE '%_migrated%'"
    ).fetchone()
    assert json.loads(marker_row["data"])["_migrated"]["measurement_id"] == rows[0]["id"]
    plain_row = db.conn.execute(
        "SELECT data FROM checkins WHERE type='body' AND data NOT LIKE '%_migrated%'"
    ).fetchone()
    assert json.loads(plain_row["data"]).get("raw")
    # 用户隔离
    assert db.list_body_measurements("b") == []
    # 新 body 打卡（record_checkin 拦截）进入测量表且按用户隔离、无 checkin 行
    mid = db.record_checkin("b", "body", {"weight_kg": 60})
    assert db.get_body_measurement("b", mid)["weight_kg"] == 60.0
    assert db.conn.execute(
        "SELECT COUNT(*) FROM checkins WHERE user_id='b'").fetchone()[0] == 0


def test_body_recorded_invalidates_nutrition_insight(client):
    """用户改体重后，引用过该体重的营养分析失效（7.3 统一证据）。"""
    c, db = client
    egg = c.get("/api/nutrition/foods", params={"q": "鸡蛋"}).json()["foods"][0]
    c.post("/api/users/u/meals", json={
        "date": TODAY, "meal_type": "breakfast",
        "items": [{"food_id": egg["id"], "amount": 2, "unit": "个"}]})
    # 先有体重 → 记饮食 → 洞察带体重上下文
    c.post("/api/users/u/body-measurements", json={
        "data": {"weight_kg": 74.0, "local_date": D(1),
                 "measurement_method": "home_scale"}})
    ins = next(i for i in insight_service.list_insights(db, "u", specialist="nutrition")
               if i["status"] == "ready")
    full = insight_service.get_insight(db, "u", ins["id"])
    assert any(f["kind"] == "weight-context" for f in full["findings"])
    assert full["source_revision"].get("body")
    # 编辑体重 → 营养洞察失效
    mid = int(next(iter(full["source_revision"]["body"])))
    measurement_service.update_measurement(
        db, "u", mid, 0, {"weight_kg": 75.5, "local_date": D(1),
                          "measurement_method": "home_scale"},
        "修正", "用户说 75.5")
    stale = insight_service.get_insight(db, "u", ins["id"])
    assert stale["status"] == "invalidated" and "身体测量" in stale["status_reason"]


# ---- 场景 B：恢复顾问独立工作 ----

def seed_recovery(c, days=3, fatigue_seq=(2, 4, 4)):
    for i, fat in enumerate(fatigue_seq):
        c.post("/api/users/u/recovery-checkins", json={"data": {
            "local_date": D(i), "sleep_hours": 7.5 - i * 0.8,
            "sleep_quality": 5 - i, "fatigue": fat,
            "muscle_soreness": min(5, fat),
            "training_readiness": max(1, 5 - i),
            "soreness_regions": ["膝"] if fat >= 4 else []}})


def test_recovery_workflow_no_chat(client):
    c, db = client
    seed_recovery(c)
    # 校验：量表越界拒绝；全空拒绝
    assert c.post("/api/users/u/recovery-checkins",
                  json={"data": {"fatigue": 9}}).status_code == 422
    assert c.post("/api/users/u/recovery-checkins",
                  json={"data": {"notes": ""}}).status_code == 422
    # 只记一项也可以
    solo = c.post("/api/users/u/recovery-checkins", json={
        "data": {"local_date": D(9), "sleep_hours": 6.5}})
    assert solo.status_code == 200
    # 完成一次力量训练（触发训练科学 + 恢复两条链）
    c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 70, "reps": 5,
                                     "rpe": 8, "warmup": False}] * 3}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    insights = [i for i in insight_service.list_insights(db, "u", specialist="recovery")
                if i["status"] == "ready"]
    assert insights, "训练后应产生恢复回顾洞察"
    full = insight_service.get_insight(db, "u", insights[0]["id"])
    # 引用真实记录（训练×恢复），不带综合评分
    assert full["facts_snapshot"]["caliber"].startswith("recovery_metrics")
    load_findings = [f for f in full["findings"] if f["kind"] == "training-load-context"]
    assert load_findings and any("正式组" in f["text"] for f in load_findings)
    assert all(f["evidence"] == "verified" for f in full["findings"])
    text_all = " ".join(f["text"] for f in full["findings"]) + full["summary"]
    assert "过度训练" not in text_all  # 不做医学推断
    # 疲劳 4 的最新记录 → 调整/延后选项出现（可选方向而非指令）
    recs = c.get("/api/users/u/recovery-checkins").json()["checkins"]
    latest = recs[0]
    assert latest["fatigue"] == 2  # 最新=今天(i=0 疲劳2)——种子顺序
    # 汇总接口：观察/数据质量/局限齐备
    summary = c.get("/api/users/u/recovery-summary").json()
    assert summary["records_count"] >= 4
    assert any("均值" in o for o in summary["observations"])
    # 幂等：重放同一次 WorkoutSaved 事件（同 checkin_id）不产生新任务
    n_tasks = len(db.list_expert_tasks("u", specialist="recovery"))
    last_checkin = db.conn.execute(
        "SELECT id FROM checkins WHERE user_id='u' AND type='training'"
        " ORDER BY id DESC LIMIT 1").fetchone()["id"]
    task_dispatcher.on_event(db, "u", "WorkoutSaved", {"checkin_id": last_checkin})
    assert len(db.list_expert_tasks("u", specialist="recovery")) == n_tasks


def test_recovery_update_requires_reason_and_invalidates(client):
    c, db = client
    seed_recovery(c, fatigue_seq=(4, 4, 4))
    ins = next(i for i in insight_service.list_insights(db, "u", specialist="recovery")
               if i["status"] == "ready")
    # 当天已有记录：无 reason 拒绝
    r1 = c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5}})
    assert r1.status_code == 422 and "修改原因" in r1.json()["detail"]["error"]
    r2 = c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5,
        "reason": "下午更累", "evidence": "用户补充：下午特别累"}})
    assert r2.status_code == 200 and r2.json()["revision"] == 1
    stale = insight_service.get_insight(db, "u", ins["id"])
    assert stale["status"] == "invalidated"
    # 删除恢复记录同样失效
    ins2 = next(i for i in insight_service.list_insights(db, "u", specialist="recovery")
                if i["status"] == "ready")
    rid = db.get_recovery_by_date("u", TODAY)["id"]
    c.delete(f"/api/users/u/recovery-checkins/{rid}")
    assert insight_service.get_insight(db, "u", ins2["id"])["status"] == "invalidated"


def test_training_correction_invalidates_recovery_insight(client):
    """训练记录纠错后，引用其负荷事实的恢复洞察失效（7.2/7.3）。"""
    c, db = client
    seed_recovery(c)
    resp = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 60, "reps": 5,
                                     "warmup": False}] * 3}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    ins = next(i for i in insight_service.list_insights(db, "u", specialist="recovery")
               if i["status"] == "ready")
    full = insight_service.get_insight(db, "u", ins["id"])
    assert full["source_revision"]["checkins"], "应引用训练打卡"
    cur = c.get("/api/users/u/checkins?limit=1").json()["checkins"][0]
    c.post(f"/api/users/u/checkins/{cur['id']}/correct", json={
        "expected_revision": cur["revision"],
        "data": {**cur["data"], "exercises": [dict(
            cur["data"]["exercises"][0],
            set_logs=[{"type": "weight_reps", "weight_kg": 50, "reps": 5,
                       "warmup": False}] * 3)]},
        "reason": "重量记错", "evidence": "用户说其实 50kg"})
    stale = insight_service.get_insight(db, "u", ins["id"])
    assert stale["status"] == "invalidated" and "纠错" in stale["status_reason"]


def test_no_recovery_data_no_fabricated_analysis(client):
    """无恢复记录时不产生洞察，也不从训练量反推疲劳（5.1）。"""
    c, db = client
    c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 60, "reps": 5,
                                     "warmup": False}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert [i for i in insight_service.list_insights(db, "u", specialist="recovery")
            if i["status"] == "ready"] == []
    summary = c.get("/api/users/u/recovery-summary").json()
    assert summary["records_count"] == 0
    assert any("反推" in lim or "先记录" in lim for lim in summary["limitations"])


# ---- 场景 C：联合观察 ----

def test_cross_domain_each_expert_uses_own_data(client):
    c, db = client
    # 体重若干 + 几天饮食（部分完整）+ 睡眠疲劳 + 训练
    c.post("/api/users/u/body-measurements", json={
        "data": {"weight_kg": 75.0, "local_date": D(6),
                 "measurement_method": "home_scale"}})
    c.post("/api/users/u/body-measurements", json={
        "data": {"weight_kg": 74.2, "local_date": D(1),
                 "measurement_method": "home_scale"}})
    c.post("/api/users/u/nutrition/targets", json={"energy_kcal": 2200})
    egg = c.get("/api/nutrition/foods", params={"q": "鸡蛋"}).json()["foods"][0]
    for i in range(2):
        c.post("/api/users/u/meals", json={
            "date": D(i), "meal_type": "dinner",
            "items": [{"food_id": egg["id"], "amount": 2, "unit": "个"}]})
    # D(1) 未标记完整：其分析不声称摄入不足
    day1_ins = next(i for i in
                    insight_service.list_insights(db, "u", specialist="nutrition")
                    if i["status"] == "ready" and D(1) in i["title"])
    day1_full = insight_service.get_insight(db, "u", day1_ins["id"])
    assert any("不声称实际摄入不足" in lim or "未标记记录完整" in lim
               for lim in day1_full["limitations"])
    c.post(f"/api/users/u/nutrition/days/{D(0)}/complete", json={"complete": True})
    seed_recovery(c, fatigue_seq=(3, 4, 4))
    c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 70, "reps": 5,
                                     "warmup": False}] * 3}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    task_dispatcher.run_pending(db, "u")

    # 营养洞察：只引用 meal/体重（不编造睡眠）
    nut = insight_service.get_insight(db, "u", next(
        i["id"] for i in insight_service.list_insights(db, "u", specialist="nutrition")
        if i["status"] == "ready"))
    nut_srcs = {s.split(":")[0] for f in nut["findings"] for s in f["source_ids"]}
    assert "recovery" not in nut_srcs
    assert nut_srcs <= {"meal", "body", "checkin"}
    assert any(f["kind"] == "weight-context" for f in nut["findings"])

    # 恢复洞察：引用 recovery + 训练负荷（不把缺的营养当 0 摄入）
    rec = insight_service.get_insight(db, "u", next(
        i["id"] for i in insight_service.list_insights(db, "u", specialist="recovery")
        if i["status"] == "ready"))
    rec_srcs = {s.split(":")[0] for f in rec["findings"] for s in f["source_ids"]}
    assert "meal" not in rec_srcs and "recovery" in rec_srcs
    assert any("负荷" in f["text"] or "正式组" in f["text"]
               for f in rec["findings"])
    text_all = " ".join(f["text"] for f in rec["findings"])
    assert "摄入" not in text_all  # 恢复顾问不谈营养摄入

    # 训练科学 + 营养 + 恢复三条洞察并存
    specialists = {i["specialist"] for i in
                   insight_service.list_insights(db, "u", limit=50)
                   if i["status"] == "ready"}
    assert {"nutrition", "recovery", "training_science"} <= specialists


# ---- 训练前简报 ----

def test_pre_training_brief_states(client):
    c, db = client
    # 无数据 → clear + 建议先记录
    brief = c.get("/api/users/u/pre-training-recovery-brief").json()
    assert brief["stance"] == "clear" and brief["latest_recovery"] is None
    assert any(o["option_id"] == "record-first" for o in brief["options"])
    # 高疲劳 → caution + 三个可选方向
    c.post("/api/users/u/recovery-checkins", json={"data": {
        "local_date": TODAY, "fatigue": 5, "sleep_hours": 5.5}})
    brief = c.get("/api/users/u/pre-training-recovery-brief").json()
    assert brief["stance"] == "caution" and brief["signals"]
    assert {o["option_id"] for o in brief["options"]} >= {
        "adjust-today", "delay-observe", "maintain-plan"}
    assert "简报由确定性代码生成" in brief["note"]
    # 医疗隔离 → restricted 优先
    db.conn.execute(
        "UPDATE users SET profile=? WHERE user_id='u'",
        (json.dumps({**db.get_existing_profile("u"),
                     "plan_fence": {"reason": "测试隔离"}}, ensure_ascii=False),))
    db.conn.commit()
    brief = c.get("/api/users/u/pre-training-recovery-brief").json()
    assert brief["stance"] == "restricted" and brief["restrictions"]


# ---- 幂等提交 / 导出 / 隔离 ----

def test_submission_idempotency_and_export(client):
    c, _ = client
    first = c.post("/api/users/u/body-measurements", json={
        "data": {"weight_kg": 74}, "submission_id": "sub-1"})
    again = c.post("/api/users/u/body-measurements", json={
        "data": {"weight_kg": 88}, "submission_id": "sub-1"})
    assert first.json()["measurement_id"] == again.json()["measurement_id"]
    assert again.json()["existing"] is True  # 重放不覆盖成 88
    r_first = c.post("/api/users/u/recovery-checkins", json={
        "data": {"local_date": D(3), "fatigue": 3}, "submission_id": "sub-2"})
    r_again = c.post("/api/users/u/recovery-checkins", json={
        "data": {"local_date": D(3), "fatigue": 5}, "submission_id": "sub-2"})
    assert r_again.json()["existing"] is True
    # 导出（含用户自己的数据；他人不可见）
    data = c.get("/api/users/u/body-measurements").json()["measurements"]
    assert data and all(m["weight_kg"] is not None for m in data)
    other = c.get("/api/users/other/body-measurements").json()["measurements"]
    assert other == []
    assert c.get("/api/users/other/recovery-summary").json()["records_count"] == 0
