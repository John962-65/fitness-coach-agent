"""P5-B2 回归：地点/器械、筛选、替代候选与安全确认。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from coach.plan import generate_plan
from coach.rehab import restriction_service
from test_repair_regressions import profile

TODAY = "2026-10-26"


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "p5b2.db")
    with TestClient(app) as c:
        db = app.state.db
        for uid in ("u", "other"):
            db.save_profile(uid, profile())
            db.create_plan(uid, generate_plan(profile()))
        yield c, db


def locations(c, uid="u"):
    return c.get(f"/api/users/{uid}/locations").json()


def configure_gym_home(c):
    data = locations(c)
    by_name = {x["name"]: x for x in data["locations"]}
    assert set(by_name) >= {"健身房", "居家", "户外"}
    gym = c.patch(f"/api/users/u/locations/{by_name['健身房']['id']}", json={
        "required_equipment": ["barbell", "dumbbell", "bench"],
        "optional_equipment": [],
    }).json()["location"]
    home = c.patch(f"/api/users/u/locations/{by_name['居家']['id']}", json={
        "required_equipment": ["dumbbell", "band", "bench"],
        "optional_equipment": [],
    }).json()["location"]
    assert gym["required_equipment_ids"] == ["barbell", "dumbbell", "bench"]
    assert home["required_equipment_ids"] == ["dumbbell", "band", "bench"]
    c.post(f"/api/users/u/locations/{home['id']}/select")
    return by_name, gym, home


def checkin_bench(c):
    return c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "杠铃平板卧推", "exercise_id": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 60,
                                     "reps": 10}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})


def save_session_replacement(c, target="dumbbell_bench_press"):
    return c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "哑铃卧推", "exercise_id": target,
                       "session_replacement_of": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 20,
                                     "reps": 10}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})


def test_location_crud_custom_equipment_and_user_isolation(client):
    c, _ = client
    data = locations(c)
    assert data["current_id"] is not None
    assert len(data["locations"]) == 3

    made = c.post("/api/users/u/locations", json={
        "name": "宿舍", "kind": "custom",
        "required_equipment": [], "optional_equipment": [], "current": True,
    }).json()["location"]
    assert made["kind"] == "custom"
    assert locations(c)["current_id"] == made["id"]

    upd = c.patch(f"/api/users/u/locations/{made['id']}", json={
        "name": "宿舍训练角", "kind": "custom"}).json()["location"]
    assert upd["name"] == "宿舍训练角"

    custom_eq = c.post("/api/users/u/equipment", json={
        "name": "可调哑铃", "category": "free_weight",
        "aliases": ["小哑铃"], "fulfills": "dumbbell",
    }).json()["equipment"]
    assert custom_eq["id"].startswith("custom_eq_")
    assert custom_eq["fulfills"] == "dumbbell"

    upd_loc = c.patch(f"/api/users/u/locations/{made['id']}", json={
        "required_equipment": [custom_eq["id"]],
        "optional_equipment": ["band"]}).json()["location"]
    assert upd_loc["required_equipment_ids"] == [custom_eq["id"]]
    assert upd_loc["optional_equipment_ids"] == ["band"]

    other = locations(c, "other")
    assert all(x["scope"] == "system" for x in other["equipment"])
    assert all(x["name"] != "宿舍训练角" for x in other["locations"])
    assert c.post(f"/api/users/other/locations/{made['id']}/select").status_code == 404
    assert c.delete(f"/api/users/other/equipment/{custom_eq['id']}").status_code == 404

    assert c.delete(f"/api/users/u/equipment/{custom_eq['id']}").status_code == 200
    after = locations(c)["locations"]
    loc = next(x for x in after if x["id"] == made["id"])
    assert loc["required_equipment_ids"] == []
    assert c.delete(f"/api/users/u/locations/{made['id']}").status_code == 200


def test_custom_equipment_equivalent_satisfies_builtin_by_id(client):
    c, _ = client
    data = locations(c)
    home = next(x for x in data["locations"] if x["kind"] == "home")
    custom_eq = c.post("/api/users/u/equipment", json={
        "name": "家里的可调哑铃", "category": "free_weight",
        "fulfills": "dumbbell",
    }).json()["equipment"]
    c.patch(f"/api/users/u/locations/{home['id']}", json={
        "required_equipment": [custom_eq["id"], "bench"],
        "optional_equipment": []})
    c.post(f"/api/users/u/locations/{home['id']}/select")
    rows = c.get("/api/exercises", params={
        "uid": "u", "q": "哑铃卧推", "location_id": home["id"],
        "available": "true",
    }).json()["exercises"]
    assert any(x["id"] == "dumbbell_bench_press" for x in rows)


def test_exercise_filters_use_equipment_ids_not_names(client):
    c, _ = client
    by_name, _, home = configure_gym_home(c)
    all_rows = c.get("/api/exercises", params={
        "uid": "u", "location_id": home["id"]}).json()["exercises"]
    bench = next(x for x in all_rows if x["id"] == "barbell_bench_press")
    assert bench["available"] is False
    assert bench["missing_equipment"] == ["杠铃"]

    available = c.get("/api/exercises", params={
        "uid": "u", "location_id": home["id"], "available": "true",
        "pattern": "h_push", "muscle": "chest",
    }).json()["exercises"]
    ids = {x["id"] for x in available}
    assert "dumbbell_bench_press" in ids
    assert "barbell_bench_press" not in ids
    assert all(x["available"] is True for x in available)

    by_equipment = c.get("/api/exercises", params={
        "uid": "u", "location": "home", "equipment": "band"}).json()["exercises"]
    assert by_equipment and all("band" in x["equipment"] for x in by_equipment)

    assert checkin_bench(c).status_code == 200
    frequent = c.get("/api/exercises", params={
        "uid": "u", "frequent": "true"}).json()["exercises"]
    assert any(x["id"] == "barbell_bench_press" and x["frequent"] for x in frequent)

    gym_options = c.get("/api/exercises", params={
        "uid": "u", "location_id": by_name["健身房"]["id"], "available": "true",
        "q": "杠铃平板卧推"}).json()["exercises"]
    assert gym_options[0]["available"] is True


def test_substitution_candidates_and_safety_validation(client):
    c, db = client
    _, _, home = configure_gym_home(c)
    result = c.get("/api/users/u/exercise-substitutes", params={
        "exercise_id": "barbell_bench_press", "location_id": home["id"]}).json()
    ids = [x["id"] for x in result["candidates"]]
    assert "dumbbell_bench_press" in ids
    assert result["location"]["name"] == "居家"
    assert "不代表动作等价" in result["disclaimer"]
    candidate = next(x for x in result["candidates"] if x["id"] == "dumbbell_bench_press")
    assert candidate["differences"] and candidate["equipment_names"]
    assert "goblet_squat" not in ids
    assert result["excluded"]["unrelated"] > 0

    ok = c.post("/api/users/u/exercise-substitutions/validate", json={
        "source_exercise_id": "barbell_bench_press",
        "target_exercise_id": "dumbbell_bench_press",
        "location_id": home["id"]})
    assert ok.status_code == 200 and ok.json()["safety_checked"] is True

    c.patch(f"/api/users/u/locations/{home['id']}", json={
        "required_equipment": ["dumbbell", "band"]})
    missing = c.post("/api/users/u/exercise-substitutions/validate", json={
        "source_exercise_id": "barbell_bench_press",
        "target_exercise_id": "dumbbell_bench_press",
        "location_id": home["id"]})
    assert missing.status_code == 422 and "缺少" in missing.json()["detail"]["error"]

    c.patch(f"/api/users/u/locations/{home['id']}", json={
        "required_equipment": ["dumbbell", "band", "bench"]})
    db.add_custom_exercise("u", "test_chest_duration", {
        "id": "test_chest_duration", "name": "胸部门控测试",
        "pattern": "h_push", "primary": ["chest"],
        "equipment": ["bodyweight"], "location": ["home"],
        "measurement": "duration", "level_min": "beginner",
        "status": "approved", "scope": "user",
    })
    incompatible = c.post("/api/users/u/exercise-substitutions/validate", json={
        "source_exercise_id": "barbell_bench_press",
        "target_exercise_id": "test_chest_duration",
        "location_id": home["id"]})
    assert incompatible.status_code == 422
    assert "记录口径" in incompatible.json()["detail"]["error"]

    restriction_service.create_restriction(db, "u", {
        "source_type": "user_reported", "source_evidence": "肩部发力不适",
        "restriction_description": "暂不做哑铃卧推",
        "affected_activities": {"regions": [], "movements": ["dumbbell_bench_press"]},
    })
    filtered = c.get("/api/users/u/exercise-substitutes", params={
        "exercise_id": "barbell_bench_press", "location_id": home["id"]}).json()
    assert "dumbbell_bench_press" not in [x["id"] for x in filtered["candidates"]]
    assert filtered["excluded"]["safety"] >= 1

    blocked = c.post("/api/users/u/exercise-substitutions/validate", json={
        "source_exercise_id": "barbell_bench_press",
        "target_exercise_id": "dumbbell_bench_press",
        "location_id": home["id"]})
    assert blocked.status_code == 422 and "限制" in blocked.json()["detail"]["error"]
    assert save_session_replacement(c).status_code == 422

    plan = c.get("/api/users/u/plan").json()
    day = next(d for d in plan["content"]["schedule"]
               if any(x["exercise_id"] == "barbell_bench_press" for x in d["exercises"]))
    idx = next(i for i, x in enumerate(day["exercises"])
               if x["exercise_id"] == "barbell_bench_press")
    proposed = c.post("/api/users/u/changes/ai", json={
        "target": "plan",
        "operations": [{"op": "replace_exercise", "day": day["day"],
                        "index": idx, "exercise": "dumbbell_bench_press"}],
        "reason": "居家替代", "base_version": plan["base_version"]})
    assert proposed.status_code == 422


def test_unrelated_actions_never_fill_candidate_list(client):
    c, _ = client
    data = locations(c)
    home = next(x for x in data["locations"] if x["kind"] == "home")
    c.patch(f"/api/users/u/locations/{home['id']}", json={
        "required_equipment": ["band"], "optional_equipment": []})
    c.post(f"/api/users/u/locations/{home['id']}/select")
    result = c.get("/api/users/u/exercise-substitutes", params={
        "exercise_id": "barbell_bench_press", "location_id": home["id"]}).json()
    assert result["candidates"] == []
    assert result["excluded"]["unrelated"] > 0


def test_session_replacement_rejects_wrong_measurement_type(client):
    c, _ = client
    configure_gym_home(c)
    wrong = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "引体向上", "exercise_id": "pull_up",
                       "session_replacement_of": "barbell_bench_press",
                       "set_logs": [{"type": "weight_reps", "weight_kg": 20,
                                     "reps": 8}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert wrong.status_code == 422
    assert "记录口径" in wrong.json()["detail"]["error"]
    right = c.post("/api/users/u/checkins", json={"type": "training", "data": {
        "exercises": [{"name": "引体向上", "exercise_id": "pull_up",
                       "session_replacement_of": "barbell_bench_press",
                       "set_logs": [{"type": "bodyweight_reps",
                                     "added_weight_kg": 5, "reps": 8}]}],
        "session_meta": {"mode": "free", "local_date": TODAY}}})
    assert right.status_code == 200


def test_session_only_and_long_term_confirmation_are_separate(client):
    c, _ = client
    configure_gym_home(c)
    plan_before = c.get("/api/users/u/plan").json()
    saved = save_session_replacement(c)
    assert saved.status_code == 200
    plan_after_session = c.get("/api/users/u/plan").json()
    assert plan_after_session["version"] == plan_before["version"]

    day = next(d for d in plan_after_session["content"]["schedule"]
               if any(x["exercise_id"] == "barbell_bench_press" for x in d["exercises"]))
    idx = next(i for i, x in enumerate(day["exercises"])
               if x["exercise_id"] == "barbell_bench_press")
    staged = c.post("/api/users/u/changes/ai", json={
        "target": "plan",
        "operations": [{"op": "replace_exercise", "day": day["day"],
                        "index": idx, "exercise": "dumbbell_bench_press"}],
        "reason": "长期改为哑铃卧推",
        "base_version": plan_after_session["base_version"]})
    assert staged.status_code == 200
    proposal = staged.json()
    assert proposal["status"] == "pending"
    assert c.get("/api/users/u/plan").json()["version"] == plan_before["version"]

    confirmed = c.post(f"/api/users/u/changes/{proposal['proposal_id']}/confirm",
                       json={"message": "确认，改为哑铃卧推"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "applied"
    plan_final = c.get("/api/users/u/plan").json()
    assert plan_final["version"] == plan_before["version"] + 1
    assert any(x["exercise_id"] == "dumbbell_bench_press"
               for x in next(d for d in plan_final["content"]["schedule"]
                             if d["day"] == day["day"])["exercises"])
