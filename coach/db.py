"""SQLite 数据层（四表：users / plans / checkins / messages）"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "coach.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     TEXT PRIMARY KEY,
    profile     TEXT NOT NULL,          -- JSON
    created_at  TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    content     TEXT NOT NULL,          -- JSON
    active      INTEGER DEFAULT 1,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    type        TEXT NOT NULL,          -- training / diet / body
    data        TEXT NOT NULL,          -- JSON
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS checkin_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    checkin_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    old_data TEXT NOT NULL,
    new_data TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(checkin_id, revision)
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS user_exercise (
    user_id      TEXT NOT NULL,
    exercise_id  TEXT NOT NULL,
    preference   INTEGER,               -- -2 讨厌 … +2 最爱
    feel         INTEGER,               -- 目标肌群发力感 0-3
    discomfort   TEXT,
    status       TEXT,                  -- active / avoid / learning
    evidence     TEXT,                  -- 用户原话（反馈依据）
    best_e1rm    REAL,
    last_weight  REAL,
    last_rpe     REAL,
    notes        TEXT,
    updated_at   TEXT,
    PRIMARY KEY (user_id, exercise_id)
);
CREATE TABLE IF NOT EXISTS coach_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    note        TEXT NOT NULL,
    evidence    TEXT NOT NULL,          -- 依据（用户原话/打卡）
    status      TEXT DEFAULT 'open',    -- open / closed
    expires_at  TEXT,                   -- 可空
    created_at  TEXT,
    closed_at   TEXT
);
"""

