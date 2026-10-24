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
    expires_at  TEXT,                   -- 适用期限（可空）：到期不再作为当前情况注入
    note_type   TEXT DEFAULT 'inference', -- 来源性质（C1）：fact/preference/observation/inference
    review_at   TEXT,                   -- 复核时点（可空）：到期提醒向用户确认仍适用
    created_at  TEXT,
    closed_at   TEXT
);
CREATE TABLE IF NOT EXISTS personal_trials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    change_desc TEXT NOT NULL,          -- 改变了什么（单一因素）
    reason      TEXT NOT NULL,          -- 为什么尝试
    observe     TEXT NOT NULL,          -- 观察什么
    stop_rule   TEXT NOT NULL,          -- 何时停止
    review_at   TEXT,                   -- 何时复盘
    outcome     TEXT,                   -- 结果（结束填写）：带混杂因素的个人观察
    decision    TEXT,                   -- keep / stop / adjust
    status      TEXT DEFAULT 'active',  -- active / ended
    created_at  TEXT,
    ended_at    TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_discussions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    source      TEXT NOT NULL,          -- 用户原话/来源描述（依据）
    topic       TEXT NOT NULL,
    claimed_conditions TEXT,            -- 该观点声称的适用条件
    verdict     TEXT NOT NULL,          -- consistent/conditional_useful/diverging/insufficient_evidence/not_suitable
    relation    TEXT,                   -- 与现有知识及个人情况的关系
    followup    TEXT,                   -- 后续待办
    related_card TEXT,                  -- 自动比对的已审核卡（可空；C3）
    status      TEXT DEFAULT 'active',  -- active / closed
    created_at  TEXT,
    closed_at   TEXT
);
CREATE TABLE IF NOT EXISTS training_approach (
    user_id     TEXT PRIMARY KEY,
    content     TEXT NOT NULL,          -- JSON：当前训练方式文档（2.0 B1）
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS approach_revisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    revision    INTEGER NOT NULL,
    content     TEXT NOT NULL,          -- JSON：该版本完整快照
    diff        TEXT NOT NULL,          -- JSON：[{field, old, new}]
    initiator   TEXT NOT NULL,          -- user / ai / system_migration
    reason      TEXT NOT NULL,
    confirmed   INTEGER NOT NULL DEFAULT 1,  -- AI 建议经确认后落库的版本记 0→确认时已为 1；手动/system 恒 1
    proposal_id TEXT,
    affected_plan_version INTEGER,     -- 变更时生效的计划版本（可空）
    created_at  TEXT NOT NULL,
    UNIQUE(user_id, revision)
);
CREATE TABLE IF NOT EXISTS change_proposals (
    id          TEXT PRIMARY KEY,       -- chg-<uuid>
    user_id     TEXT NOT NULL,
    target      TEXT NOT NULL,          -- approach / plan（2.0 B2）
    operations  TEXT NOT NULL,          -- JSON：类型化操作列表（非自由补丁）
    source      TEXT NOT NULL,          -- user_manual / ai / rule
    reason      TEXT NOT NULL,
    base_version TEXT NOT NULL,         -- JSON：{approach_revision} 或 {plan_id, plan_version}
    status      TEXT NOT NULL,          -- pending / applied / rejected / expired
    result      TEXT,                   -- JSON：执行结果摘要
    created_message_id INTEGER,
    created_at  TEXT NOT NULL,
    decided_at  TEXT
);
CREATE TABLE IF NOT EXISTS checkin_submissions (
    user_id     TEXT NOT NULL,
    submission_id TEXT NOT NULL,        -- 客户端稳定提交 ID（M1.1 P0-2 幂等）
    checkin_id  INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, submission_id)
);
CREATE TABLE IF NOT EXISTS agent_consultations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    question    TEXT NOT NULL,          -- 用户原话（M2：主教练咨询的原始问题）
    specialists TEXT NOT NULL,          -- JSON：本轮咨询的专业 Agent 列表
    advices     TEXT NOT NULL,          -- JSON：结构化 AgentAdvice（含知识依据）
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- text / markdown / pdf / article（M3 §6.4）
    origin      TEXT,                   -- URL 或出处说明
    content_hash TEXT NOT NULL,         -- 同内容重复导入去重
    status      TEXT NOT NULL,          -- saved（资料已保存≠内容审核通过）
    created_at  TEXT NOT NULL,
    UNIQUE(user_id, content_hash)
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL,
    seq         INTEGER NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    source_id   INTEGER NOT NULL,
    chunk_id    INTEGER,
    content     TEXT NOT NULL,
    claim_type  TEXT,                   -- 规则粗分类：method/principle/cue/nutrition/other
    status      TEXT NOT NULL,          -- pending_review / approved / rejected / quarantined
    risk_flag   TEXT,                   -- 高风险命中原因（隔离：不可作为处方依据）
    duplicate_of TEXT,                  -- JSON：相似既有内容命中
    conflict_with TEXT,                 -- JSON：疑似冲突的既有观点
    reviewed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    video_path  TEXT NOT NULL,
    subtitle_path TEXT,                 -- 用户提供的 srt/vtt（无则本地 whisper 转写）
    transcript  TEXT,                   -- JSON：[{start, end, text}]
    status      TEXT NOT NULL,          -- processing / ready / failed（兼作任务状态）
    error       TEXT,
    candidates  TEXT,                   -- JSON：动作候选（库匹配 + 证据句 + 时间戳）
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exercise_media_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    exercise_id TEXT NOT NULL,
    asset_id    INTEGER NOT NULL,
    cover_path  TEXT,                   -- 封面帧（可空：生成失败不阻塞关联）
    clip_path   TEXT,                   -- 演示片段（可空）
    sentence    TEXT,                   -- 关联依据（转写原句）
    start       REAL, "end" REAL,
    created_at  TEXT NOT NULL,
    UNIQUE(user_id, exercise_id, asset_id, start)
);
CREATE TABLE IF NOT EXISTS exercise_proposals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,          -- 新动作候选（用户确认，不入 exercises/ 库）
    aliases     TEXT,                   -- JSON list
    pattern     TEXT,
    note        TEXT,
    asset_id    INTEGER,
    sentence    TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending / approved / rejected（发起人批）
    created_at  TEXT NOT NULL
);
"""

# C1 记忆契约：笔记必须可回答"这是谁说的/怎么知道的"（DESIGN 26.2）
NOTE_TYPES = ("fact", "preference", "observation", "inference")

# C3 知识讨论闭环（26.3B）：讨论结论枚举；记录讨论 ≠ 批准知识用于处方
KD_VERDICTS = ("consistent", "conditional_useful", "diverging",
               "insufficient_evidence", "not_suitable")

DEFAULT_PROFILE = {
    "basic": {"name": "", "age": 0, "gender": "", "height_cm": 0, "weight_kg": 0},
    "experience": {"training_years": 0, "level": "beginner", "big3": {},
                  "recent_layoff_weeks": 0},
    "goal": {"primary": "", "phase": "", "target": "",
             "secondary": "", "timeline": ""},
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
        self._migrate_note_columns()

    def _migrate_note_columns(self) -> None:
        """老库增量补列；不动既有数据。"""
        for table, cols in (("coach_notes", ("note_type", "review_at")),
                            ("knowledge_discussions", ("related_card",))):
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col in cols:
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        self.conn.commit()

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
    def record_checkin(self, user_id: str, type_: str, data: dict) -> int:
        """运行时打卡、派生指标和旧规则建议失效一起提交，失败时一起回滚。"""
        from .exercises import library
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            cur = self.conn.execute(
                "INSERT INTO checkins(user_id,type,data,created_at) VALUES(?,?,?,?)",
                (user_id, type_, json.dumps(data, ensure_ascii=False), _now()))
            if type_ == "training":
                ids = {ex["exercise_id"] for ex in data.get("exercises", [])
                       if ex.get("exercise_id") and library.get(ex["exercise_id"])}
                self._recompute_exercise_states(user_id, ids)
            if type_ in ("training", "body"):
                profile = self.get_existing_profile(user_id)
                if profile.get("pending_adjustments"):
                    profile["pending_adjustments"] = [s for s in profile["pending_adjustments"]
                                                       if s.get("source") == "regenerate"]
                    self._write_profile(user_id, profile)
        return cur.lastrowid

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
                       expires_days: int | None = None,
                       note_type: str = "inference",
                       review_days: int | None = None) -> int:
        if note_type not in NOTE_TYPES:
            raise ValueError(f"未知笔记性质 {note_type!r}，须为 {NOTE_TYPES} 之一")
        expires = None
        if expires_days:
            expires = (datetime.now() + timedelta(days=expires_days)
                       ).isoformat(timespec="seconds")
        review = None
        if review_days:
            review = (datetime.now() + timedelta(days=review_days)
                      ).isoformat(timespec="seconds")
        cur = self.conn.execute(
            "INSERT INTO coach_notes(user_id, note, evidence, status,"
            " expires_at, note_type, review_at, created_at)"
            " VALUES(?,?,?,'open',?,?,?,?)",
            (user_id, note, evidence, expires, note_type, review, _now()))
        self.conn.commit()
        return cur.lastrowid

    def close_coach_note(self, user_id: str, note_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE coach_notes SET status='closed', closed_at=?"
            " WHERE user_id=? AND id=? AND status='open'",
            (_now(), user_id, note_id))
        self.conn.commit()
        return cur.rowcount > 0

    def get_coach_note(self, user_id: str, note_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM coach_notes WHERE user_id=? AND id=?",
                                (user_id, note_id)).fetchone()
        return dict(row) if row else None

    def open_coach_notes(self, user_id: str, limit: int = 8) -> list[dict]:
        now = _now()
        rows = self.conn.execute(
            "SELECT * FROM coach_notes WHERE user_id=? AND status='open'"
            " AND (expires_at IS NULL OR expires_at > ?)"
            " ORDER BY id DESC LIMIT ?",
            (user_id, now, limit)).fetchall()
        notes = [dict(r) for r in rows]
        for n in notes:
            n["due_review"] = bool(n.get("review_at") and n["review_at"] <= now)
        return notes

    def notes_for_reconfirm(self, user_id: str, limit: int = 3) -> list[dict]:
        """已过适用期但仍 open 的笔记：到期后先向用户确认，不静默当永久（26.2）。"""
        now = _now()
        rows = self.conn.execute(
            "SELECT * FROM coach_notes WHERE user_id=? AND status='open'"
            " AND expires_at IS NOT NULL AND expires_at <= ?"
            " ORDER BY id DESC LIMIT ?",
            (user_id, now, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---- knowledge_discussions（C3 知识讨论闭环，26.3B）----
    def add_knowledge_discussion(self, user_id: str, source: str, topic: str,
                                 claimed_conditions: str, verdict: str,
                                 relation: str = "", followup: str = "",
                                 related_card: str = "") -> int:
        if verdict not in KD_VERDICTS:
            raise ValueError(f"未知讨论结论 {verdict!r}，须为 {KD_VERDICTS} 之一")
        cur = self.conn.execute(
            "INSERT INTO knowledge_discussions(user_id, source, topic,"
            " claimed_conditions, verdict, relation, followup, related_card,"
            " status, created_at) VALUES(?,?,?,?,?,?,?,?,'active',?)",
            (user_id, source, topic, claimed_conditions, verdict,
             relation, followup, related_card, _now()))
        self.conn.commit()
        return cur.lastrowid

    def close_knowledge_discussion(self, user_id: str, item_id: int) -> bool:
        cur = self.conn.execute(
            "UPDATE knowledge_discussions SET status='closed', closed_at=?"
            " WHERE user_id=? AND id=? AND status='active'",
            (_now(), user_id, item_id))
        self.conn.commit()
        return cur.rowcount > 0

    def open_knowledge_discussions(self, user_id: str, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM knowledge_discussions WHERE user_id=? AND status='active'"
            " ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---- personal_trials（C4 有边界的个人尝试，26.3C）----
    def start_personal_trial(self, user_id: str, change_desc: str, reason: str,
                             observe: str, stop_rule: str,
                             review_days: int | None = None) -> int:
        row = self.conn.execute(
            "SELECT id, change_desc FROM personal_trials WHERE user_id=? AND status='active'",
            (user_id,)).fetchone()
        if row:
            raise ValueError(
                f"已有进行中的尝试 #{row['id']}「{row['change_desc']}」——"
                "每次只改一个因素，先结束它再开新的")
        review = None
        if review_days:
            review = (datetime.now() + timedelta(days=review_days)
                      ).isoformat(timespec="seconds")
        cur = self.conn.execute(
            "INSERT INTO personal_trials(user_id, change_desc, reason, observe,"
            " stop_rule, review_at, status, created_at) VALUES(?,?,?,?,?,?,'active',?)",
            (user_id, change_desc, reason, observe, stop_rule, review, _now()))
        self.conn.commit()
        return cur.lastrowid

    def end_personal_trial(self, user_id: str, trial_id: int,
                           outcome: str, decision: str) -> bool:
        if decision not in ("keep", "stop", "adjust"):
            raise ValueError("decision 必须是 keep/stop/adjust 之一")
        cur = self.conn.execute(
            "UPDATE personal_trials SET status='ended', outcome=?, decision=?, ended_at=?"
            " WHERE user_id=? AND id=? AND status='active'",
            (outcome, decision, _now(), user_id, trial_id))
        self.conn.commit()
        return cur.rowcount > 0

    def personal_trials(self, user_id: str, limit: int = 4) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM personal_trials WHERE user_id=?"
            " ORDER BY (status='active') DESC, id DESC LIMIT ?",
            (user_id, limit)).fetchall()
        now = _now()
        out = [dict(r) for r in rows]
        for t in out:
            t["due_review"] = bool(t["status"] == "active" and t.get("review_at")
                                   and t["review_at"] <= now)
        return out

    # ---- training_approach / change_proposals（2.0 B1/B2）----
    def get_approach(self, user_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT content FROM training_approach WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row["content"]) if row else None

    def save_approach(self, user_id: str, content: dict) -> None:
        self.conn.execute(
            "INSERT INTO training_approach(user_id, content, updated_at)"
            " VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET content=?, updated_at=?",
            (user_id, json.dumps(content, ensure_ascii=False), _now(),
             json.dumps(content, ensure_ascii=False), _now()))
        self.conn.commit()

    def add_approach_revision(self, user_id: str, revision: int, content: dict,
                              diff: list, initiator: str, reason: str,
                              confirmed: bool = True, proposal_id: str | None = None,
                              affected_plan_version: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO approach_revisions(user_id, revision, content, diff,"
            " initiator, reason, confirmed, proposal_id, affected_plan_version,"
            " created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id, revision, json.dumps(content, ensure_ascii=False),
             json.dumps(diff, ensure_ascii=False), initiator, reason,
             int(confirmed), proposal_id, affected_plan_version, _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_approach_revision(self, user_id: str, revision: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM approach_revisions WHERE user_id=? AND revision=?",
            (user_id, revision)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["content"] = json.loads(out["content"])
        out["diff"] = json.loads(out["diff"])
        return out

    def list_approach_revisions(self, user_id: str, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT revision, initiator, reason, confirmed, proposal_id,"
            " affected_plan_version, created_at, diff FROM approach_revisions"
            " WHERE user_id=? ORDER BY revision DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [{**dict(r), "diff": json.loads(r["diff"])} for r in rows]

    def insert_proposal(self, proposal: dict) -> None:
        self.conn.execute(
            "INSERT INTO change_proposals(id, user_id, target, operations, source,"
            " reason, base_version, status, created_message_id, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (proposal["id"], proposal["user_id"], proposal["target"],
             json.dumps(proposal["operations"], ensure_ascii=False),
             proposal["source"], proposal["reason"],
             json.dumps(proposal["base_version"], ensure_ascii=False),
             proposal["status"], proposal.get("created_message_id"), _now()))
        self.conn.commit()

    def get_proposal(self, user_id: str, proposal_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM change_proposals WHERE user_id=? AND id=?",
            (user_id, proposal_id)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["operations"] = json.loads(out["operations"])
        out["base_version"] = json.loads(out["base_version"])
        if out.get("result"):
            out["result"] = json.loads(out["result"])
        return out

    def list_proposals(self, user_id: str, status: str | None = None,
                       limit: int = 20) -> list[dict]:
        sql = ("SELECT id, target, source, reason, status, base_version,"
               " operations, result, created_at, decided_at"
               " FROM change_proposals WHERE user_id=?")
        params: list = [user_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["base_version"] = json.loads(d["base_version"])
            d["operations"] = json.loads(d["operations"])
            if d.get("result"):
                d["result"] = json.loads(d["result"])
            out.append(d)
        return out

    def decide_proposal(self, user_id: str, proposal_id: str, status: str,
                        result: dict | None = None) -> bool:
        cur = self.conn.execute(
            "UPDATE change_proposals SET status=?, result=?, decided_at=?"
            " WHERE user_id=? AND id=? AND status='pending'",
            (status, json.dumps(result, ensure_ascii=False) if result is not None else None,
             _now(), user_id, proposal_id))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- checkin_submissions（M1.1 P0-2：客户端提交 ID 幂等）----
    def get_checkin_submission(self, user_id: str, submission_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT checkin_id, created_at FROM checkin_submissions"
            " WHERE user_id=? AND submission_id=?", (user_id, submission_id)).fetchone()
        return dict(row) if row else None

    def record_checkin_submission(self, user_id: str, submission_id: str,
                                  checkin_id: int) -> bool:
        """记录提交 ID；已存在返回 False（重试场景，调用方改取既有结果）。"""
        try:
            self.conn.execute(
                "INSERT INTO checkin_submissions(user_id, submission_id,"
                " checkin_id, created_at) VALUES(?,?,?,?)",
                (user_id, submission_id, checkin_id, _now()))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    # ---- agent_consultations（M2：多智能体咨询留痕，可追溯依据）----
    def add_consultation(self, user_id: str, question: str,
                         specialists: list, advices: list) -> int:
        cur = self.conn.execute(
            "INSERT INTO agent_consultations(user_id, question, specialists,"
            " advices, created_at) VALUES(?,?,?,?,?)",
            (user_id, question[:500], json.dumps(specialists, ensure_ascii=False),
             json.dumps(advices, ensure_ascii=False), _now()))
        self.conn.commit()
        return cur.lastrowid

    def list_consultations(self, user_id: str, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, question, specialists, advices, created_at"
            " FROM agent_consultations WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [{"id": r["id"], "question": r["question"],
                 "specialists": json.loads(r["specialists"]),
                 "advices": json.loads(r["advices"]), "at": r["created_at"]}
                for r in rows]

    def get_plan_by_version(self, user_id: str, version: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, content FROM plans WHERE user_id=? AND version=?",
            (user_id, version)).fetchone()
        return ({"id": row["id"], "content": json.loads(row["content"])} if row else None)

    def list_plan_versions(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, version, active, created_at, content FROM plans"
            " WHERE user_id=? ORDER BY version DESC LIMIT ?",
            (user_id, limit)).fetchall()
        out = []
        for r in rows:
            content = json.loads(r["content"])
            out.append({"id": r["id"], "version": r["version"],
                        "active": bool(r["active"]), "at": r["created_at"],
                        "action": content.get("adjust_action"),
                        "reason": content.get("adjust_reason"),
                        "template": content.get("template"),
                        "days": [d.get("day") for d in content.get("schedule", [])]})
        return out

    # ---- M3：统一知识库（knowledge_sources / chunks / claims）----
    def add_knowledge_source(self, user_id: str, title: str, kind: str,
                             origin: str, content_hash: str) -> int | None:
        """同内容重复导入返回 None（调用方提示已存在）。"""
        try:
            cur = self.conn.execute(
                "INSERT INTO knowledge_sources(user_id, title, kind, origin,"
                " content_hash, status, created_at) VALUES(?,?,?,?,?,'saved',?)",
                (user_id, title[:200], kind, origin, content_hash, _now()))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def find_knowledge_source(self, user_id: str, content_hash: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, title, kind, created_at FROM knowledge_sources"
            " WHERE user_id=? AND content_hash=?", (user_id, content_hash)).fetchone()
        return dict(row) if row else None

    def add_knowledge_chunk(self, source_id: int, seq: int, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO knowledge_chunks(source_id, seq, content, created_at)"
            " VALUES(?,?,?,?)", (source_id, seq, content, _now()))
        self.conn.commit()
        return cur.lastrowid

    def add_knowledge_claim(self, user_id: str, source_id: int, chunk_id: int | None,
                            content: str, claim_type: str, status: str,
                            risk_flag: str | None = None,
                            duplicate_of: str | None = None,
                            conflict_with: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO knowledge_claims(user_id, source_id, chunk_id, content,"
            " claim_type, status, risk_flag, duplicate_of, conflict_with,"
            " created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id, source_id, chunk_id, content[:1000], claim_type, status,
             risk_flag, duplicate_of, conflict_with, _now()))
        self.conn.commit()
        return cur.lastrowid

    def list_knowledge_claims(self, user_id: str, status: str | None = None,
                              limit: int = 100) -> list[dict]:
        sql = ("SELECT kc.*, ks.title AS source_title, ks.kind AS source_kind"
               " FROM knowledge_claims kc JOIN knowledge_sources ks"
               " ON kc.source_id=ks.id WHERE kc.user_id=?")
        params: list = [user_id]
        if status:
            sql += " AND kc.status=?"
            params.append(status)
        sql += " ORDER BY kc.id DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for key in ("duplicate_of", "conflict_with"):
                if d.get(key):
                    try:
                        d[key] = json.loads(d[key])
                    except ValueError:
                        pass
            out.append(d)
        return out

    def get_knowledge_claim(self, user_id: str, claim_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM knowledge_claims WHERE user_id=? AND id=?",
            (user_id, claim_id)).fetchone()
        return dict(row) if row else None

    def review_knowledge_claim(self, user_id: str, claim_id: int,
                               decision: str) -> bool:
        cur = self.conn.execute(
            "UPDATE knowledge_claims SET status=?, reviewed_at=?"
            " WHERE user_id=? AND id=? AND status='pending_review'",
            (decision, _now(), user_id, claim_id))
        self.conn.commit()
        return cur.rowcount > 0

    def list_knowledge_sources(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT s.id, s.title, s.kind, s.origin, s.created_at,"
            " (SELECT COUNT(*) FROM knowledge_claims c"
            "  WHERE c.source_id=s.id AND c.status='approved') AS approved,"
            " (SELECT COUNT(*) FROM knowledge_claims c"
            "  WHERE c.source_id=s.id AND c.status='pending_review') AS pending,"
            " (SELECT COUNT(*) FROM knowledge_claims c"
            "  WHERE c.source_id=s.id AND c.status='quarantined') AS quarantined"
            " FROM knowledge_sources s WHERE s.user_id=? ORDER BY s.id DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def search_user_knowledge(self, user_id: str, keywords: list[str],
                              limit: int = 10) -> list[dict]:
        """用户导入中 approved 的观点检索（pending/quarantined 不进结果）。"""
        if not keywords:
            return []
        rows = self.conn.execute(
            "SELECT kc.id, kc.content, kc.claim_type, ks.title AS source_title"
            " FROM knowledge_claims kc JOIN knowledge_sources ks"
            " ON kc.source_id=ks.id"
            " WHERE kc.user_id=? AND kc.status='approved' ORDER BY kc.id DESC",
            (user_id,)).fetchall()
        out = []
        for r in rows:
            text = r["content"]
            if any(k in text for k in keywords):
                out.append(dict(r))
                if len(out) >= limit:
                    break
        return out

    def approved_user_claim_texts(self, user_id: str, limit: int = 500) -> list[str]:
        rows = self.conn.execute(
            "SELECT content FROM knowledge_claims WHERE user_id=?"
            " AND status='approved' ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
        return [r["content"] for r in rows]

    # ---- M3.2：视频导入（media_assets / 链接 / 新动作候选）----
    def add_media_asset(self, user_id: str, title: str, video_path: str,
                        subtitle_path: str | None) -> int:
        cur = self.conn.execute(
            "INSERT INTO media_assets(user_id, title, video_path, subtitle_path,"
            " status, created_at) VALUES(?,?,?,?, 'processing', ?)",
            (user_id, title[:200], video_path, subtitle_path, _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_media_asset(self, user_id: str, asset_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM media_assets WHERE user_id=? AND id=?",
            (user_id, asset_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("transcript", "candidates"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except ValueError:
                    d[key] = []
        return d

    def list_media_assets(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, title, status, error, candidates, created_at FROM media_assets"
            " WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["candidates"] = json.loads(d["candidates"] or "[]")
            except ValueError:
                d["candidates"] = []
            out.append(d)
        return out

    def update_media_asset(self, asset_id: int, *, status: str,
                           transcript: list | None = None,
                           candidates: list | None = None,
                           error: str | None = None) -> None:
        sets = ["status=?"]
        params: list = [status]
        if transcript is not None:
            sets.append("transcript=?")
            params.append(json.dumps(transcript, ensure_ascii=False))
        if candidates is not None:
            sets.append("candidates=?")
            params.append(json.dumps(candidates, ensure_ascii=False))
        if error is not None:
            sets.append("error=?")
            params.append(error[:500])
        params.append(asset_id)
        self.conn.execute(f"UPDATE media_assets SET {', '.join(sets)} WHERE id=?", params)
        self.conn.commit()

    def add_exercise_media_link(self, user_id: str, exercise_id: str, asset_id: int,
                                sentence: str, start: float, end: float,
                                cover_path: str | None, clip_path: str | None) -> int | None:
        try:
            cur = self.conn.execute(
                'INSERT INTO exercise_media_links(user_id, exercise_id, asset_id,'
                ' cover_path, clip_path, sentence, start, "end", created_at)'
                ' VALUES(?,?,?,?,?,?,?,?,?)',
                (user_id, exercise_id, asset_id, cover_path, clip_path,
                 sentence[:300], start, end, _now()))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def list_exercise_media(self, user_id: str, exercise_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT l.*, a.title AS asset_title FROM exercise_media_links l"
            " JOIN media_assets a ON l.asset_id=a.id"
            " WHERE l.user_id=? AND l.exercise_id=? ORDER BY l.id DESC",
            (user_id, exercise_id)).fetchall()
        return [dict(r) for r in rows]

    def add_exercise_proposal(self, user_id: str, name: str, aliases: list,
                              pattern: str, note: str, asset_id: int | None,
                              sentence: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO exercise_proposals(user_id, name, aliases, pattern,"
            " note, asset_id, sentence, status, created_at)"
            " VALUES(?,?,?,?,?,?,?, 'pending', ?)",
            (user_id, name[:100], json.dumps(aliases, ensure_ascii=False),
             pattern, note[:500], asset_id, sentence[:300], _now()))
        self.conn.commit()
        return cur.lastrowid

    def list_exercise_proposals(self, user_id: str,
                                status: str | None = "pending") -> list[dict]:
        sql = ("SELECT * FROM exercise_proposals WHERE user_id=?")
        params: list = [user_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY id DESC", params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["aliases"] = json.loads(d.get("aliases") or "[]")
            except ValueError:
                d["aliases"] = []
            out.append(d)
        return out
