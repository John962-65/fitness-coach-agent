"""SQLite 数据层（四表：users / plans / checkins / messages）"""
from __future__ import annotations

import json
import sqlite3
import uuid
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
CREATE TABLE IF NOT EXISTS training_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  doc TEXT NOT NULL,
  created_at TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS custom_exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    ex_id       TEXT NOT NULL,           -- 用户自定义动作 id（M5.2 P0-1：独立存储，不入全局库）
    doc         TEXT NOT NULL,           -- JSON：与内置动作同构
    source      TEXT NOT NULL DEFAULT 'user_created',
    created_at  TEXT NOT NULL,
    UNIQUE(user_id, ex_id)
);
CREATE TABLE IF NOT EXISTS motion_analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    exercise_id TEXT NOT NULL,
    view        TEXT NOT NULL,          -- side / front / back
    video_path  TEXT NOT NULL,
    status      TEXT NOT NULL,          -- processing / ready / failed（M4 任务状态）
    error       TEXT,
    result      TEXT,                   -- JSON：supported/frames/faults/reps/summary/note
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expert_tasks (
    id          TEXT PRIMARY KEY,       -- ext-<uuid>
    user_id     TEXT NOT NULL,
    specialist  TEXT NOT NULL,          -- training_science / nutrition / ...
    task_type   TEXT NOT NULL,          -- post-workout-review / ...
    trigger_source TEXT NOT NULL,       -- WorkoutSaved / UserRequested / ...（trigger 是 SQL 关键字）
    input_refs  TEXT NOT NULL,          -- JSON：{checkin_id, exercise_ids, ...}
    dedup_key   TEXT,                   -- 幂等键（NULL=允许重复，如用户主动请求）
    status      TEXT NOT NULL,          -- pending / running / ready / failed / cancelled
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    insight_id  TEXT,                   -- 产出的 ExpertInsight
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    completed_at TEXT,
    heartbeat_at TEXT,                  -- running 崩溃恢复判定
    error_code  TEXT,
    error       TEXT,
    UNIQUE(user_id, dedup_key)          -- 同一事件不重复入队（NULL 互不冲突）
);
CREATE TABLE IF NOT EXISTS expert_task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    event   TEXT NOT NULL,              -- enqueued/started/retry/ready/failed/cancelled
    detail  TEXT,
    at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expert_insights (
    id          TEXT PRIMARY KEY,       -- ins-<uuid>
    user_id     TEXT NOT NULL,
    task_id     TEXT,
    specialist  TEXT NOT NULL,
    insight_type TEXT NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    findings    TEXT NOT NULL,          -- JSON：[{finding_id, text, fact_ids, source_ids}]
    evidence_refs TEXT NOT NULL,        -- JSON：全部引用的 fact_id
    facts_snapshot TEXT NOT NULL,       -- JSON：生成时的 fact_service 输出（证据面板用）
    knowledge_refs TEXT NOT NULL,       -- JSON：知识检索命中（引擎:ref + 出处）
    options     TEXT NOT NULL,          -- JSON：[{option_id, title, detail, basis,
                                        --   tradeoffs, proposal_hint?}]
    limitations TEXT NOT NULL,          -- JSON：[str]
    status      TEXT NOT NULL,          -- ready / viewed / dismissed / expired /
                                        -- invalidated / failed（分析在任务侧，不占洞察行）
    confidence  TEXT NOT NULL,          -- high / medium / low——按数据充分性规则生成
    confidence_basis TEXT NOT NULL,     -- 为什么是这个置信度（人可读）
    generated_at TEXT NOT NULL,
    expires_at  TEXT,                   -- 过期时点（懒判定）
    source_revision TEXT NOT NULL,      -- JSON：{checkins:{id:rev}, plan_version}
    input_refs  TEXT,                   -- JSON：分析输入（重新分析用）
    read_at     TEXT
);
CREATE TABLE IF NOT EXISTS expert_settings (
    user_id     TEXT PRIMARY KEY,
    proactive_enabled INTEGER NOT NULL DEFAULT 1,   -- 用户可关闭主动分析
    min_interval_minutes INTEGER NOT NULL DEFAULT 0, -- 同类任务最小间隔（频率限制）
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS foods (
    id          TEXT PRIMARY KEY,       -- food-<uuid>（自定义）/ bi-<slug>（内置）
    user_id     TEXT,                   -- NULL=内置公共；自定义按用户隔离
    name        TEXT NOT NULL,
    aliases     TEXT NOT NULL,          -- JSON list
    brand       TEXT,
    category    TEXT NOT NULL,          -- staple/meat/seafood/egg_dairy/soy/vegetable/fruit/nuts/oil/processed/beverage/other
    serving_units TEXT NOT NULL,        -- JSON：[{unit,grams}] 首项为基准（克/毫升）
    energy_kcal REAL,                   -- 以下营养值均对应 reference_amount；NULL=未知（绝不用 0 冒充）
    protein_g   REAL,
    carbohydrate_g REAL,
    fat_g       REAL,
    fiber_g     REAL,
    sodium_mg   REAL,
    reference_amount REAL NOT NULL DEFAULT 100,
    reference_unit TEXT NOT NULL DEFAULT 'g',
    source_name TEXT,
    source_url  TEXT,
    source_version TEXT,
    license     TEXT,
    verified_status TEXT NOT NULL,      -- reference（公开参考值）/ user_created
    created_at  TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_builtin_name ON foods(name) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_foods_user_name ON foods(user_id, name);
CREATE TABLE IF NOT EXISTS meal_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    local_date  TEXT NOT NULL,          -- YYYY-MM-DD
    meal_type   TEXT NOT NULL,          -- breakfast/lunch/dinner/snack
    items       TEXT NOT NULL,          -- JSON MealItem[]（含记录时营养快照）
    notes       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meals_user_date ON meal_entries(user_id, local_date);
CREATE TABLE IF NOT EXISTS nutrition_days (
    user_id     TEXT NOT NULL,
    local_date  TEXT NOT NULL,
    complete    INTEGER NOT NULL DEFAULT 0,  -- 用户标记当天记录是否完整
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, local_date)
);
CREATE TABLE IF NOT EXISTS nutrition_targets (
    user_id     TEXT PRIMARY KEY,
    energy_kcal REAL,                   -- 手动设置；NULL=未设置（估算建议另算，不代填）
    protein_g   REAL,
    carbohydrate_g REAL,
    fat_g       REAL,
    preferences TEXT NOT NULL DEFAULT '{}',  -- JSON：饮食偏好
    allergies   TEXT NOT NULL DEFAULT '[]',  -- JSON：过敏与限制
    budget_note TEXT,
    precision_willing TEXT,             -- willing_precise / rough / minimal
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nutrition_recipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    items       TEXT NOT NULL,          -- JSON MealItem[]（快照，可整餐复用）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS body_measurements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    measured_at TEXT NOT NULL,          -- 测量时间（ISO；缺省=录入时间）
    local_date  TEXT NOT NULL,          -- YYYY-MM-DD
    timezone    TEXT,
    weight_kg   REAL,                   -- 以下指标全部可选；NULL=未测量（绝不用 0 冒充）
    waist_cm    REAL,
    hip_cm      REAL,
    chest_cm    REAL,
    body_fat_percent REAL,
    muscle_mass_kg REAL,
    measurement_method TEXT,            -- home_scale / tape / dexa / import / ...
    device_source TEXT,                 -- 设备/来源（不同来源估算值不可默认可比）
    notes       TEXT,
    migrated_from TEXT,                 -- checkin:{id}（旧 body 打卡迁移来源）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_body_user_date ON body_measurements(user_id, local_date);
CREATE TABLE IF NOT EXISTS body_measurement_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    measurement_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    old_data TEXT NOT NULL,
    new_data TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(measurement_id, revision)
);
CREATE TABLE IF NOT EXISTS recovery_checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    local_date  TEXT NOT NULL,          -- 每用户每天一条（编辑走修订）
    recorded_at TEXT NOT NULL,
    timezone    TEXT,
    sleep_hours REAL,                   -- 全部可选；NULL=未填写（不默认"正常"）
    sleep_quality INTEGER,              -- 主观 1-5（5=非常好，方向全局统一）
    fatigue     INTEGER,                -- 1-5（5=非常疲劳）
    muscle_soreness INTEGER,            -- 1-5（5=非常酸痛）
    training_readiness INTEGER,         -- 1-5（5=状态很好想练）
    soreness_regions TEXT NOT NULL DEFAULT '[]',  -- JSON list
    notes       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(user_id, local_date)
);
CREATE TABLE IF NOT EXISTS recovery_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    recovery_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    old_data TEXT NOT NULL,
    new_data TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(recovery_id, revision)
);
CREATE TABLE IF NOT EXISTS record_submissions (
    user_id     TEXT NOT NULL,
    submission_id TEXT NOT NULL,        -- 客户端幂等提交 ID（body/recovery 通用）
    kind        TEXT NOT NULL,          -- body / recovery
    record_id   INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, submission_id)
);
CREATE TABLE IF NOT EXISTS symptom_episodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    body_region TEXT NOT NULL,          -- knee/shoulder/...（与限制区域同一映射表）
    side        TEXT,                   -- left / right / bilateral / NULL
    onset_at    TEXT NOT NULL,          -- 大致发生时间（日期或日期时间）
    onset_context TEXT,                 -- 与某次运动相关 / 逐渐出现 / 外伤等（用户原话）
    description TEXT NOT NULL,          -- 用户自述（首录原话）
    related_checkin_id INTEGER,         -- 关联训练（可空）
    professional_evaluated INTEGER NOT NULL DEFAULT 0,  -- 是否已接受专业评估
    status      TEXT NOT NULL DEFAULT 'active',   -- active / resolved / monitoring
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symptom_user ON symptom_episodes(user_id, status);
CREATE TABLE IF NOT EXISTS symptom_observations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id  INTEGER NOT NULL,
    user_id     TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    severity    INTEGER,                -- 1-10 自报程度（不单独推断损伤严重度）
    symptom_description TEXT,
    functional_limitations TEXT NOT NULL DEFAULT '[]',  -- JSON list（影响的活动）
    user_notes  TEXT,
    triage_result TEXT,                 -- JSON：本次观察的安全分流结果快照
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symptom_obs_episode ON symptom_observations(episode_id);
CREATE TABLE IF NOT EXISTS imported_device_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    metric      TEXT NOT NULL,          -- weight/sleep_hours/heart_rate/exercise_minutes/steps/distance
    value       REAL NOT NULL,
    unit        TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    source_platform TEXT NOT NULL,      -- healthkit / health_connect / csv:xxx
    source_device   TEXT,
    source_record_id TEXT NOT NULL,     -- 平台记录 ID（去重键）
    measurement_method TEXT,
    imported_at TEXT NOT NULL,
    UNIQUE(user_id, source_platform, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_imported_device_user ON
    imported_device_records(user_id, metric, measured_at);
CREATE TABLE IF NOT EXISTS training_restrictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    source_type TEXT NOT NULL,          -- user_reported / professional / triage_recommended
    source_evidence TEXT NOT NULL,      -- 用户原话或专业人员说明（留痕）
    affected_activities TEXT NOT NULL,  -- JSON：{regions:[], movements:[], notes}
    restriction_description TEXT NOT NULL,
    related_episode_id INTEGER,         -- 关联不适事件（可空）
    effective_at TEXT NOT NULL,
    review_at   TEXT,                   -- 复核时点
    status      TEXT NOT NULL DEFAULT 'active',   -- active / lifted / expired
    lift_evidence TEXT,                 -- 解除依据（professional 需专业人员说明）
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_restriction_user ON training_restrictions(user_id, status);
CREATE TABLE IF NOT EXISTS training_restriction_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    restriction_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    old_data TEXT NOT NULL,
    new_data TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(restriction_id, revision)
);
CREATE TABLE IF NOT EXISTS care_plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL,
    professional_source TEXT NOT NULL,  -- 专业人员来源说明（用户录入）
    applicable_conditions TEXT,
    related_episode_id INTEGER,
    review_at   TEXT,
    status      TEXT NOT NULL DEFAULT 'active',   -- active / completed / paused
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS care_activities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id     INTEGER NOT NULL,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    frequency   TEXT,                   -- 用户录入的执行频率（软件不自行提高）
    notes       TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS care_activity_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    user_id     TEXT NOT NULL,
    local_date  TEXT NOT NULL,
    completed   INTEGER NOT NULL,       -- 是否执行
    feedback    TEXT,                   -- 用户反馈（如疼痛变化）
    created_at  TEXT NOT NULL,
    UNIQUE(activity_id, local_date)
);
CREATE TABLE IF NOT EXISTS motion_tech_profiles (
    analysis_id INTEGER PRIMARY KEY,    -- 1:1 挂 motion_analyses（不产生两套历史）
    user_id     TEXT NOT NULL,
    exercise_id TEXT NOT NULL,
    model_version TEXT NOT NULL,        -- 分析模型/规则版本（升级可追溯）
    video_quality TEXT NOT NULL,        -- JSON：{status, view, detection_ratio, valid_ratio, limitations}
    motion_observations TEXT NOT NULL,  -- JSON：[{kind, text}]
    phase_timestamps TEXT NOT NULL,     -- JSON：[{rep, start_s, end_s, peak_s}]
    review_status TEXT NOT NULL DEFAULT 'unreviewed',  -- 系统生成结果未经人工复核
    user_notes  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mtp_user_ex ON motion_tech_profiles(user_id, exercise_id);
CREATE TABLE IF NOT EXISTS user_equipment (
    user_id      TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    aliases      TEXT NOT NULL DEFAULT '[]',
    fulfills     TEXT,                  -- 可选：等效的系统器械稳定 ID
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, equipment_id)
);
CREATE TABLE IF NOT EXISTS training_locations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            TEXT NOT NULL,
    name               TEXT NOT NULL,
    kind               TEXT NOT NULL,   -- gym / home / outdoor / custom
    required_equipment TEXT NOT NULL DEFAULT '[]',
    optional_equipment TEXT NOT NULL DEFAULT '[]',
    is_current         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    UNIQUE(user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_locations_user ON training_locations(user_id, is_current);
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
                            ("knowledge_discussions", ("related_card",)),
                            ("personal_trials", ("baseline",))):
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col in cols:
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        # P5-C3：个人尝试与进阶候选/计划上下文关联（可空；老数据保持 NULL）
        trial_cols = (("origin", "TEXT"), ("exercise_id", "TEXT"),
                      ("plan_id", "TEXT"), ("plan_version", "TEXT"),
                      ("chosen_target", "TEXT"), ("observation_metric", "TEXT"),
                      ("observation_window_days", "TEXT"),
                      ("min_sessions", "TEXT"),
                      ("baseline_source_revisions", "TEXT"))
        have = {r["name"] for r in self.conn.execute("PRAGMA table_info(personal_trials)")}
        for col, decl in trial_cols:
            if col not in have:
                self.conn.execute(
                    f"ALTER TABLE personal_trials ADD COLUMN {col} {decl}")
        self.conn.commit()

    # ---- users ----
    def upsert_imported_device_record(self, user_id: str, r: dict) -> bool:
        """P7-C 设备导入（只读观察数据，独立存储，不与手动记录混算）。"""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO imported_device_records(user_id, metric,"
            " value, unit, measured_at, source_platform, source_device,"
            " source_record_id, measurement_method, imported_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id, r["metric"], r["value"], r["unit"], r["measured_at"],
             r["source_platform"], r.get("source_device"),
             r["source_record_id"], r.get("measurement_method"), _now()))
        self.conn.commit()
        return cur.rowcount > 0

    def list_imported_device_records(self, user_id: str, metric: str | None = None,
                                     limit: int = 200) -> list[dict]:
        sql = ("SELECT * FROM imported_device_records WHERE user_id=?")
        params: list = [user_id]
        if metric:
            sql += " AND metric=?"
            params.append(metric)
        return [dict(r) for r in self.conn.execute(
            sql + " ORDER BY measured_at DESC LIMIT ?",
            params + [limit]).fetchall()]

    def delete_user(self, user_id: str) -> dict:
        """P7-B 账户删除：删除该用户在所有带 user_id 列的表中的数据。

        返回逐表删除计数；媒体文件本体留在磁盘（清单随 media_assets
        行删除，文件回收由部署级清理完成）。不可逆操作由调用方确认。
        """
        tables = [r["name"] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        counts: dict = {}
        with self.conn:
            for t in sorted(tables):
                cols = [r["name"] for r in self.conn.execute(
                    f"PRAGMA table_info({t})").fetchall()]
                if "user_id" in cols:
                    cur = self.conn.execute(
                        f"DELETE FROM {t} WHERE user_id=?", (user_id,))
                    if cur.rowcount:
                        counts[t] = cur.rowcount
        return counts

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
        """运行时打卡、派生指标和旧规则建议失效一起提交，失败时一起回滚。

        P2 兼容：type='body' 统一转发到身体测量模块（单一权威存储），
        返回测量记录 id——旧接口（含 agent 打卡）无感，新旧数据不分裂。
        """
        if type_ == "body":
            from .body.measurement_service import record_from_checkin
            return record_from_checkin(self, user_id, data)
        from .exercises import library
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            cur = self.conn.execute(
                "INSERT INTO checkins(user_id,type,data,created_at) VALUES(?,?,?,?)",
                (user_id, type_, json.dumps(data, ensure_ascii=False), _now()))
            if type_ == "training":
                # M6.3.1：自定义动作同样进入派生状态（用户可见动作统一定位）
                ids = {ex["exercise_id"] for ex in data.get("exercises", [])
                       if ex.get("exercise_id")
                       and (library.get(ex["exercise_id"])
                            or self.get_custom_exercise(user_id, ex["exercise_id"]))}
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

    def list_checkins(self, user_id: str, limit: int = 20, offset: int = 0,
                      date: str | None = None) -> list[dict]:
        """date 过滤与日历聚合使用同一口径（session_local_date：会话本地日期优先，
        旧记录回退服务器时间）——SQL 只做窗口粗筛，精确过滤在 Python 侧完成。"""
        from .analytics.exercise_metrics import session_local_date
        sql = ("SELECT c.id,c.type,c.data,c.created_at,"
               " (SELECT COUNT(*) FROM checkin_revisions r WHERE r.checkin_id=c.id) AS revision,"
               " (SELECT reason FROM checkin_revisions r WHERE r.checkin_id=c.id"
               "  ORDER BY r.revision DESC LIMIT 1) AS last_reason"
               " FROM checkins c WHERE c.user_id=?")
        params: list = [user_id]
        if date:
            # 窗口粗筛：±2 天覆盖跨时区/跨日场景，精确口径由 session_local_date 统一判定
            base = date
            yy, mm, dd = int(base[:4]), int(base[5:7]), int(base[8:10])
            from datetime import date as _d, timedelta as _td
            lo = (_d(yy, mm, dd) - _td(days=2)).isoformat()
            hi = (_d(yy, mm, dd) + _td(days=3)).isoformat()
            sql += " AND c.created_at >= ? AND c.created_at < ?"
            params.extend([lo, hi])
        sql += " ORDER BY c.id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            data = json.loads(r["data"])
            if date and session_local_date(r["created_at"], data) != date:
                continue
            out.append({"id": r["id"], "revision": r["revision"], "last_reason": r["last_reason"],
                        "type": r["type"], "data": data, "at": r["created_at"]})
        return out[offset:offset + limit]

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
                    # M6.3.1：自定义动作同样参与派生状态（按用户可见动作统一定位）
                    if isinstance(eid, str) and (library.get(eid)
                                                 or self.get_custom_exercise(user_id, eid)):
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

    def _visible_exercise_name(self, user_id: str, eid: str) -> str:
        """用户可见动作的名称（内置优先，回退本人自定义）。"""
        from .exercises import library
        doc = library.get(eid)
        if doc:
            return doc["name"]
        custom = self.get_custom_exercise(user_id, eid)
        return str(custom.get("name") or eid) if custom else eid

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
                # M6.4-A.1：分型——仅 weight_reps 口径参与杠铃式 e1RM；
                # bodyweight_reps 的聚合 weight_kg 是"额外负重"，不能套用 Epley
                stype = None
                logs = ex.get("set_logs")
                if isinstance(logs, list):
                    for l in logs:
                        if isinstance(l, dict) and not l.get("warmup"):
                            stype = l.get("type") or "weight_reps"
                            break
                for eid, state in values.items():
                    # M6.3.1：已验证稳定 ID 直接命中（含自定义动作）；旧记录回退名称匹配
                    if ex.get("exercise_id") != eid and not _same_exercise(
                            self._visible_exercise_name(user_id, eid), ex):
                        continue
                    weight, rpe = _to_number(ex.get("weight_kg")), _to_number(ex.get("rpe"))
                    score = (e1rm(weight, _to_reps(ex.get("reps")))
                             if stype in (None, "weight_reps") else None)
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
                             review_days: int | None = None,
                             baseline: str | None = None,
                             origin: str | None = None,
                             exercise_id: str | None = None,
                             plan_id: int | None = None,
                             plan_version: int | None = None,
                             chosen_target: str | None = None,
                             observation_metric: str | None = None,
                             observation_window_days: int | None = None,
                             min_sessions: int | None = None,
                             baseline_source_revisions: str | None = None) -> int:
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
            " stop_rule, review_at, baseline, origin, exercise_id, plan_id,"
            " plan_version, chosen_target, observation_metric,"
            " observation_window_days, min_sessions, baseline_source_revisions,"
            " status, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?)",
            (user_id, change_desc, reason, observe, stop_rule, review,
             baseline, origin, exercise_id,
             str(plan_id) if plan_id is not None else None,
             str(plan_version) if plan_version is not None else None,
             chosen_target, observation_metric,
             str(observation_window_days) if observation_window_days is not None else None,
             str(min_sessions) if min_sessions is not None else None,
             baseline_source_revisions, _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_personal_trial(self, user_id: str, trial_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM personal_trials WHERE user_id=? AND id=?",
            (user_id, int(trial_id))).fetchone()
        return dict(row) if row else None

    def extend_personal_trial(self, user_id: str, trial_id: int,
                              days: int) -> bool:
        """暂不判断，继续观察：仅延长 review_at，不结束尝试（P5-C3）。"""
        if not 1 <= int(days) <= 180:
            raise ValueError("观察延长天数必须是 1-180 的整数")
        row = self.conn.execute(
            "SELECT id, review_at FROM personal_trials"
            " WHERE user_id=? AND id=? AND status='active'",
            (user_id, int(trial_id))).fetchone()
        if not row:
            return False
        base = row["review_at"] or _now()
        try:
            start = datetime.fromisoformat(base)
        except ValueError:
            start = datetime.now()
        extended = (max(start, datetime.now())
                    + timedelta(days=int(days))).isoformat(timespec="seconds")
        cur = self.conn.execute(
            "UPDATE personal_trials SET review_at=? WHERE user_id=? AND id=?",
            (extended, user_id, int(trial_id)))
        self.conn.commit()
        return cur.rowcount > 0

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

    # ---- M5.2 P0-1：用户自定义动作（custom_exercises）----
    def add_custom_exercise(self, user_id: str, ex_id: str, doc: dict) -> int | None:
        """插入自定义动作；同 user 下 id 冲突返回 None。"""
        try:
            cur = self.conn.execute(
                "INSERT INTO custom_exercises(user_id, ex_id, doc, created_at)"
                " VALUES(?,?,?,?)",
                (user_id, ex_id, json.dumps(doc, ensure_ascii=False), _now()))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def get_custom_exercises(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ex_id, doc FROM custom_exercises WHERE user_id=?"
            " ORDER BY id", (user_id,)).fetchall()
        out = []
        for r in rows:
            doc = json.loads(r["doc"])
            doc["scope"] = "user"
            out.append(doc)
        return out

    # ---- M6.4-A：训练模板（可复用；与计划/会话相互独立） ----
    def list_training_templates(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, doc, created_at, updated_at FROM training_templates"
            " WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
        return [{"id": r["id"], "name": r["name"], **json.loads(r["doc"]),
                 "created_at": r["created_at"], "updated_at": r["updated_at"]}
                for r in rows]

    def get_training_template(self, user_id: str, template_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, doc, created_at, updated_at FROM training_templates"
            " WHERE user_id=? AND id=?", (user_id, template_id)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "name": row["name"], **json.loads(row["doc"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def save_training_template(self, user_id: str, name: str, doc: dict,
                               template_id: int | None = None) -> int:
        """template_id 为空 = 新建；否则更新本人模板（不改训练计划、不碰会话）。"""
        now = _now()
        if template_id is None:
            cur = self.conn.execute(
                "INSERT INTO training_templates(user_id,name,doc,created_at,updated_at)"
                " VALUES(?,?,?,?,?)", (user_id, name, json.dumps(doc, ensure_ascii=False), now, now))
            self.conn.commit()
            return cur.lastrowid
        cur = self.conn.execute(
            "UPDATE training_templates SET name=?, doc=?, updated_at=?"
            " WHERE user_id=? AND id=?",
            (name, json.dumps(doc, ensure_ascii=False), now, user_id, template_id))
        if cur.rowcount != 1:
            raise ValueError("模板不存在或不属于当前用户")
        self.conn.commit()
        return template_id

    def delete_training_template(self, user_id: str, template_id: int) -> None:
        cur = self.conn.execute(
            "DELETE FROM training_templates WHERE user_id=? AND id=?",
            (user_id, template_id))
        if cur.rowcount != 1:
            raise ValueError("模板不存在或不属于当前用户")
        self.conn.commit()


    def get_custom_exercise(self, user_id: str, ex_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT doc FROM custom_exercises WHERE user_id=? AND ex_id=?",
            (user_id, ex_id)).fetchone()
        if not row:
            return None
        doc = json.loads(row["doc"])
        doc["scope"] = "user"
        return doc

    # ---- M4：动作视频分析（motion_analyses）----
    def add_motion_analysis(self, user_id: str, exercise_id: str, view: str,
                            video_path: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO motion_analyses(user_id, exercise_id, view, video_path,"
            " status, created_at) VALUES(?,?,?,?, 'processing', ?)",
            (user_id, exercise_id, view, video_path, _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_motion_analysis(self, user_id: str, analysis_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM motion_analyses WHERE user_id=? AND id=?",
            (user_id, analysis_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("result"):
            try:
                d["result"] = json.loads(d["result"])
            except ValueError:
                d["result"] = {}
        return d

    def list_motion_analyses(self, user_id: str, exercise_id: str | None = None,
                             limit: int = 20) -> list[dict]:
        sql = ("SELECT id, exercise_id, view, status, error, result, video_path,"
               " created_at FROM motion_analyses WHERE user_id=?")
        params: list = [user_id]
        if exercise_id:
            sql += " AND exercise_id=?"
            params.append(exercise_id)
        rows = self.conn.execute(sql + " ORDER BY id DESC LIMIT ?",
                                 params + [limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["result"] = json.loads(d["result"] or "{}")
            except ValueError:
                d["result"] = {}
            out.append(d)
        return out

    def finish_motion_analysis(self, analysis_id: int, status: str,
                               result: dict | None = None,
                               error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE motion_analyses SET status=?, result=?, error=? WHERE id=?",
            (status,
             json.dumps(result, ensure_ascii=False) if result is not None else None,
             error[:500] if error else None, analysis_id))
        self.conn.commit()

    # ---- 专家平台（P0：ExpertTask / ExpertInsight / 设置）----
    #
    # 设计要点：
    # - 任务状态落库（不依赖进程内存），服务重启后 pending 可继续执行、
    #   running 凭 heartbeat_at 判定崩溃并恢复；
    # - dedup_key 唯一约束 = 事件级幂等（同一 WorkoutSaved 重放不重复分析）；
    # - 洞察的失效不靠钩子全覆盖：读取时对比 source_revision 与当前数据
    #   （checkin 修订数 / 生效计划版本），漂移即失效（懒失效）。

    def _task_event(self, task_id: str, event: str, detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO expert_task_events(task_id, event, detail, at)"
            " VALUES(?,?,?,?)", (task_id, event, detail[:500], _now()))

    def create_expert_task(self, user_id: str, specialist: str, task_type: str,
                           trigger_source: str, input_refs: dict,
                           dedup_key: str | None = None,
                           max_retries: int = 2) -> dict | None:
        """入队；命中 dedup（同事件重放/并发）返回既有任务，不重复创建。"""
        task_id = "ext-" + uuid.uuid4().hex
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO expert_tasks(id, user_id, specialist, task_type,"
                    " trigger_source, input_refs, dedup_key, status, max_retries,"
                    " created_at) VALUES(?,?,?,?,?,?,?,'pending',?,?)",
                    (task_id, user_id, specialist, task_type, trigger_source,
                     json.dumps(input_refs, ensure_ascii=False), dedup_key,
                     max_retries, _now()))
                self._task_event(task_id, "enqueued",
                                 f"{trigger_source} → {specialist}/{task_type}")
        except sqlite3.IntegrityError:
            row = self.conn.execute(
                "SELECT * FROM expert_tasks WHERE user_id=? AND dedup_key=?",
                (user_id, dedup_key)).fetchone()
            return self._task_row(row) if row else None
        return self.get_expert_task(user_id, task_id)

    @staticmethod
    def _task_row(row) -> dict:
        task = dict(row)
        task["input_refs"] = json.loads(task["input_refs"])
        return task

    def get_expert_task(self, user_id: str, task_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM expert_tasks WHERE user_id=? AND id=?",
            (user_id, task_id)).fetchone()
        return self._task_row(row) if row else None

    def list_expert_tasks(self, user_id: str, specialist: str | None = None,
                          status: str | None = None, limit: int = 20) -> list[dict]:
        sql = "SELECT * FROM expert_tasks WHERE user_id=?"
        params: list = [user_id]
        if specialist:
            sql += " AND specialist=?"
            params.append(specialist)
        if status:
            sql += " AND status=?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY created_at DESC, id DESC LIMIT ?",
                                 params + [limit]).fetchall()
        return [self._task_row(r) for r in rows]

    def update_expert_task(self, user_id: str, task_id: str, *,
                           status: str | None = None,
                           insight_id: str | None = None,
                           error_code: str | None = None,
                           error: str | None = None,
                           bump_retry: bool = False,
                           heartbeat: bool = False,
                           event: str | None = None,
                           event_detail: str = "") -> None:
        """任务状态迁移 + 执行日志。仅更新给出的字段。"""
        sets, params = [], []
        if status is not None:
            sets.append("status=?")
            params.append(status)
            if status == "running":
                sets += ["started_at=?", "heartbeat_at=?"]
                params += [_now(), _now()]
            if status in ("ready", "failed", "cancelled"):
                sets.append("completed_at=?")
                params.append(_now())
        if insight_id is not None:
            sets.append("insight_id=?")
            params.append(insight_id)
        if error_code is not None:
            sets.append("error_code=?")
            params.append(error_code)
        if error is not None:
            sets.append("error=?")
            params.append(error[:500])
        if bump_retry:
            sets.append("retry_count=retry_count+1")
        if heartbeat:
            sets.append("heartbeat_at=?")
            params.append(_now())
        if event:
            self._task_event(task_id, event, event_detail)
        if not sets:
            return
        params += [user_id, task_id]
        with self.conn:
            self.conn.execute(
                f"UPDATE expert_tasks SET {', '.join(sets)} WHERE user_id=? AND id=?",
                params)

    def stale_running_expert_tasks(self, max_running_minutes: int = 10) -> list[dict]:
        """running 且心跳过期的任务（进程崩溃残留），供启动恢复。"""
        cutoff = (datetime.now() - timedelta(minutes=max_running_minutes)
                  ).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT * FROM expert_tasks WHERE status='running'"
            " AND (heartbeat_at IS NULL OR heartbeat_at < ?)", (cutoff,)).fetchall()
        return [self._task_row(r) for r in rows]

    def expert_task_events(self, task_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT event, detail, at FROM expert_task_events WHERE task_id=?"
            " ORDER BY id DESC LIMIT ?", (task_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---- 洞察 ----

    def insert_expert_insight(self, insight: dict) -> str:
        cur = self.conn.execute(
            "INSERT INTO expert_insights(id, user_id, task_id, specialist,"
            " insight_type, title, summary, findings, evidence_refs,"
            " facts_snapshot, knowledge_refs, options, limitations, status,"
            " confidence, confidence_basis, generated_at, expires_at,"
            " source_revision, input_refs) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'ready',?,?,?,?,?,?)",
            (insight["id"], insight["user_id"], insight.get("task_id"),
             insight["specialist"], insight["insight_type"],
             insight["title"][:200], insight["summary"][:1000],
             json.dumps(insight.get("findings") or [], ensure_ascii=False),
             json.dumps(insight.get("evidence_refs") or [], ensure_ascii=False),
             json.dumps(insight.get("facts_snapshot") or {}, ensure_ascii=False),
             json.dumps(insight.get("knowledge_refs") or [], ensure_ascii=False),
             json.dumps(insight.get("options") or [], ensure_ascii=False),
             json.dumps(insight.get("limitations") or [], ensure_ascii=False),
             insight["confidence"], insight["confidence_basis"][:500],
             insight["generated_at"], insight.get("expires_at"),
             json.dumps(insight.get("source_revision") or {}, ensure_ascii=False),
             json.dumps(insight.get("input_refs") or {}, ensure_ascii=False)))
        self.conn.commit()
        return cur.lastrowid

    @staticmethod
    def _insight_row(row) -> dict:
        d = dict(row)
        for key in ("findings", "evidence_refs", "facts_snapshot",
                    "knowledge_refs", "options", "limitations", "source_revision",
                    "input_refs"):
            default = "{}" if key in ("facts_snapshot", "source_revision",
                                      "input_refs") else "[]"
            try:
                d[key] = json.loads(d.get(key) or default)
            except (ValueError, TypeError):
                d[key] = json.loads(default)
        return d

    def get_expert_insight(self, user_id: str, insight_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM expert_insights WHERE user_id=? AND id=?",
            (user_id, insight_id)).fetchone()
        return self._insight_row(row) if row else None

    def list_expert_insights(self, user_id: str, specialist: str | None = None,
                             status: str | None = None, limit: int = 20) -> list[dict]:
        sql = ("SELECT id, user_id, task_id, specialist, insight_type, title,"
               " summary, status, confidence, confidence_basis, generated_at,"
               " expires_at, source_revision, input_refs, read_at"
               " FROM expert_insights"
               " WHERE user_id=?")
        params: list = [user_id]
        if specialist:
            sql += " AND specialist=?"
            params.append(specialist)
        if status:
            sql += " AND status=?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY generated_at DESC, rowid DESC LIMIT ?",
                                 params + [limit]).fetchall()
        return [self._insight_row(r) for r in rows]

    def update_expert_insight_status(self, user_id: str, insight_id: str,
                                     status: str) -> bool:
        """ready↔viewed↔dismissed/expired/invalidated 的状态迁移（幂等）。"""
        allowed = ("ready", "viewed", "dismissed", "expired", "invalidated")
        if status not in allowed:
            raise ValueError(f"未知洞察状态 {status!r}")
        extra = ", read_at=?" if status == "viewed" else ""
        params: list = [_now()] if status == "viewed" else []
        cur = self.conn.execute(
            f"UPDATE expert_insights SET status=?{extra} WHERE user_id=? AND id=?"
            " AND status IN ('ready','viewed')",
            [status, *params, user_id, insight_id])
        self.conn.commit()
        return cur.rowcount > 0

    def expert_settings(self, user_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM expert_settings WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return {"proactive_enabled": bool(row["proactive_enabled"]),
                    "min_interval_minutes": row["min_interval_minutes"]}
        return {"proactive_enabled": True, "min_interval_minutes": 0}

    def save_expert_settings(self, user_id: str, proactive_enabled: bool,
                             min_interval_minutes: int) -> dict:
        if not isinstance(min_interval_minutes, int) or isinstance(min_interval_minutes, bool) \
                or not 0 <= min_interval_minutes <= 1440:
            raise ValueError("min_interval_minutes 必须是 0-1440 的整数")
        self.conn.execute(
            "INSERT INTO expert_settings(user_id, proactive_enabled,"
            " min_interval_minutes, updated_at) VALUES(?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET proactive_enabled=?,"
            " min_interval_minutes=?, updated_at=?",
            (user_id, int(proactive_enabled), min_interval_minutes, _now(),
             int(proactive_enabled), min_interval_minutes, _now()))
        self.conn.commit()
        return self.expert_settings(user_id)

    # ---- P1 营养系统：食物库 / 餐次记录 / 目标 / 食谱 ----
    #
    # 设计要点：
    # - 营养值挂在 reference_amount（默认每 100g/ml）上，快照随餐保存——
    #   食物库后续更新不改变历史记录；
    # - 未知营养素 = NULL，读取与计算层绝不用 0 冒充；
    # - 内置食物 user_id IS NULL（公共），自定义食物按用户隔离。

    def upsert_food(self, food: dict) -> None:
        """插入或按 id 更新食物（内置目录装载与自定义共用）。"""
        self.conn.execute(
            "INSERT INTO foods(id, user_id, name, aliases, brand, category,"
            " serving_units, energy_kcal, protein_g, carbohydrate_g, fat_g,"
            " fiber_g, sodium_mg, reference_amount, reference_unit,"
            " source_name, source_url, source_version, license,"
            " verified_status, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " aliases=excluded.aliases, brand=excluded.brand,"
            " category=excluded.category, serving_units=excluded.serving_units,"
            " energy_kcal=excluded.energy_kcal, protein_g=excluded.protein_g,"
            " carbohydrate_g=excluded.carbohydrate_g, fat_g=excluded.fat_g,"
            " fiber_g=excluded.fiber_g, sodium_mg=excluded.sodium_mg,"
            " reference_amount=excluded.reference_amount,"
            " reference_unit=excluded.reference_unit,"
            " source_name=excluded.source_name, source_url=excluded.source_url,"
            " source_version=excluded.source_version,"
            " license=excluded.license,"
            " verified_status=excluded.verified_status",
            (food["id"], food.get("user_id"), food["name"],
             json.dumps(food.get("aliases") or [], ensure_ascii=False),
             food.get("brand"), food["category"],
             json.dumps(food.get("serving_units") or [{"unit": "克", "grams": 1}],
                        ensure_ascii=False),
             food.get("energy_kcal"), food.get("protein_g"),
             food.get("carbohydrate_g"), food.get("fat_g"),
             food.get("fiber_g"), food.get("sodium_mg"),
             food.get("reference_amount", 100), food.get("reference_unit", "g"),
             food.get("source_name"), food.get("source_url"),
             food.get("source_version"), food.get("license"),
             food.get("verified_status", "user_created"),
             food.get("created_at") or _now()))
        self.conn.commit()

    def add_custom_food(self, user_id: str, food: dict) -> str | None:
        """自定义食物：同名拒绝（含与内置同名/别名冲突，避免搜索歧义）。"""
        import uuid as _uuid
        name = str(food.get("name") or "").strip()
        row = self.conn.execute(
            "SELECT 1 FROM foods WHERE user_id IS NULL AND name=?"
            " UNION SELECT 1 FROM foods WHERE user_id=? AND name=?",
            (name, user_id, name)).fetchone()
        if row:
            return None
        food = dict(food)
        food["id"] = "food-" + _uuid.uuid4().hex
        food["user_id"] = user_id
        food["verified_status"] = "user_created"
        try:
            self.upsert_food(food)
        except sqlite3.IntegrityError:
            return None
        return food["id"]

    def update_custom_food(self, user_id: str, food_id: str, patch: dict) -> bool:
        """仅允许改本人的自定义食物；改后由调用方触发漂移失效提示。"""
        row = self.conn.execute(
            "SELECT id FROM foods WHERE id=? AND user_id=?", (food_id, user_id)
        ).fetchone()
        if not row:
            return False
        cols = ("name", "aliases", "brand", "category", "serving_units",
                "energy_kcal", "protein_g", "carbohydrate_g", "fat_g",
                "fiber_g", "sodium_mg", "reference_amount", "reference_unit",
                "source_name", "source_url", "source_version", "license")
        sets, params = [], []
        for col in cols:
            if col in patch:
                val = patch[col]
                if col in ("aliases", "serving_units"):
                    val = json.dumps(val, ensure_ascii=False)
                sets.append(f"{col}=?")
                params.append(val)
        if not sets:
            return True
        params.append(food_id)
        self.conn.execute(
            f"UPDATE foods SET {', '.join(sets)} WHERE id=?", params)
        self.conn.commit()
        return True

    @staticmethod
    def _food_row(row) -> dict:
        d = dict(row)
        for key in ("aliases", "serving_units"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except (ValueError, TypeError):
                d[key] = []
        return d

    def get_food(self, user_id: str | None, food_id: str) -> dict | None:
        """取食物：内置（user_id IS NULL）或本人的自定义。"""
        row = self.conn.execute(
            "SELECT * FROM foods WHERE id=? AND (user_id IS NULL OR user_id=?)",
            (food_id, user_id)).fetchone()
        return self._food_row(row) if row else None

    def search_foods(self, user_id: str | None, q: str = "",
                     category: str = "", scope: str = "",
                     limit: int = 40) -> list[dict]:
        """中文搜索（名称/别名/品牌子串）+ 分类/范围过滤。"""
        rows = self.conn.execute(
            "SELECT * FROM foods WHERE user_id IS NULL OR user_id=?"
            " ORDER BY (user_id IS NULL) DESC, id", (user_id or "",)).fetchall()
        items = [self._food_row(r) for r in rows]
        if category:
            items = [f for f in items if f["category"] == category]
        if scope == "builtin":
            items = [f for f in items if f["user_id"] is None]
        elif scope == "mine" and user_id:
            items = [f for f in items if f["user_id"] == user_id]
        if q:
            ql = q.strip().lower()
            def hit(f):
                return ql in f["name"].lower() or ql in (f.get("brand") or "").lower() \
                    or any(ql in str(a).lower() for a in (f.get("aliases") or []))
            items = [f for f in items if hit(f)]
        return items[:limit]

    def builtin_food_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM foods WHERE user_id IS NULL").fetchone()[0]

    # ---- 餐次记录 ----

    def _meal_row(self, row) -> dict:
        d = dict(row)
        d["items"] = json.loads(d["items"])
        return d

    def save_meal(self, user_id: str, local_date: str, meal_type: str,
                  items: list, notes: str = "") -> int:
        if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
            raise ValueError("meal_type 必须是 breakfast/lunch/dinner/snack")
        cur = self.conn.execute(
            "INSERT INTO meal_entries(user_id, local_date, meal_type, items,"
            " notes, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, local_date, meal_type,
             json.dumps(items, ensure_ascii=False), notes[:500], _now(), _now()))
        self.conn.commit()
        return cur.lastrowid

    def update_meal(self, user_id: str, meal_id: int, items: list,
                    notes: str | None = None, meal_type: str | None = None) -> bool:
        sets = ["items=?", "updated_at=?"]
        params: list = [json.dumps(items, ensure_ascii=False), _now()]
        if notes is not None:
            sets.append("notes=?")
            params.append(notes[:500])
        if meal_type is not None:
            if meal_type not in ("breakfast", "lunch", "dinner", "snack"):
                raise ValueError("非法 meal_type")
            sets.append("meal_type=?")
            params.append(meal_type)
        params += [user_id, meal_id]
        cur = self.conn.execute(
            f"UPDATE meal_entries SET {', '.join(sets)} WHERE user_id=? AND id=?",
            params)
        self.conn.commit()
        return cur.rowcount == 1

    def delete_meal(self, user_id: str, meal_id: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM meal_entries WHERE user_id=? AND id=?", (user_id, meal_id))
        self.conn.commit()
        return cur.rowcount == 1

    def get_meal(self, user_id: str, meal_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM meal_entries WHERE user_id=? AND id=?",
            (user_id, meal_id)).fetchone()
        return self._meal_row(row) if row else None

    def meals_on(self, user_id: str, local_date: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM meal_entries WHERE user_id=? AND local_date=?"
            " ORDER BY id", (user_id, local_date)).fetchall()
        return [self._meal_row(r) for r in rows]

    def copy_day_meals(self, user_id: str, from_date: str, to_date: str) -> int:
        """复制某天全部餐次到另一天（沿用快照，不重算）。"""
        count = 0
        for meal in self.meals_on(user_id, from_date):
            self.save_meal(user_id, to_date, meal["meal_type"], meal["items"],
                           meal.get("notes") or "")
            count += 1
        return count

    def meal_history(self, user_id: str, days: int = 90) -> list[dict]:
        """近 N 天餐次（趋势与最近食物用）。"""
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM meal_entries WHERE user_id=? AND local_date>=?"
            " ORDER BY local_date DESC, id DESC", (user_id, cutoff)).fetchall()
        return [self._meal_row(r) for r in rows]

    def set_day_complete(self, user_id: str, local_date: str, complete: bool) -> None:
        self.conn.execute(
            "INSERT INTO nutrition_days(user_id, local_date, complete, updated_at)"
            " VALUES(?,?,?,?) ON CONFLICT(user_id, local_date) DO UPDATE SET"
            " complete=excluded.complete, updated_at=excluded.updated_at",
            (user_id, local_date, int(complete), _now()))
        self.conn.commit()

    def day_complete(self, user_id: str, local_date: str) -> bool:
        row = self.conn.execute(
            "SELECT complete FROM nutrition_days WHERE user_id=? AND local_date=?",
            (user_id, local_date)).fetchone()
        return bool(row and row["complete"])

    def complete_days(self, user_id: str, days: int = 90) -> set[str]:
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        rows = self.conn.execute(
            "SELECT local_date FROM nutrition_days WHERE user_id=? AND complete=1"
            " AND local_date>=?", (user_id, cutoff)).fetchall()
        return {r["local_date"] for r in rows}

    # ---- 目标与食谱 ----

    def get_nutrition_targets(self, user_id: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM nutrition_targets WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return {"energy_kcal": None, "protein_g": None,
                    "carbohydrate_g": None, "fat_g": None,
                    "preferences": {}, "allergies": [],
                    "budget_note": None, "precision_willing": None}
        d = dict(row)
        d["preferences"] = json.loads(d.get("preferences") or "{}")
        d["allergies"] = json.loads(d.get("allergies") or "[]")
        return d

    def save_nutrition_targets(self, user_id: str, t: dict) -> dict:
        for key in ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g"):
            v = t.get(key)
            if v is not None and (not isinstance(v, (int, float))
                                  or isinstance(v, bool) or v < 0 or v > 10000):
                raise ValueError(f"{key} 必须是 0-10000 的数值或留空")
        precision = t.get("precision_willing")
        if precision is not None and precision not in (
                "willing_precise", "rough", "minimal"):
            raise ValueError("precision_willing 必须是 willing_precise/rough/minimal")
        self.conn.execute(
            "INSERT INTO nutrition_targets(user_id, energy_kcal, protein_g,"
            " carbohydrate_g, fat_g, preferences, allergies, budget_note,"
            " precision_willing, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET energy_kcal=excluded.energy_kcal,"
            " protein_g=excluded.protein_g,"
            " carbohydrate_g=excluded.carbohydrate_g, fat_g=excluded.fat_g,"
            " preferences=excluded.preferences, allergies=excluded.allergies,"
            " budget_note=excluded.budget_note,"
            " precision_willing=excluded.precision_willing,"
            " updated_at=excluded.updated_at",
            (user_id, t.get("energy_kcal"), t.get("protein_g"),
             t.get("carbohydrate_g"), t.get("fat_g"),
             json.dumps(t.get("preferences") or {}, ensure_ascii=False),
             json.dumps(t.get("allergies") or [], ensure_ascii=False),
             t.get("budget_note"), precision, _now()))
        self.conn.commit()
        return self.get_nutrition_targets(user_id)

    def save_recipe(self, user_id: str, name: str, items: list,
                    recipe_id: int | None = None) -> int:
        now = _now()
        if recipe_id is None:
            cur = self.conn.execute(
                "INSERT INTO nutrition_recipes(user_id, name, items, created_at,"
                " updated_at) VALUES(?,?,?,?,?)",
                (user_id, name[:40], json.dumps(items, ensure_ascii=False), now, now))
            self.conn.commit()
            return cur.lastrowid
        cur = self.conn.execute(
            "UPDATE nutrition_recipes SET name=?, items=?, updated_at=?"
            " WHERE user_id=? AND id=?",
            (name[:40], json.dumps(items, ensure_ascii=False), now, user_id, recipe_id))
        if cur.rowcount != 1:
            raise ValueError("食谱不存在或不属于当前用户")
        self.conn.commit()
        return recipe_id

    def list_recipes(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM nutrition_recipes WHERE user_id=? ORDER BY id DESC",
            (user_id,)).fetchall()
        return [{"id": r["id"], "name": r["name"],
                 "items": json.loads(r["items"]),
                 "updated_at": r["updated_at"]} for r in rows]

    def delete_recipe(self, user_id: str, recipe_id: int) -> None:
        cur = self.conn.execute(
            "DELETE FROM nutrition_recipes WHERE user_id=? AND id=?",
            (user_id, recipe_id))
        if cur.rowcount != 1:
            raise ValueError("食谱不存在或不属于当前用户")
        self.conn.commit()

    # ---- P2 身体数据 / 恢复记录 ----
    #
    # 纪律：指标全部可选且 NULL=未测量；修订保留原始值（纠错需 reason+evidence，
    # 与训练打卡同一纪律）；幂等提交走 record_submissions；来源（设备/方法）
    # 随记录保存，不同来源估算值不默认可比。

    def get_record_submission(self, user_id: str, submission_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT kind, record_id, created_at FROM record_submissions"
            " WHERE user_id=? AND submission_id=?", (user_id, submission_id)).fetchone()
        return dict(row) if row else None

    def record_submission(self, user_id: str, submission_id: str,
                          kind: str, record_id: int) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO record_submissions(user_id, submission_id, kind,"
                " record_id, created_at) VALUES(?,?,?,?,?)",
                (user_id, submission_id, kind, record_id, _now()))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    # ---- body_measurements ----

    @staticmethod
    def _measurement_row(row) -> dict:
        d = dict(row)
        rev = d.pop("_revision", None)
        if rev is not None:
            d["revision"] = rev
        return d

    def create_body_measurement(self, user_id: str, m: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO body_measurements(user_id, measured_at, local_date,"
            " timezone, weight_kg, waist_cm, hip_cm, chest_cm, body_fat_percent,"
            " muscle_mass_kg, measurement_method, device_source, notes,"
            " migrated_from, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, m["measured_at"], m["local_date"], m.get("timezone"),
             m.get("weight_kg"), m.get("waist_cm"), m.get("hip_cm"),
             m.get("chest_cm"), m.get("body_fat_percent"), m.get("muscle_mass_kg"),
             m.get("measurement_method"), m.get("device_source"),
             m.get("notes"), m.get("migrated_from"), _now(), _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_body_measurement(self, user_id: str, mid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT m.*, (SELECT COUNT(*) FROM body_measurement_revisions r"
            " WHERE r.measurement_id=m.id) AS _revision"
            " FROM body_measurements m WHERE m.user_id=? AND m.id=?",
            (user_id, mid)).fetchone()
        return self._measurement_row(row) if row else None

    def list_body_measurements(self, user_id: str, start: str | None = None,
                               end: str | None = None, limit: int = 200) -> list[dict]:
        sql = ("SELECT m.*, (SELECT COUNT(*) FROM body_measurement_revisions r"
               " WHERE r.measurement_id=m.id) AS _revision"
               " FROM body_measurements m WHERE m.user_id=?")
        params: list = [user_id]
        if start:
            sql += " AND m.local_date>=?"
            params.append(start)
        if end:
            sql += " AND m.local_date<=?"
            params.append(end)
        rows = self.conn.execute(sql + " ORDER BY m.measured_at DESC, m.id DESC LIMIT ?",
                                 params + [limit]).fetchall()
        return [self._measurement_row(r) for r in rows]

    def body_measurement_revision_count(self, user_id: str, mid: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM body_measurement_revisions"
            " WHERE measurement_id=?", (mid,)).fetchone()[0]

    def revise_body_measurement(self, user_id: str, mid: int, expected_revision: int,
                                patch: dict, reason: str, evidence: str) -> dict:
        """身体记录纠错：保留原值快照，修订号 +1（与训练打卡同一纪律）。"""
        if not reason.strip() or not evidence.strip():
            raise ValueError("纠错必须说明原因并附用户原话")
        current = self.get_body_measurement(user_id, mid)
        if not current:
            raise ValueError("测量记录不存在")
        if current["revision"] != expected_revision:
            raise ValueError("记录已被修订，请先重新读取最新版本")
        fields = ("measured_at", "local_date", "timezone", "weight_kg", "waist_cm",
                  "hip_cm", "chest_cm", "body_fat_percent", "muscle_mass_kg",
                  "measurement_method", "device_source", "notes")
        new = {k: current.get(k) for k in fields}
        for k, v in patch.items():
            if k in fields:
                new[k] = v
        with self.conn:
            self.conn.execute(
                "INSERT INTO body_measurement_revisions(user_id, measurement_id,"
                " revision, old_data, new_data, reason, evidence, created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (user_id, mid, expected_revision + 1,
                 json.dumps(current, ensure_ascii=False, default=str),
                 json.dumps(new, ensure_ascii=False), reason, evidence, _now()))
            self.conn.execute(
                "UPDATE body_measurements SET measured_at=?, local_date=?,"
                " timezone=?, weight_kg=?, waist_cm=?, hip_cm=?, chest_cm=?,"
                " body_fat_percent=?, muscle_mass_kg=?, measurement_method=?,"
                " device_source=?, notes=?, updated_at=? WHERE user_id=? AND id=?",
                (new["measured_at"], new["local_date"], new["timezone"],
                 new["weight_kg"], new["waist_cm"], new["hip_cm"], new["chest_cm"],
                 new["body_fat_percent"], new["muscle_mass_kg"],
                 new["measurement_method"], new["device_source"], new["notes"],
                 _now(), user_id, mid))
        return self.get_body_measurement(user_id, mid)

    def delete_body_measurement(self, user_id: str, mid: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM body_measurements WHERE user_id=? AND id=?", (user_id, mid))
        self.conn.commit()
        return cur.rowcount == 1

    def body_measurement_revisions(self, user_id: str, mid: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT revision, reason, evidence, created_at FROM"
            " body_measurement_revisions WHERE measurement_id=? ORDER BY revision DESC",
            (mid,)).fetchall()
        return [dict(r) for r in rows]

    # ---- recovery_checkins ----

    @staticmethod
    def _recovery_row(row) -> dict:
        d = dict(row)
        d["soreness_regions"] = json.loads(d.get("soreness_regions") or "[]")
        rev = d.pop("_revision", None)
        if rev is not None:
            d["revision"] = rev
        return d

    def upsert_recovery_checkin(self, user_id: str, r: dict) -> tuple[int, bool]:
        """当天一条：已存在则覆盖并记修订，返回 (id, created?)。"""
        existing = self.conn.execute(
            "SELECT id, (SELECT COUNT(*) FROM recovery_revisions rr"
            " WHERE rr.recovery_id=recovery_checkins.id) AS _revision"
            " FROM recovery_checkins WHERE user_id=? AND local_date=?",
            (user_id, r["local_date"])).fetchone()
        if existing:
            rid, rev = existing["id"], existing["_revision"]
            old = self.get_recovery_checkin(user_id, rid)
            with self.conn:
                self.conn.execute(
                    "INSERT INTO recovery_revisions(user_id, recovery_id, revision,"
                    " old_data, new_data, reason, evidence, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, rid, rev + 1,
                     json.dumps(old, ensure_ascii=False, default=str),
                     json.dumps(r, ensure_ascii=False),
                     r.get("reason") or "更新当日恢复记录", r.get("evidence") or "", _now()))
                self.conn.execute(
                    "UPDATE recovery_checkins SET recorded_at=?, timezone=?,"
                    " sleep_hours=?, sleep_quality=?, fatigue=?, muscle_soreness=?,"
                    " training_readiness=?, soreness_regions=?, notes=?, updated_at=?"
                    " WHERE user_id=? AND id=?",
                    (r["recorded_at"], r.get("timezone"), r.get("sleep_hours"),
                     r.get("sleep_quality"), r.get("fatigue"), r.get("muscle_soreness"),
                     r.get("training_readiness"),
                     json.dumps(r.get("soreness_regions") or [], ensure_ascii=False),
                     r.get("notes"), _now(), user_id, rid))
            return rid, False
        cur = self.conn.execute(
            "INSERT INTO recovery_checkins(user_id, local_date, recorded_at,"
            " timezone, sleep_hours, sleep_quality, fatigue, muscle_soreness,"
            " training_readiness, soreness_regions, notes, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, r["local_date"], r["recorded_at"], r.get("timezone"),
             r.get("sleep_hours"), r.get("sleep_quality"), r.get("fatigue"),
             r.get("muscle_soreness"), r.get("training_readiness"),
             json.dumps(r.get("soreness_regions") or [], ensure_ascii=False),
             r.get("notes"), _now(), _now()))
        self.conn.commit()
        return cur.lastrowid, True

    def get_recovery_checkin(self, user_id: str, rid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT rc.*, (SELECT COUNT(*) FROM recovery_revisions rr"
            " WHERE rr.recovery_id=rc.id) AS _revision"
            " FROM recovery_checkins rc WHERE rc.user_id=? AND rc.id=?",
            (user_id, rid)).fetchone()
        return self._recovery_row(row) if row else None

    def get_recovery_by_date(self, user_id: str, local_date: str) -> dict | None:
        row = self.conn.execute(
            "SELECT rc.*, (SELECT COUNT(*) FROM recovery_revisions rr"
            " WHERE rr.recovery_id=rc.id) AS _revision"
            " FROM recovery_checkins rc WHERE rc.user_id=? AND rc.local_date=?",
            (user_id, local_date)).fetchone()
        return self._recovery_row(row) if row else None

    def list_recovery_checkins(self, user_id: str, days: int = 90) -> list[dict]:
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        rows = self.conn.execute(
            "SELECT rc.*, (SELECT COUNT(*) FROM recovery_revisions rr"
            " WHERE rr.recovery_id=rc.id) AS _revision"
            " FROM recovery_checkins rc WHERE rc.user_id=? AND rc.local_date>=?"
            " ORDER BY rc.local_date DESC", (user_id, cutoff)).fetchall()
        return [self._recovery_row(r) for r in rows]

    def recovery_revision_count(self, user_id: str, rid: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM recovery_revisions WHERE recovery_id=?",
            (rid,)).fetchone()[0]

    def delete_recovery_checkin(self, user_id: str, rid: int) -> bool:
        cur = self.conn.execute(
            "DELETE FROM recovery_checkins WHERE user_id=? AND id=?", (user_id, rid))
        self.conn.commit()
        return cur.rowcount == 1

    # ---- P3 康复辅助：症状事件 / 训练限制 / 专业安排 ----

    def create_symptom_episode(self, user_id: str, ep: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO symptom_episodes(user_id, body_region, side, onset_at,"
            " onset_context, description, related_checkin_id, professional_evaluated,"
            " status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, ep["body_region"], ep.get("side"), ep["onset_at"],
             ep.get("onset_context"), ep["description"],
             ep.get("related_checkin_id"), int(ep.get("professional_evaluated") or 0),
             "active", _now(), _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_symptom_episode(self, user_id: str, eid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM symptom_episodes WHERE user_id=? AND id=?",
            (user_id, eid)).fetchone()
        return dict(row) if row else None

    def list_symptom_episodes(self, user_id: str,
                              status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM symptom_episodes WHERE user_id=?"
        params: list = [user_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        return [dict(r) for r in self.conn.execute(
            sql + " ORDER BY updated_at DESC", params).fetchall()]

    def update_symptom_episode(self, user_id: str, eid: int, patch: dict) -> bool:
        # 微秒精度：状态变更与创建发生在同一秒时版本指纹也必须变化
        sets, params = ["updated_at=?"], [
            datetime.now().isoformat(timespec="microseconds")]
        for col in ("status", "professional_evaluated", "side", "onset_context"):
            if col in patch:
                sets.append(f"{col}=?")
                params.append(patch[col])
        params += [user_id, eid]
        cur = self.conn.execute(
            f"UPDATE symptom_episodes SET {', '.join(sets)} WHERE user_id=? AND id=?",
            params)
        self.conn.commit()
        return cur.rowcount == 1

    def add_symptom_observation(self, user_id: str, ep_id: int, obs: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO symptom_observations(episode_id, user_id, recorded_at,"
            " severity, symptom_description, functional_limitations, user_notes,"
            " triage_result, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ep_id, user_id, obs.get("recorded_at") or _now(), obs.get("severity"),
             obs.get("symptom_description"),
             json.dumps(obs.get("functional_limitations") or [], ensure_ascii=False),
             obs.get("user_notes"),
             json.dumps(obs.get("triage_result") or {}, ensure_ascii=False),
             _now(), _now()))
        self.conn.execute(
            "UPDATE symptom_episodes SET updated_at=? WHERE user_id=? AND id=?",
            (_now(), user_id, ep_id))
        self.conn.commit()
        return cur.lastrowid

    def get_symptom_observation(self, user_id: str, obs_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM symptom_observations WHERE user_id=? AND id=?",
            (user_id, obs_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("functional_limitations", "triage_result"):
            try:
                d[key] = json.loads(d.get(key) or ("{}" if key == "triage_result" else "[]"))
            except (ValueError, TypeError):
                d[key] = {} if key == "triage_result" else []
        return d

    def list_symptom_observations(self, user_id: str, ep_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM symptom_observations WHERE user_id=? AND episode_id=?"
            " ORDER BY id", (user_id, ep_id)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for key in ("functional_limitations", "triage_result"):
                try:
                    d[key] = json.loads(d.get(key) or
                                        ("{}" if key == "triage_result" else "[]"))
                except (ValueError, TypeError):
                    d[key] = {} if key == "triage_result" else []
            out.append(d)
        return out

    def symptoms_version(self, user_id: str) -> str:
        """症状数据版本（漂移锚：任何事件/观察变化都会变化）。"""
        row = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM symptom_episodes WHERE user_id=?) AS eps,"
            " (SELECT COUNT(*) FROM symptom_observations WHERE user_id=?) AS obs,"
            " (SELECT COALESCE(MAX(updated_at),'') FROM symptom_episodes"
            "  WHERE user_id=?) AS last",
            (user_id, user_id, user_id)).fetchone()
        return f"{row['eps']}:{row['obs']}:{row['last']}"

    # ---- 训练限制 ----

    def create_restriction(self, user_id: str, r: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO training_restrictions(user_id, source_type,"
            " source_evidence, affected_activities, restriction_description,"
            " related_episode_id, effective_at, review_at, status, created_at,"
            " updated_at) VALUES(?,?,?,?,?,?,?,?, 'active', ?, ?)",
            (user_id, r["source_type"], r["source_evidence"],
             json.dumps(r.get("affected_activities") or {}, ensure_ascii=False),
             r["restriction_description"], r.get("related_episode_id"),
             r["effective_at"], r.get("review_at"), _now(), _now()))
        self.conn.commit()
        return cur.lastrowid

    @staticmethod
    def _restriction_row(row) -> dict:
        d = dict(row)
        d["affected_activities"] = json.loads(d.get("affected_activities") or "{}")
        rev = d.pop("_revision", None)
        if rev is not None:
            d["revision"] = rev
        return d

    def get_restriction(self, user_id: str, rid: int) -> dict | None:
        row = self.conn.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM training_restriction_revisions x"
            " WHERE x.restriction_id=r.id) AS _revision"
            " FROM training_restrictions r WHERE r.user_id=? AND r.id=?",
            (user_id, rid)).fetchone()
        return self._restriction_row(row) if row else None

    def list_restrictions(self, user_id: str,
                          status: str | None = "active") -> list[dict]:
        sql = ("SELECT r.*, (SELECT COUNT(*) FROM training_restriction_revisions x"
               " WHERE x.restriction_id=r.id) AS _revision"
               " FROM training_restrictions r WHERE r.user_id=?")
        params: list = [user_id]
        if status:
            sql += " AND r.status=?"
            params.append(status)
        return [self._restriction_row(r) for r in self.conn.execute(
            sql + " ORDER BY effective_at DESC", params).fetchall()]

    def revise_restriction(self, user_id: str, rid: int, expected_revision: int,
                           patch: dict, reason: str, evidence: str) -> dict:
        """限制修订（状态/描述/复核时间）；解除走这里并必须附依据。"""
        current = self.get_restriction(user_id, rid)
        if not current:
            raise ValueError("限制不存在")
        if current["revision"] != expected_revision:
            raise ValueError("限制已被更新，请先重新读取")
        fields = ("status", "restriction_description", "review_at", "lift_evidence")
        new = {k: current.get(k) for k in fields}
        for k, v in patch.items():
            if k in fields:
                new[k] = v
        with self.conn:
            self.conn.execute(
                "INSERT INTO training_restriction_revisions(user_id,"
                " restriction_id, revision, old_data, new_data, reason, evidence,"
                " created_at) VALUES(?,?,?,?,?,?,?,?)",
                (user_id, rid, expected_revision + 1,
                 json.dumps(current, ensure_ascii=False, default=str),
                 json.dumps(new, ensure_ascii=False), reason, evidence, _now()))
            self.conn.execute(
                "UPDATE training_restrictions SET status=?,"
                " restriction_description=?, review_at=?, lift_evidence=?,"
                " updated_at=? WHERE user_id=? AND id=?",
                (new["status"], new["restriction_description"], new["review_at"],
                 new["lift_evidence"], _now(), user_id, rid))
        return self.get_restriction(user_id, rid)

    def restrictions_version(self, user_id: str) -> str:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(MAX(updated_at),'') AS last,"
            " COALESCE(SUM((SELECT COUNT(*) FROM training_restriction_revisions x"
            " WHERE x.restriction_id=training_restrictions.id)),0) AS revs"
            " FROM training_restrictions WHERE user_id=?", (user_id,)).fetchone()
        return f"{row['n']}:{row['last']}:{row['revs']}"

    # ---- 专业安排（CarePlan） ----

    def create_care_plan(self, user_id: str, p: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO care_plans(user_id, title, professional_source,"
            " applicable_conditions, related_episode_id, review_at, status,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?, 'active', ?, ?)",
            (user_id, p["title"], p["professional_source"],
             p.get("applicable_conditions"), p.get("related_episode_id"),
             p.get("review_at"), _now(), _now()))
        self.conn.commit()
        return cur.lastrowid

    def list_care_plans(self, user_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM care_plans WHERE user_id=? ORDER BY id DESC",
            (user_id,)).fetchall()]

    def get_care_plan(self, user_id: str, plan_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM care_plans WHERE user_id=? AND id=?",
            (user_id, plan_id)).fetchone()
        return dict(row) if row else None

    def update_care_plan_status(self, user_id: str, plan_id: int, status: str) -> bool:
        if status not in ("active", "completed", "paused"):
            raise ValueError("status 必须是 active/completed/paused")
        cur = self.conn.execute(
            "UPDATE care_plans SET status=?, updated_at=? WHERE user_id=? AND id=?",
            (status, _now(), user_id, plan_id))
        self.conn.commit()
        return cur.rowcount == 1

    def add_care_activity(self, user_id: str, plan_id: int, a: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO care_activities(plan_id, user_id, name, frequency,"
            " notes, created_at) VALUES(?,?,?,?,?,?)",
            (plan_id, user_id, a["name"], a.get("frequency"), a.get("notes"),
             _now()))
        self.conn.commit()
        return cur.lastrowid

    def list_care_activities(self, user_id: str, plan_id: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM care_activities WHERE user_id=? AND plan_id=? ORDER BY id",
            (user_id, plan_id)).fetchall()]

    def log_care_activity(self, user_id: str, activity_id: int, local_date: str,
                          completed: bool, feedback: str | None) -> int | None:
        try:
            cur = self.conn.execute(
                "INSERT INTO care_activity_logs(activity_id, user_id, local_date,"
                " completed, feedback, created_at) VALUES(?,?,?,?,?,?)",
                (activity_id, user_id, local_date, int(completed), feedback, _now()))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def care_activity_logs(self, user_id: str, activity_id: int,
                           limit: int = 30) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM care_activity_logs WHERE user_id=? AND activity_id=?"
            " ORDER BY local_date DESC LIMIT ?", (user_id, activity_id, limit)).fetchall()]

    # ---- P4 动作技术档案（扩展表，1:1 挂 motion_analyses）----

    def upsert_motion_tech_profile(self, user_id: str, analysis_id: int,
                                   exercise_id: str, profile: dict) -> None:
        self.conn.execute(
            "INSERT INTO motion_tech_profiles(analysis_id, user_id, exercise_id,"
            " model_version, video_quality, motion_observations, phase_timestamps,"
            " review_status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(analysis_id) DO UPDATE SET model_version=excluded.model_version,"
            " video_quality=excluded.video_quality,"
            " motion_observations=excluded.motion_observations,"
            " phase_timestamps=excluded.phase_timestamps,"
            " review_status=excluded.review_status, updated_at=excluded.updated_at",
            (analysis_id, user_id, exercise_id, profile["model_version"],
             json.dumps(profile.get("video_quality") or {}, ensure_ascii=False),
             json.dumps(profile.get("motion_observations") or [], ensure_ascii=False),
             json.dumps(profile.get("phase_timestamps") or [], ensure_ascii=False),
             profile.get("review_status", "unreviewed"), _now(), _now()))
        self.conn.commit()

    def get_motion_tech_profile(self, user_id: str, analysis_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM motion_tech_profiles WHERE user_id=? AND analysis_id=?",
            (user_id, analysis_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("video_quality", "motion_observations", "phase_timestamps"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except (ValueError, TypeError):
                d[key] = []
        return d

    def motion_profile_version(self, user_id: str) -> str:
        """技术档案版本（洞察漂移锚：重算/删除/备注变化都会变化——
        同秒重算靠内容长度签名区分）。"""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(MAX(updated_at),'') AS last,"
            " COALESCE(SUM(LENGTH(motion_observations)),0) AS obs_len,"
            " COALESCE(SUM(LENGTH(phase_timestamps)),0) AS phase_len"
            " FROM motion_tech_profiles WHERE user_id=?", (user_id,)).fetchone()
        return f"{row['n']}:{row['last']}:{row['obs_len']}:{row['phase_len']}"

    def delete_motion_analysis(self, user_id: str, analysis_id: int) -> bool:
        """删除视频分析（含关联技术档案与视频文件引用记录；视频文件保留
        由用户在文件系统层面管理——记录删除后不再可达）。"""
        row = self.conn.execute(
            "SELECT id FROM motion_analyses WHERE user_id=? AND id=?",
            (user_id, analysis_id)).fetchone()
        if not row:
            return False
        with self.conn:
            self.conn.execute(
                "DELETE FROM motion_tech_profiles WHERE user_id=? AND analysis_id=?",
                (user_id, analysis_id))
            self.conn.execute(
                "DELETE FROM motion_analyses WHERE user_id=? AND id=?",
                (user_id, analysis_id))
        return True

    def set_motion_user_notes(self, user_id: str, analysis_id: int,
                              notes: str) -> bool:
        cur = self.conn.execute(
            "UPDATE motion_tech_profiles SET user_notes=?, updated_at=?"
            " WHERE user_id=? AND analysis_id=?",
            (notes[:500], _now(), user_id, analysis_id))
        self.conn.commit()
        return cur.rowcount == 1

    # ---- P5-B2：训练地点与用户器械 ----

    @staticmethod
    def _location_row(row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        doc = dict(row)
        for key in ("required_equipment", "optional_equipment"):
            try:
                doc[key] = json.loads(doc.get(key) or "[]")
            except (ValueError, TypeError):
                doc[key] = []
        doc["is_current"] = bool(doc.get("is_current"))
        return doc

    def list_training_locations(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM training_locations WHERE user_id=?"
            " ORDER BY is_current DESC, id", (user_id,)).fetchall()
        return [self._location_row(row) for row in rows]

    def get_training_location(self, user_id: str, location_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM training_locations WHERE user_id=? AND id=?",
            (user_id, location_id)).fetchone()
        return self._location_row(row)

    def create_training_location(self, user_id: str, data: dict,
                                 make_current: bool = False) -> dict:
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            if not self.conn.execute(
                    "SELECT 1 FROM training_locations WHERE user_id=?", (user_id,)).fetchone():
                make_current = True
            if make_current:
                self.conn.execute(
                    "UPDATE training_locations SET is_current=0 WHERE user_id=?", (user_id,))
            try:
                cur = self.conn.execute(
                    "INSERT INTO training_locations(user_id,name,kind,"
                    " required_equipment,optional_equipment,is_current,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, data["name"], data["kind"],
                     json.dumps(data.get("required_equipment") or [], ensure_ascii=False),
                     json.dumps(data.get("optional_equipment") or [], ensure_ascii=False),
                     int(make_current), _now(), _now()))
            except sqlite3.IntegrityError:
                raise ValueError("地点名称已存在") from None
        return self.get_training_location(user_id, cur.lastrowid)

    def update_training_location(self, user_id: str, location_id: int,
                                 data: dict) -> dict:
        current = self.get_training_location(user_id, location_id)
        if not current:
            raise ValueError("训练地点不存在")
        next_doc = {**current, **data}
        with self.conn:
            try:
                self.conn.execute(
                    "UPDATE training_locations SET name=?, kind=?, required_equipment=?,"
                    " optional_equipment=?, updated_at=? WHERE user_id=? AND id=?",
                    (next_doc["name"], next_doc["kind"],
                     json.dumps(next_doc.get("required_equipment") or [], ensure_ascii=False),
                     json.dumps(next_doc.get("optional_equipment") or [], ensure_ascii=False),
                     _now(), user_id, location_id))
            except sqlite3.IntegrityError:
                raise ValueError("地点名称已存在") from None
        return self.get_training_location(user_id, location_id)

    def select_training_location(self, user_id: str, location_id: int) -> dict:
        if not self.get_training_location(user_id, location_id):
            raise ValueError("训练地点不存在")
        with self.conn:
            if not self.conn.in_transaction:
                self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                "UPDATE training_locations SET is_current=0 WHERE user_id=?", (user_id,))
            self.conn.execute(
                "UPDATE training_locations SET is_current=1, updated_at=?"
                " WHERE user_id=? AND id=?", (_now(), user_id, location_id))
        return self.get_training_location(user_id, location_id)

    def delete_training_location(self, user_id: str, location_id: int) -> bool:
        row = self.get_training_location(user_id, location_id)
        if not row:
            return False
        with self.conn:
            self.conn.execute(
                "DELETE FROM training_locations WHERE user_id=? AND id=?",
                (user_id, location_id))
            if row["is_current"]:
                nxt = self.conn.execute(
                    "SELECT id FROM training_locations WHERE user_id=? ORDER BY id LIMIT 1",
                    (user_id,)).fetchone()
                if nxt:
                    self.conn.execute(
                        "UPDATE training_locations SET is_current=1 WHERE user_id=? AND id=?",
                        (user_id, nxt["id"]))
        return True

    def list_user_equipment(self, user_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM user_equipment WHERE user_id=? ORDER BY name",
            (user_id,)).fetchall()
        out = []
        for row in rows:
            doc = dict(row)
            doc["id"] = doc["equipment_id"]
            try:
                doc["aliases"] = json.loads(doc.get("aliases") or "[]")
            except (ValueError, TypeError):
                doc["aliases"] = []
            doc["scope"] = "user"
            out.append(doc)
        return out

    def get_user_equipment(self, user_id: str, equipment_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM user_equipment WHERE user_id=? AND equipment_id=?",
            (user_id, equipment_id)).fetchone()
        if not row:
            return None
        doc = dict(row)
        doc["id"] = doc["equipment_id"]
        try:
            doc["aliases"] = json.loads(doc.get("aliases") or "[]")
        except (ValueError, TypeError):
            doc["aliases"] = []
        doc["scope"] = "user"
        return doc

    def add_user_equipment(self, user_id: str, equipment_id: str, data: dict) -> dict:
        with self.conn:
            try:
                self.conn.execute(
                    "INSERT INTO user_equipment(user_id,equipment_id,name,category,"
                    " aliases,fulfills,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, equipment_id, data["name"], data["category"],
                     json.dumps(data.get("aliases") or [], ensure_ascii=False),
                     data.get("fulfills") or None, _now(), _now()))
            except sqlite3.IntegrityError:
                raise ValueError("器械 ID 已存在") from None
        return self.get_user_equipment(user_id, equipment_id)

    def update_user_equipment(self, user_id: str, equipment_id: str, data: dict) -> dict:
        current = self.get_user_equipment(user_id, equipment_id)
        if not current:
            raise ValueError("自定义器械不存在")
        doc = {**current, **data}
        with self.conn:
            self.conn.execute(
                "UPDATE user_equipment SET name=?, category=?, aliases=?, fulfills=?,"
                " updated_at=? WHERE user_id=? AND equipment_id=?",
                (doc["name"], doc["category"],
                 json.dumps(doc.get("aliases") or [], ensure_ascii=False),
                 doc.get("fulfills") or None, _now(), user_id, equipment_id))
        return self.get_user_equipment(user_id, equipment_id)

    def delete_user_equipment(self, user_id: str, equipment_id: str) -> bool:
        if not self.get_user_equipment(user_id, equipment_id):
            return False
        rows = self.list_training_locations(user_id)
        with self.conn:
            self.conn.execute(
                "DELETE FROM user_equipment WHERE user_id=? AND equipment_id=?",
                (user_id, equipment_id))
            for row in rows:
                required = [x for x in row["required_equipment"] if x != equipment_id]
                optional = [x for x in row["optional_equipment"] if x != equipment_id]
                if (required != row["required_equipment"]
                        or optional != row["optional_equipment"]):
                    self.conn.execute(
                        "UPDATE training_locations SET required_equipment=?,"
                        " optional_equipment=?, updated_at=? WHERE user_id=? AND id=?",
                        (json.dumps(required, ensure_ascii=False),
                         json.dumps(optional, ensure_ascii=False),
                         _now(), user_id, row["id"]))
        return True
