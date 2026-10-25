"""P1 营养系统回归：食物库 / 确定性计算 / 餐次记录 / 目标 / 营养顾问洞察。

覆盖 2.0 §三 P1 验收：
搜索食物 → 记录三餐 → 编辑份量 → 查看营养统计 → 营养顾问 → 分析依据 →
比较方案 → 自主决定。核心断言：
- 计算可复现（快照口径）且份量修改后统计更新；
- 不完整记录不产生虚假的摄入判断（方向性建议降级为补齐记录）；
- 未知营养素保留缺失，绝不用 0 冒充；
- 自定义食物按用户隔离；
- 全程无 LLM（确定性链路）。
"""
import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.db import Database
from coach.experts import insight_service
from coach.nutrition import meal_service
from test_repair_regressions import profile

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "nutri.db")
    with TestClient(app) as c:
        app.state.db.save_profile("nu", profile())
        app.state.db.save_profile("other", profile())
        yield c, app.state.db


def food_id(c, q: str) -> str:
    hits = c.get("/api/nutrition/foods", params={"q": q}).json()["foods"]
    assert hits, f"搜索不到 {q}"
    return hits[0]["id"]


def record(c, day, meal_type, items, notes=""):
    return c.post("/api/users/nu/meals", json={
        "date": day, "meal_type": meal_type, "items": items, "notes": notes})


# ---- 食物库 ----

def test_builtin_catalog_loaded_and_chinese_search(client):
    c, _ = client
    body = c.get("/api/nutrition/foods", params={"q": "鸡蛋"}).json()
    names = [f["name"] for f in body["foods"]]
    assert "鸡蛋" in names and "鸡蛋白" in names
    assert body["foods"][0]["source_name"]  # 来源声明必须存在
    alias = c.get("/api/nutrition/foods", params={"q": "地瓜"}).json()["foods"]
    assert alias and alias[0]["name"] == "红薯（熟）"
    cats = c.get("/api/nutrition/foods", params={"category": "fruit"}).json()
    assert cats["categories"]["fruit"] == "水果"
    assert all(f["category"] == "fruit" for f in cats["foods"])


def test_custom_food_isolation_and_validation(client):
    c, _ = client
    made = c.post("/api/users/nu/nutrition/foods", json={
        "name": "家乡辣酱", "category": "other",
        "serving_units": [{"unit": "勺", "grams": 15}],
        "energy_kcal": 40, "protein_g": 1})
    assert made.status_code == 200
    fid = made.json()["food_id"]
    # 用户隔离：他人搜索/直取都不可见
    assert all(f["id"] != fid for f in
               c.get("/api/nutrition/foods", params={"q": "家乡辣酱", "uid": "other"}
                     ).json()["foods"])
    assert c.get(f"/api/nutrition/foods/{fid}", params={"uid": "other"}
                 ).status_code == 404
    # 同名（含内置同名）拒绝
    dup = c.post("/api/users/nu/nutrition/foods", json={
        "name": "鸡蛋", "category": "other"})
    assert dup.status_code == 422
    # 非法输入
    assert c.post("/api/users/nu/nutrition/foods", json={
        "name": "x", "category": "not_a_cat"}).status_code == 422
    assert c.post("/api/users/nu/nutrition/foods", json={
        "name": "y", "category": "other", "energy_kcal": -5}).status_code == 422


# ---- 确定性计算 ----

def test_unit_conversion_and_reproducible_math(client):
    c, _ = client
    rice = food_id(c, "米饭（熟）")
    # 1.5 碗 = 300g → 能量 = 116 × 3 = 348 kcal
    resp = record(c, TODAY, "lunch", [{"food_id": rice, "amount": 1.5, "unit": "碗"}])
    assert resp.status_code == 200
    totals = resp.json()["summary"]["totals"]
    assert totals["energy_kcal"] == pytest.approx(348, abs=0.5)
    assert totals["protein_g"] == pytest.approx(7.8, abs=0.1)
    # 未知单位拒绝（不静默按克）
    bad = record(c, TODAY, "snack", [{"food_id": rice, "amount": 1, "unit": "斤"}])
    assert bad.status_code == 422 and "不支持单位" in bad.json()["detail"]["error"]