DEFAULT_PROFILE = {
    "basic": {"name": "", "age": 0, "gender": "", "height_cm": 0, "weight_kg": 0},
    "experience": {"training_years": 0, "level": "beginner", "big3": {},
                  "recent_layoff_weeks": 0},
    "goal": {"primary": "", "phase": "", "target": ""},
    "conditions": {"injuries": [], "injuries_collected": False,
                   "injuries_evidence": "",
                   "health_screen": {}, "health_screen_collected": False,
                   "health_screen_evidence": "",
                   "pain_flags": []},
    "resources": {"location": "gym", "days_per_week": 0, "session_minutes": 60},
    "nutrition": {"meals_per_day": 3, "sleep_hours": 7},
    "onboarding_done": False,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- users ----
    def get_existing_profile(self, user_id: str) -> dict:
        row = self.conn.execute("SELECT profile FROM users WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row["profile"]) if row else {}

    def get_profile(self, user_id: str) -> dict:
        row = self.conn.execute(
            "SELECT profile FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row:
            return json.loads(row["profile"])
        profile = json.loads(json.dumps(DEFAULT_PROFILE))
        self.save_profile(user_id, profile)
        return profile

    def _write_profile(self, user_id: str, profile: dict) -> None:
        self.conn.execute(
            "INSERT INTO users(user_id, profile, created_at, updated_at)"
            " VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET profile=?, updated_at=?",
            (user_id, json.dumps(profile, ensure_ascii=False), _now(), _now(),
             json.dumps(profile, ensure_ascii=False), _now()),
        )

    def save_profile(self, user_id: str, profile: dict) -> None:
        with self.conn:
            self._write_profile(user_id, profile)

    # ---- plans ----
    def create_plan(self, user_id: str, content: dict, *,
                    profile: dict | None = None, expected_plan_id: int | None = None) -> int:
        """计划与建议状态一起提交；有基准版本时拒绝基于旧版本的写入。"""
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            current = self.get_active_plan_record(user_id)
            if expected_plan_id is not None and (current or {}).get("id") != expected_plan_id:
                raise ValueError("计划版本已变化，请重新获取建议")
            self.conn.execute("UPDATE plans SET active=0 WHERE user_id=?", (user_id,))
            v = self.conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            cur = self.conn.execute(
                "INSERT INTO plans(user_id, version, content, active, created_at)"
                " VALUES(?,?,?,1,?)",
                (user_id, v, json.dumps(content, ensure_ascii=False), _now()),
            )
            if profile is not None:
                self._write_profile(user_id, profile)
        return cur.lastrowid

    def get_active_plan_record(self, user_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, version, content FROM plans WHERE user_id=? AND active=1",
            (user_id,),
        ).fetchone()
        return dict(row, content=json.loads(row["content"])) if row else None

    def get_active_plan(self, user_id: str) -> dict | None:
        row = self.get_active_plan_record(user_id)
        return row["content"] if row else None

    def get_plan_content(self, user_id: str, plan_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT content FROM plans WHERE user_id=? AND id=?", (user_id, plan_id)
        ).fetchone()
        return json.loads(row["content"]) if row else None

    # ---- checkins ----
    def add_checkin(self, user_id: str, type_: str, data: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO checkins(user_id, type, data, created_at) VALUES(?,?,?,?)",
            (user_id, type_, json.dumps(data, ensure_ascii=False), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_checkins(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT c.id,c.type,c.data,c.created_at,"
            " (SELECT COUNT(*) FROM checkin_revisions r WHERE r.checkin_id=c.id) AS revision"
            " FROM checkins c WHERE c.user_id=? ORDER BY c.id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [{"id": r["id"], "revision": r["revision"], "type": r["type"],
                 "data": json.loads(r["data"]), "at": r["created_at"]} for r in rows]

    def get_checkin(self, user_id: str, checkin_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM checkin_revisions r WHERE r.checkin_id=c.id) AS revision"
            " FROM checkins c WHERE c.user_id=? AND c.id=?", (user_id, checkin_id)).fetchone()
        return ({"id": row["id"], "revision": row["revision"], "type": row["type"],
                 "data": json.loads(row["data"]), "at": row["created_at"]} if row else None)

    def revise_checkin(self, user_id: str, checkin_id: int, expected_revision: int,
                       data: dict, reason: str, evidence: str) -> dict:
        """保留原值、日期及用户归属；纠错和派生状态重算在同一事务内。"""
        if not reason.strip() or not evidence.strip():
            raise ValueError("纠错必须说明原因并附用户原话")
        from .exercises import library
        def ids(payload):
            result = set()
            for ex in payload.get("exercises", []) if isinstance(payload, dict) else []:
                if isinstance(ex, dict):
                    eid = ex.get("exercise_id") if "exercise_id" in ex else library.normalize(ex.get("name", ""))[0]
                    if isinstance(eid, str) and library.get(eid):
                        result.add(eid)
            return result
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            old = self.get_checkin(user_id, checkin_id)
            if not old:
                raise ValueError("记录不存在")
            if old["revision"] != expected_revision:
                raise ValueError("记录已被修订，请先重新读取最新版本")
            revision = expected_revision + 1
            self.conn.execute(
                "INSERT INTO checkin_revisions(user_id,checkin_id,revision,old_data,new_data,reason,evidence,created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (user_id, checkin_id, revision, json.dumps(old["data"], ensure_ascii=False),
                 json.dumps(data, ensure_ascii=False), reason, evidence, _now()))
            self.conn.execute("UPDATE checkins SET data=? WHERE user_id=? AND id=?",
                              (json.dumps(data, ensure_ascii=False), user_id, checkin_id))
            affected = ids(old["data"]) | ids(data)
            self._recompute_exercise_states(user_id, affected)
            profile = self.get_existing_profile(user_id)
            if profile:
                profile["pending_adjustments"] = []
                self._write_profile(user_id, profile)
        return self.get_checkin(user_id, checkin_id)

    def _recompute_exercise_states(self, user_id: str, exercise_ids: set[str]) -> None:
        from .exercises import library
        from .review import _same_exercise, e1rm
        from .validate import _to_number, _to_reps
        values = {eid: {"best": None, "weight": None, "rpe": None} for eid in exercise_ids}
        rows = self.conn.execute(
            "SELECT data FROM checkins WHERE user_id=? AND type='training' ORDER BY created_at DESC,id DESC",
            (user_id,))
        for row in rows:
            payload = json.loads(row["data"])
            if not isinstance(payload, dict):
                continue
            for ex in payload.get("exercises", []) or []:
                if not isinstance(ex, dict):
                    continue
                for eid, state in values.items():
                    if not _same_exercise(library.get(eid)["name"], ex):
                        continue
                    weight, rpe = _to_number(ex.get("weight_kg")), _to_number(ex.get("rpe"))
                    score = e1rm(weight, _to_reps(ex.get("reps")))
                    if score is not None:
                        state["best"] = max(state["best"] or 0, score)
                    if state["weight"] is None and weight is not None:
                        state["weight"], state["rpe"] = weight, rpe
        for eid, state in values.items():
            self.conn.execute(
                "INSERT INTO user_exercise(user_id,exercise_id,best_e1rm,last_weight,last_rpe,updated_at)"
                " VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,exercise_id) DO UPDATE SET"
                " best_e1rm=excluded.best_e1rm,last_weight=excluded.last_weight,"
                " last_rpe=excluded.last_rpe,updated_at=excluded.updated_at",
                (user_id, eid, state["best"], state["weight"], state["rpe"], _now()))

    # ---- messages ----
    def add_message(self, user_id: str, role: str, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages(user_id, role, content, created_at) VALUES(?,?,?,?)",
            (user_id, role, content, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def latest_user_message_id(self, user_id: str) -> int:
        return self.conn.execute(
            "SELECT COALESCE(MAX(id),0) FROM messages WHERE user_id=? AND role='user'",
            (user_id,),
        ).fetchone()[0]

    def user_messages_after(self, user_id: str, message_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id=? AND role='user' AND id>?",
            (user_id, message_id),
        ).fetchone()[0]

    def recent_messages(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE user_id=?"
            " ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ---- user_exercise ----
    def update_exercise_state(self, user_id: str, exercise_id: str,
                              weight: float | None, rpe: float | None,
                              e1rm_: float | None) -> None:
        """打卡驱动的自动状态（best_e1rm/last_weight/last_rpe），不碰反馈字段"""
        row = self.conn.execute(
            "SELECT best_e1rm FROM user_exercise WHERE user_id=? AND exercise_id=?",
            (user_id, exercise_id)).fetchone()
        best = e1rm_
        if row and row["best_e1rm"] is not None:
            best = max(row["best_e1rm"], e1rm_ or 0) or row["best_e1rm"]
        self.conn.execute(
            "INSERT INTO user_exercise(user_id, exercise_id, best_e1rm,"
            " last_weight, last_rpe, updated_at) VALUES(?,?,?,?,?,?)"
            " ON CONFLICT(user_id, exercise_id) DO UPDATE SET"
            " best_e1rm=?, last_weight=?, last_rpe=?, updated_at=?",
            (user_id, exercise_id, best, weight, rpe, _now(),
             best, weight, rpe, _now()))
        self.conn.commit()

    def record_exercise_feedback(self, user_id: str, exercise_id: str,
                                 preference=None, feel=None, discomfort=None,
                                 status=None, evidence: str = "",
                                 notes: str = "") -> None:
        """LLM 上报的动作反馈；空 discomfort 明确清除旧不适，不解除医疗限制。"""
        for value, lo, hi in ((preference, -2, 2), (feel, 0, 3)):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi):
                raise ValueError("动作反馈评分超出允许范围")
        if status is not None and status not in ("active", "avoid", "learning"):
            raise ValueError("未知动作状态")
        row = self.conn.execute(
            "SELECT * FROM user_exercise WHERE user_id=? AND exercise_id=?",
            (user_id, exercise_id)).fetchone()
        if not row:
            self.conn.execute(
                "INSERT INTO user_exercise(user_id, exercise_id, updated_at)"
                " VALUES(?,?,?)", (user_id, exercise_id, _now()))
        sets, params = [], []
        for col, val in (("preference", preference), ("feel", feel),
                         ("discomfort", discomfort), ("status", status),
                         ("evidence", evidence), ("notes", notes)):
            if val is not None and (val != "" or col == "discomfort"):
                sets.append(f"{col}=?")
                params.append(val)
        sets.append("updated_at=?")
        params.append(_now())
        params += [user_id, exercise_id]
        self.conn.execute(
            f"UPDATE user_exercise SET {', '.join(sets)}"
            " WHERE user_id=? AND exercise_id=?", params)
        self.conn.commit()

    def exercise_feedback_rows(self, user_id: str) -> list[dict]:
        """有反馈内容（偏好/发力感/不适/状态任一）的动作行，供 system prompt"""
        rows = self.conn.execute(
            "SELECT * FROM user_exercise WHERE user_id=? AND"
            " (preference IS NOT NULL OR feel IS NOT NULL"
            "  OR discomfort IS NOT NULL OR status IS NOT NULL)"
            " ORDER BY updated_at DESC LIMIT 10",
            (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def all_exercise_states(self, user_id: str) -> list[dict]:
        """全部动作状态行（含仅自动追踪的），供槽位式计划生成用"""
        rows = self.conn.execute(
            "SELECT * FROM user_exercise WHERE user_id=?", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_user_exercise(self, user_id: str, exercise_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM user_exercise WHERE user_id=? AND exercise_id=?",
            (user_id, exercise_id)).fetchone()
        return dict(row) if row else None

    # ---- coach_notes ----
    def add_coach_note(self, user_id: str, note: str, evidence: str,
                       expires_days: int | None = None) -> int:
        expires = None
        if expires_days:
            expires = (datetime.now() + timedelta(days=expires_days)
                       ).isoformat(timespec="seconds")
        cur = self.conn.execute(
            "INSERT INTO coach_notes(user_id, note, evidence, status,"
            " expires_at, created_at) VALUES(?,?,?,'open',?,?)",
            (user_id, note, evidence, expires, _now()))
        self.conn.commit()
        return cur.lastrowid

    def close_coach_note(self, user_id: str, note_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE coach_notes SET status='closed', closed_at=?"
            " WHERE user_id=? AND id=? AND status='open'",
            (_now(), user_id, note_id))
        self.conn.commit()
        return cur.rowcount > 0

    def open_coach_notes(self, user_id: str, limit: int = 8) -> list[dict]:
        now = _now()
        rows = self.conn.execute(
            "SELECT * FROM coach_notes WHERE user_id=? AND status='open'"
            " AND (expires_at IS NULL OR expires_at > ?)"
            " ORDER BY id DESC LIMIT ?",
            (user_id, now, limit)).fetchall()
        return [dict(r) for r in rows]
