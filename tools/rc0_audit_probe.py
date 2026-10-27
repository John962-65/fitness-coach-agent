"""RC-0 independent audit probes (reproducible, synthetic data only).

Run:
    FAKE_LLM=1 python3 tools/rc0_audit_probe.py

These probes intentionally target claims in the P10 release-readiness table:
- full backup restore / idempotency (P7-A)
- long-term report consistency with period summary (P7-D)
- account deletion scope (P7-B)
- local-date vs created_at window consistency (P6.5/P5-B3)
- insight freshness after a new workout (P5-C2/P6)
- PersonalTrial observation identity / frozen review (P5-C3)

They do NOT use data/ or the real user's media. Every database and file is
under a temporary directory.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from coach.analytics.fact_service import get_training_facts
from coach.analytics.long_term_report import build_report
from coach.analytics.training_calendar import period_summary
from coach.db import Database
from coach.plan import generate_plan
from coach.rehab import restriction_service, symptom_service
from coach.training_progression import trial_service


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="rc0-probe-"))


def _profile():
    from test_repair_regressions import profile
    return profile()


def probe_import_roundtrip() -> dict:
    tmp = _tmp()
    try:
        app = create_app(db_path=tmp / "p7a.db")
        c = TestClient(app)
        db = app.state.db
        today = date.today().isoformat()
        for uid in ("u", "v"):
            db.save_profile(uid, _profile())
            db.create_plan(uid, generate_plan(_profile()))
        logs = [{"type": "weight_reps", "weight_kg": 60, "reps": 10}] * 3
        c.post("/api/users/u/checkins", json={
            "type": "training", "data": {
                "exercises": [{"name": "杠铃平板卧推",
                               "exercise_id": "barbell_bench_press",
                               "set_logs": logs}],
                "session_meta": {"mode": "free", "local_date": today}}})
        c.post("/api/users/u/body-measurements", json={
            "measured_at": f"{today}T08:00:00", "local_date": today,
            "weight_kg": 75.0, "source": "user"})
        c.post("/api/users/u/recovery-checkins", json={"data": {
            "local_date": today, "fatigue": 3, "sleep_hours": 7}})
        symptom_service.report_episode(db, "u", {
            "body_region": "shoulder", "description": "肩部酸痛",
            "onset_at": today})
        restriction_service.create_restriction(db, "u", {
            "source_type": "professional",
            "source_evidence": "医生要求暂不卧推（合成审计数据）",
            "restriction_description": "暂不做杠铃卧推",
            "affected_activities": {"regions": [],
                                    "movements": ["barbell_bench_press"]}})
        c.post("/api/users/u/trials", json={
            "change_desc": "卧推加重一档", "reason": "审计",
            "observe": "次数", "stop_rule": "3 次"})
        db.save_training_template("u", "审计模板", {"days": []})
        db.save_recipe("u", "审计食谱", [{"food_id": "bi-rice",
                                          "amount": 100}])
        db.add_user_equipment("u", "barbell", {"name": "杠铃",
                                               "category": "free_weight"})
        db.create_training_location("u", {
            "name": "家", "kind": "home", "required_equipment": [],
            "optional_equipment": []})
        export = c.post("/api/users/u/export",
                        json={"format": "json", "confirm": True}).json()
        for _ in range(2):
            c.post("/api/users/v/import/apply",
                   json={"backup": export, "confirmed": True})
        counts = {}
        for table in ("plans", "checkins", "body_measurements",
                      "recovery_checkins", "symptom_episodes",
                      "training_restrictions", "personal_trials",
                      "training_templates", "nutrition_recipes",
                      "user_equipment", "training_locations"):
            counts[table] = db.conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE user_id='v'"
            ).fetchone()["c"]
        active = [dict(r) for r in db.conn.execute(
            "SELECT source_type,status FROM training_restrictions"
            " WHERE user_id='v'")]
        return {
            "export_sections": sorted(export["user_data"].keys()),
            "counts_after_two_imports": counts,
            "active_restrictions_after_import": active,
            "imported_active_plan": db.get_active_plan_record("v"),
            "observation": ("plans/body/symptoms/restrictions duplicated; "
                            "trials/templates/recipes/equipment/locations "
                            "missing; professional restriction imported as "
                            "lifted"),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_long_term_report() -> dict:
    tmp = _tmp()
    try:
        db = Database(tmp / "p7d.db")
        db.save_profile("u", _profile())
        db.create_plan("u", generate_plan(_profile()))
        today = date.today().isoformat()
        db.record_checkin("u", "training", {
            "exercises": [
                {"name": "杠铃平板卧推",
                 "exercise_id": "barbell_bench_press",
                 "set_logs": [{"type": "weight_reps", "weight_kg": 60,
                               "reps": 10}] * 4},
                {"name": "杠铃深蹲", "exercise_id": "barbell_back_squat",
                 "set_logs": [{"type": "weight_reps", "weight_kg": 100,
                               "reps": 5}] * 4}],
            "session_meta": {"mode": "free", "local_date": today}})
        ps = period_summary(db, "u", 30)
        rep = build_report(db, "u", "month")
        return {
            "period_summary": {"working_sets": ps["strength_working_sets"],
                               "volume_kg": ps["strength_volume_kg"]},
            "long_term_report": {
                "working_sets": rep["training"]["working_sets"],
                "volume_kg": rep["training"]["strength_volume_kg"]},
            "expected": {"working_sets": 8, "volume_kg": 4400},
            "observation": ("long-term report only aggregates the first "
                            "exercise of each checkin"),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_account_deletion() -> dict:
    tmp = _tmp()
    try:
        db = Database(tmp / "p7b.db")
        db.save_profile("u", _profile())
        media_dir = tmp / "media" / "u"
        media_dir.mkdir(parents=True)
        video = media_dir / "v1_clip.mp4"
        video.write_bytes(b"fake video")
        asset_id = db.add_media_asset("u", "审计视频", str(video), None)
        db.update_media_asset(asset_id, status="ready")
        source_id = db.add_knowledge_source("u", "审计资料", "text",
                                            "raw", "hash-audit-1")
        db.add_knowledge_chunk(source_id, 1, "个人导入资料正文")
        task = db.create_expert_task("u", "training_science",
                                     "post-workout-review", "UserRequested",
                                     {"checkin_id": 1})
        task_id = task["id"]
        counts = db.delete_user("u")
        return {
            "deleted_rows": counts,
            "media_file_still_exists": video.exists(),
            "orphan_knowledge_chunks": db.conn.execute(
                "SELECT COUNT(*) c FROM knowledge_chunks WHERE source_id=?",
                (source_id,)).fetchone()["c"],
            "orphan_task_events": db.conn.execute(
                "SELECT COUNT(*) c FROM expert_task_events WHERE task_id=?",
                (task_id,)).fetchone()["c"],
            "observation": ("DB rows with user_id are deleted; media files, "
                            "knowledge chunks and task events remain"),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_window_consistency() -> dict:
    tmp = _tmp()
    try:
        db = Database(tmp / "window.db")
        db.save_profile("w", _profile())
        logs = [{"type": "weight_reps", "weight_kg": 60, "reps": 10}] * 3
        old = (date.today() - timedelta(days=31)).isoformat()
        db.record_checkin("w", "training", {
            "exercises": [{"name": "杠铃平板卧推",
                           "exercise_id": "barbell_bench_press",
                           "set_logs": logs}],
            "session_meta": {"mode": "free", "local_date": old}})
        facts = get_training_facts(db, "w", 30)
        ps = period_summary(db, "w", 30)
        rep = build_report(db, "w", "month")
        return {
            "training_facts_sessions": next(
                (f["value"] for f in facts["facts"]
                 if f["metric"] == "sessions"), None),
            "period_summary_sessions": ps["training_sessions"],
            "long_term_report_sessions": rep["training"]["sessions"],
            "record_local_date": old,
            "created_at": "now (probe inserts with current time)",
            "observation": ("facts/period_summary filter by created_at while "
                            "long-term report filters by local_date"),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_insight_staleness() -> dict:
    tmp = _tmp()
    try:
        app = create_app(db_path=tmp / "insight.db")
        c = TestClient(app)
        db = app.state.db
        db.save_profile("u", _profile())
        db.create_plan("u", generate_plan(_profile()))
        plan = db.get_active_plan_record("u")
        pctx = {"plan_id": plan["id"], "plan_version": plan["version"]}
        for day in plan["content"]["schedule"]:
            for i, entry in enumerate(day["exercises"]):
                if entry["exercise_id"] == "barbell_bench_press":
                    pctx.update({"planned_day": day["day"], "index": i,
                                 "planned_exercise_id": entry["exercise_id"]})
                    break

        def save(offset):
            logs = [{"type": "weight_reps", "weight_kg": 60,
                     "reps": 8}] * 4
            r = c.post("/api/users/u/checkins", json={
                "type": "training", "data": {
                    "exercises": [{"name": "杠铃平板卧推",
                                   "exercise_id": "barbell_bench_press",
                                   "set_logs": logs}],
                    "session_meta": {
                        "mode": "free",
                        "local_date": (date.today()
                                       - timedelta(days=offset)).isoformat()}}})
            return r.json()["id"]
        save(5)
        r = c.post("/api/users/u/experts/analysis", json={
            "specialist": "training_science",
            "task_type": "next-training-review",
            "params": {"exercise_id": "barbell_bench_press", **pctx}})
        insight = r.json()["insight"]
        save(1)
        fresh = c.get(
            f"/api/users/u/expert-insights/{insight['id']}").json()
        return {
            "status_before_new_workout": insight["status"],
            "status_after_new_workout": fresh["status"],
            "status_reason": fresh.get("status_reason"),
            "observation": ("next-training insight remains ready after a new "
                            "workout because source_revision only tracks "
                            "referenced checkin ids/revisions"),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_trial_observation() -> dict:
    tmp = _tmp()
    try:
        db = Database(tmp / "trial.db")
        db.save_profile("u", _profile())
        db.create_plan("u", generate_plan(_profile()))
        logs = [{"type": "weight_reps", "weight_kg": 60, "reps": 8}] * 4
        for i in range(10):
            day = (date.today() - timedelta(days=9 - i)).isoformat()
            db.record_checkin("u", "training", {
                "exercises": [{"name": "杠铃平板卧推",
                               "exercise_id": "barbell_bench_press",
                               "set_logs": logs}],
                "session_meta": {"mode": "free", "local_date": day}})
        trial_id = db.start_personal_trial(
            "u", "卧推尝试", "审计", "观察次数", "3 次", review_days=30,
            chosen_target=json.dumps({"sets": 4, "reps": "8",
                                      "weight_kg": 60}),
            exercise_id="barbell_bench_press",
            observation_metric="target-completion",
            observation_window_days=30, min_sessions=3)
        db.conn.execute(
            "UPDATE personal_trials SET created_at=? WHERE id=?",
            ((datetime.now() - timedelta(days=10)).isoformat(timespec="seconds"),
             trial_id))
        db.conn.commit()
        trial = db.get_personal_trial("u", trial_id)
        obs = trial_service.trial_observation(db, "u", trial)
        trial_service.decide_trial(db, "u", trial_id, "keep", "审计")
        db.record_checkin("u", "training", {
            "exercises": [{"name": "杠铃平板卧推",
                           "exercise_id": "barbell_bench_press",
                           "set_logs": logs}],
            "session_meta": {"mode": "free",
                             "local_date": date.today().isoformat()}})
        trial = db.get_personal_trial("u", trial_id)
        obs_after_end = trial_service.trial_observation(db, "u", trial)
        return {
            "real_sessions_after_start": 10,
            "observation_sessions_total": obs["sessions_total"],
            "observation_capped_at": 8,
            "sessions_total_after_end_plus_one": obs_after_end["sessions_total"],
            "ended_at": trial["ended_at"],
            "observation": ("trial_observation caps at 8 newest sessions and "
                            "does not stop at ended_at"),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    out = {
        "kind": "rc0-audit-probe",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "probes": {
            "backup_restore": probe_import_roundtrip(),
            "long_term_report": probe_long_term_report(),
            "account_deletion": probe_account_deletion(),
            "window_consistency": probe_window_consistency(),
            "insight_staleness": probe_insight_staleness(),
            "trial_observation": probe_trial_observation(),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