def test_unknown_nutrient_stays_missing_not_zero(client):
    c, _ = client
    # 自定义食物只录能量，其余未知
    fid = c.post("/api/users/nu/nutrition/foods", json={
        "name": "外卖汤", "category": "other",
        "serving_units": [{"unit": "碗", "grams": 300}],
        "energy_kcal": 90}).json()["food_id"]
    resp = record(c, TODAY, "snack", [{"food_id": fid, "amount": 1, "unit": "碗"}])
    dq = resp.json()["summary"]["data_quality"]
    # 未知项进入 data_quality，而不是被记为 0
    assert "protein_g" in dq and dq["protein_g"]["unknown"] == 1
    summary = c.get("/api/users/nu/nutrition/summary", params={"date": TODAY}).json()
    assert summary["day"]["data_quality"]["protein_g"]["unknown"] == 1
    assert "已记录摄入量" in summary["note"]


def test_edit_amount_updates_totals(client):
    c, _ = client
    rice = food_id(c, "米饭（熟）")
    made = record(c, TODAY, "lunch", [{"food_id": rice, "amount": 1, "unit": "碗"}]).json()
    before = c.get("/api/users/nu/nutrition/summary", params={"date": TODAY}
                   ).json()["day"]["totals"]["energy_kcal"]
    # 编辑份量 1 碗 → 2 碗：统计更新
    upd = c.put(f"/api/users/nu/meals/{made['meal_id']}", json={
        "items": [{"food_id": rice, "amount": 2, "unit": "碗"}], "notes": ""})
    assert upd.status_code == 200
    after = c.get("/api/users/nu/nutrition/summary", params={"date": TODAY}
                  ).json()["day"]["totals"]["energy_kcal"]
    assert after == pytest.approx(before * 2, abs=1)
    # 删除餐次
    assert c.delete(f"/api/users/nu/meals/{made['meal_id']}").status_code == 200
    assert c.get("/api/users/nu/nutrition/summary", params={"date": TODAY}
                 ).json()["day"]["items_count"] == 0


def test_copy_yesterday_and_recipes(client):
    c, _ = client
    rice = food_id(c, "米饭（熟）")
    chicken = food_id(c, "鸡胸肉")
    record(c, YESTERDAY, "lunch", [
        {"food_id": rice, "amount": 1, "unit": "碗"},
        {"food_id": chicken, "amount": 1, "unit": "块"}])
    copied = c.post("/api/users/nu/meals/copy-day",
                    json={"from_date": YESTERDAY, "to_date": TODAY})
    assert copied.json()["copied"] == 1
    today = c.get("/api/users/nu/nutrition/summary", params={"date": TODAY}).json()
    assert today["day"]["items_count"] == 2  # 快照原样复制
    # 食谱保存与复用
    recipe = c.post("/api/users/nu/nutrition/recipes", json={
        "name": "练后餐", "items": [
            {"food_id": rice, "amount": 1, "unit": "碗"},
            {"food_id": chicken, "amount": 1, "unit": "块"}]})
    assert recipe.status_code == 200
    recipes = c.get("/api/users/nu/nutrition/recipes").json()["recipes"]
    assert recipes[0]["name"] == "练后餐" and len(recipes[0]["items"]) == 2
    # 食谱条目可整餐复用
    items = recipes[0]["items"]
    served = record(c, TODAY, "snack", [
        {"food_id": it["food_id"], "amount": it["amount"], "unit": it["unit"]}
        for it in items])
    assert served.status_code == 200


