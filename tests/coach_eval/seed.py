#!/usr/bin/env python3
"""M6.5-5 评测集：固定训练数据库 + 确定性断言（AI 建议质量评测的地基）。

三层：
- seed.py：可复现的训练数据库构造器（明确日期/类型/热身/纠错/会话身份）；
- cases.py：≥30 个案例，覆盖任务书 14 类场景（编造/口径/纠错/完成率/
  安全/分歧/未审核来源/尝试数据不足等）；
- test_eval.py：运行器——硬性约束要求零违规，趋势/建议类报告通过率与
  失败类型（报告写入 docs/m6.5-eval-report.md）。

这不是"LLM 返回了 JSON 就算过"的评测：数值必须能追溯到种子记录，
口径必须与三个接口一致，行为红线用确定性断言卡死。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from coach.db import Database


def make_db(tmp_path, user_id="evalu") -> Database:
    db = Database(tmp_path / "eval.db")
    db.save_profile(user_id, {
        "basic": {"age": 30, "gender": "男", "height_cm": 175, "weight_kg": 72},
        "goal": {"primary": "力量"},
        "experience": {"training_years": 2},
        "resources": {"location": "gym", "days_per_week": 3,
                       "session_minutes": 60},
        "conditions": {"injuries": [], "injuries_evidence": "无",
                       "health_screen": {"heart": "无", "pregnancy": "不适用",
                                         "medication": "无",
                                         "clearance": "无"},
                       "health_screen_evidence": "评测种子"},
        "onboarding_done": True,
    })
    return db


def seed_plan(db, user_id, days=("周一", "周三", "周六"), plan_id=None) -> int:
    content = {"template": "评测计划", "schedule": [
        {"day": d, "focus": "评测", "exercises": [
            {"exercise_id": "barbell_bench_press", "name": "杠铃平板卧推",
             "sets": 4, "reps": "8-12"}]} for d in days]}
    cur = db.conn.execute(
        "INSERT INTO plans(user_id, version, active, content, created_at)"
        " VALUES(?,1,1,?,?)",
        (user_id, json.dumps(content, ensure_ascii=False),
         datetime.now().isoformat(timespec="seconds")))
    db.conn.commit()
    return cur.lastrowid


def seed_session(db, user_id, local_date: str, exercises: list[dict], *,
                 mode: str = "planned", day: str | None = None,
                 plan_id: int | None = None, template_id: int | None = None,
                 created_at: str | None = None) -> int:
    """一条训练打卡。exercises=[{exercise_id,name,set_logs:[...]}]。
    set_log 字段与前端一致：type/weight_kg/reps/warmup/at/rpe/
    added_weight_kg/assistance_kg/duration_seconds/distance_m。"""
    d = date.fromisoformat(local_date)
    created = created_at or f"{d.isoformat()}T20:00:00"
    meta = {"session_id": f"s-{local_date}", "mode": mode,
            "started_at": f"{d.isoformat()}T19:00:00",
            "completed_at": created, "local_date": local_date,
            "timezone": "Asia/Shanghai"}
    if day:
        meta["day"] = day
    if plan_id is not None:
        meta["plan_id"] = plan_id
        meta["plan_version"] = 1
    if template_id is not None:
        meta["template_id"] = template_id
    data = {"exercises": exercises, "raw": f"种子训练 {local_date}",
            "session_meta": meta}
    cur = db.conn.execute(
        "INSERT INTO checkins(user_id, type, data, created_at)"
        " VALUES(?, 'training', ?, ?)",
        (user_id, json.dumps(data, ensure_ascii=False), created))
    db.conn.commit()
    return cur.lastrowid


def set_log(**kw) -> dict:
    kw.setdefault("type", "weight_reps")
    kw.setdefault("at", "2026-01-01T00:00:00")
    return kw


def correct_checkin(db, user_id: str, checkin_id: int, patch: dict,
                    reason: str = "评测纠错") -> None:
    """模拟历史纠错：改写当前行 + 落一条修订记录（与运行时口径一致）。"""
    row = db.conn.execute("SELECT data FROM checkins WHERE id=?",
                          (checkin_id,)).fetchone()
    old = row["data"]
    data = json.loads(old)
    ex = data["exercises"][patch.pop("_exercise_index", 0)]
    set_idx = patch.pop("_set_index", 0)
    ex["set_logs"][set_idx].update(patch)
    new = json.dumps(data, ensure_ascii=False)
    db.conn.execute("UPDATE checkins SET data=? WHERE id=?", (new, checkin_id))
    db.conn.execute(
        "INSERT INTO checkin_revisions(user_id, checkin_id, revision,"
        " old_data, new_data, reason, evidence, created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (user_id, checkin_id, 1, old, new, reason, "评测种子用户原话",
         datetime.now().isoformat(timespec="seconds")))
    db.conn.commit()