def test_trends_and_targets(client):
    c, _ = client
    rice = food_id(c, "米饭（熟）")
    for i in range(3):
        d = (date.today() - timedelta(days=i)).isoformat()
        record(c, d, "dinner", [{"food_id": rice, "amount": 1, "unit": "碗"}])
    trends = c.get("/api/users/nu/nutrition/trends", params={"days": 7}).json()
    assert len(trends["days"]) == 3
    assert "已记录摄入量" in trends["note"]
    # 目标：手动设置 + 参考估算（有依据但不代填）
    t = c.post("/api/users/nu/nutrition/targets", json={
        "energy_kcal": 2200, "protein_g": 140, "precision_willing": "rough"})
    assert t.status_code == 200
    got = c.get("/api/users/nu/nutrition/targets").json()
    assert got["targets"]["energy_kcal"] == 2200
    assert got["reference"]["bmr"] > 1000  # Mifflin-St Jeor 参考值
    assert "个体差异" in got["reference"]["note"]
    # 非法目标值拒绝
    assert c.post("/api/users/nu/nutrition/targets",
                  json={"energy_kcal": 99999}).status_code == 422


# ---- 营养顾问：MealRecorded → ExpertInsight ----

def seed_full_day(c, day=TODAY, complete=True):
    egg = food_id(c, "鸡蛋"); rice = food_id(c, "米饭（熟）"); chicken = food_id(c, "鸡胸肉")
    record(c, day, "breakfast", [{"food_id": egg, "amount": 2, "unit": "个"}])
    record(c, day, "lunch", [{"food_id": chicken, "amount": 1, "unit": "块"},
                             {"food_id": rice, "amount": 1.5, "unit": "碗"}])
    record(c, day, "dinner", [{"food_id": rice, "amount": 1, "unit": "碗"}])
    if complete:
        c.post(f"/api/users/nu/nutrition/days/{day}/complete", json={"complete": True})


def test_meal_recorded_produces_traceable_insight(client):
    c, db = client
    seed_full_day(c)
    c.post("/api/users/nu/nutrition/targets", json={"energy_kcal": 1200, "protein_g": 140})
    insights = insight_service.list_insights(db, "nu", specialist="nutrition")
    ready = [i for i in insights if i["status"] == "ready"]
    assert ready, "完整记录 + 目标设置后应有 ready 洞察"
    ins = insight_service.get_insight(db, "nu", ready[0]["id"])
    snap_ids = {f["fact_id"] for f in ins["facts_snapshot"]["facts"]}
    assert set(ins["evidence_refs"]) <= snap_ids
    for f in ins["findings"]:
        assert f["evidence"] == "verified"
        assert f["source_ids"] and all(s.startswith("meal:") for s in f["source_ids"])
    # 目标比较存在且来自计算
    cmp_finding = next(f for f in ins["findings"] if f["kind"] == "target-compare")
    assert "已标记完整" in cmp_finding["text"]
    ids = [o["option_id"] for o in ins["options"]]
    assert "keep-observing" in ids
    # 已记录远超 1200 目标 → 参考方向出现（由用户决定）
    assert "review-direction" in ids


def test_incomplete_day_no_false_judgment(client):
    c, db = client
    egg = food_id(c, "鸡蛋")
    record(c, TODAY, "breakfast", [{"food_id": egg, "amount": 1, "unit": "个"}])
    insights = [i for i in insight_service.list_insights(db, "nu", specialist="nutrition")
                if i["status"] == "ready"]
    ins = insight_service.get_insight(db, "nu", insights[0]["id"])
    ids = [o["option_id"] for o in ins["options"]]
    assert "complete-records" in ids and "review-direction" not in ids
    assert ins["confidence"] == "low"  # 仅 1 个餐次
    assert any("未标记记录完整" in lim for lim in ins["limitations"])


def test_high_confidence_with_complete_history(client):
    c, db = client
    c.post("/api/users/nu/nutrition/targets", json={"energy_kcal": 2400})
    for i in range(4, 0, -1):  # 4 天历史 + 今天 = 5 天
        seed_full_day(c, (date.today() - timedelta(days=i)).isoformat())
    seed_full_day(c, TODAY)
    ready = [i for i in insight_service.list_insights(db, "nu", specialist="nutrition")
             if i["status"] == "ready"]
    ins = insight_service.get_insight(db, "nu", ready[0]["id"])
    assert ins["confidence"] == "high"
    assert "已标记完整" in str(ins["findings"])


def test_new_meal_same_day_reanalysis_and_drift(client):
    c, db = client
    egg = food_id(c, "鸡蛋")
    record(c, TODAY, "breakfast", [{"food_id": egg, "amount": 2, "unit": "个"}])
    first = [i for i in insight_service.list_insights(db, "nu", specialist="nutrition")
             if i["status"] == "ready"][0]
    # 同一数据状态重放（幂等）：无新任务
    from coach.experts import task_dispatcher
    from coach.nutrition.meal_service import day_version
    task_dispatcher.on_event(db, "nu", "MealRecorded",
                             {"local_date": TODAY,
                              "day_version": day_version(db, "nu", TODAY)})
    tasks = [t for t in db.list_expert_tasks("nu", specialist="nutrition")]
    assert len(tasks) == 1
    # 加午餐 → 新分析；旧洞察漂移失效
    record(c, TODAY, "lunch", [{"food_id": egg, "amount": 1, "unit": "个"}])
    fresh = insight_service.get_insight(db, "nu", first["id"])
    assert fresh["status"] == "invalidated"
    assert "饮食记录已变化" in fresh["status_reason"]
    ready = [i for i in insight_service.list_insights(db, "nu", specialist="nutrition")
             if i["status"] == "ready"]
    assert ready and ready[0]["id"] != first["id"]


def test_meal_deletion_invalidates_insight(client):
    c, db = client
    egg = food_id(c, "鸡蛋")
    made = record(c, TODAY, "breakfast", [{"food_id": egg, "amount": 2, "unit": "个"}]).json()
    ins = [i for i in insight_service.list_insights(db, "nu", specialist="nutrition")
           if i["status"] == "ready"][0]
    c.delete(f"/api/users/nu/meals/{made['meal_id']}")
    fresh = insight_service.get_insight(db, "nu", ins["id"])
    assert fresh["status"] == "invalidated"


def test_user_isolation_nutrition(client):
    c, _ = client
    egg = food_id(c, "鸡蛋")
    record(c, TODAY, "breakfast", [{"food_id": egg, "amount": 1, "unit": "个"}])
    mine = c.get("/api/users/nu/nutrition/summary", params={"date": TODAY}).json()
    theirs = c.get("/api/users/other/nutrition/summary", params={"date": TODAY}).json()
    assert mine["day"]["items_count"] == 1
    assert theirs["day"]["items_count"] == 0
    # 他人不可改/删我的餐次
    meal_id = mine["meals"][0]["id"]
    assert c.put(f"/api/users/other/meals/{meal_id}", json={"items": []}
                 ).status_code in (404, 422)
    assert c.delete(f"/api/users/other/meals/{meal_id}").status_code == 404


def test_food_snapshot_survives_catalog_update(tmp_path):
    """食物库更新不改变历史记录（快照纪律）。"""
    db = Database(tmp_path / "snap.db")
    meal_service.init_nutrition(db)
    rice = db.search_foods(None, "米饭（熟）")[0]
    meal_service.record_meal(db, "u", TODAY, "dinner",
                             [{"food_id": rice["id"], "amount": 1, "unit": "碗"}],
                             trigger_event=False)
    energy_before = db.meals_on("u", TODAY)[0]["items"][0]["intake"]["energy_kcal"]
    # 食物库更新营养值
    db.upsert_food({**rice, "energy_kcal": 200})
    energy_after = db.meals_on("u", TODAY)[0]["items"][0]["intake"]["energy_kcal"]
    assert energy_before == energy_after == pytest.approx(232, abs=1)  # 快照未变
