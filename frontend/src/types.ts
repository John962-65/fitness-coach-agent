// 与 backend/（TASKBOOK_2.0 §五）对应的 API 类型
export interface PlanEntry {
  exercise_id: string
  name: string
  role: string
  sets: number | string
  reps: number | string
  weight_kg?: number
  note?: string
  why?: string
}

export interface PlanDay {
  day: string
  focus: string
  exercises: PlanEntry[]
  estimated_minutes?: number
}

export interface Plan {
  template: string
  level: string
  days_per_week: number
  goal_version: number
  medical_status?: string
  medical_evidence?: string
  schedule: PlanDay[]
  notes: string[]
  deload?: { until: string; factor: number }
  adjust_action?: string
  approach_revision?: number
}

export interface PlanResponse {
  plan_id: number
  version: number
  fenced: boolean
  base_version: { plan_id: number; plan_version: number }
  content: Plan
  text: string
}

export interface TodayBrief {
  medical: { status: string; allows_prescription: boolean }
  plan_fenced: boolean
  open_pain_flags: number
  due_review_notes: number[]
  due_review_trials: number[]
  last_training_date: string | null
  days_since_last_training: number | null
  sessions_last_7_days: number
  plan_days_per_week: number | null
  plan: {
    id: number
    version: number
    template: string
    days: { day: string; focus: string; exercises: string[] }[]
  } | null
  plan_stale_vs_approach: boolean
  onboarding_done: boolean
}

export interface Profile {
  basic: Record<string, unknown>
  experience: { level?: string; training_years?: number; big3?: Record<string, number> }
  goal: { primary?: string; phase?: string; version?: number; timeline?: string }
  resources: { location?: string; days_per_week?: number; session_minutes?: number }
  conditions: Record<string, unknown>
  onboarding_done: boolean
  plan_fence?: { reason: string } | null
  [k: string]: unknown
}

export interface SetLog {
  weight_kg?: number | null
  reps?: number | null
  rpe?: number | null
  warmup?: boolean
  at?: string
}

export interface CheckinExercise {
  name: string
  exercise_id?: string | null
  weight_kg?: number
  reps?: number
  rpe?: number
  sets?: number | string
  set_logs?: SetLog[] // M1.1 P0-4：逐组完整记录（服务端同时派生兼容聚合字段）
  [k: string]: unknown
}

export interface Checkin {
  id: number
  revision: number
  type: string
  data: { exercises?: CheckinExercise[]; raw?: string; [k: string]: unknown }
  at: string
}

export interface ExerciseSummary {
  id: string
  name: string
  aliases: string[]
  pattern: string
  primary: string[]
  equipment: string[]
  location: string[]
  status: string
}

export interface ExerciseDetail extends Partial<Record<string, unknown>> {
  id: string
  name: string
  status: string
  aliases?: string[]
  notes?: string[]
  setup?: string
  cues?: string[]
  errors?: string[]
  self_check?: string[]
  joint_stress?: Record<string, number>
}

export interface ApproachRevision {
  revision: number
  initiator: string
  reason: string
  confirmed: number
  proposal_id: string | null
  affected_plan_version: number | null
  created_at: string
  diff: { field: string; old?: unknown; new?: unknown }[]
}

export interface ApproachView {
  initialized: boolean
  approach?: {
    revision: number
    structure: { value: string; note?: string; status?: string }
    intensity_style: { value: string; note?: string }
    exercise_selection: {
      exercise_id: string
      role: string | null
      status: string
      note?: string
    }[]
    execution_choices: { exercise_id: string; choices: Record<string, string> }[]
    diet_approach: { strategy?: string; note?: string }
    recovery_approach: { note?: string; deload_policy?: string }
    preferences: { liked: string[]; disliked: string[] }
  }
  referenced?: {
    goal: Record<string, unknown>
    resources: Record<string, unknown>
    conditions: { injuries: string[]; plan_fence: boolean; open_pain_flags: number }
    active_trial: { id: number; change_desc: string; review_at: string | null } | null
    active_plan: { id: number; version: number; template: string; approach_revision: number | null } | null
  }
}

export interface Proposal {
  id: string
  target: string
  source: string
  reason: string
  status: string
  base_version: Record<string, unknown>
  operations: Record<string, unknown>[]
  result: Record<string, unknown> | null
  created_at: string
  decided_at: string | null
}

export interface Consultation {
  id: number
  question: string
  specialists: string[]
  advices: {
    specialist: string
    label: string
    problem: string
    options: { title: string; detail: string }[]
    knowledge_basis: string[]
    conditions: string[]
  }[]
  at: string
}

export interface PlanRevision {
  id: number
  version: number
  active: boolean
  at: string
  action: string | null
  reason: string | null
  template: string
  days: (string | undefined)[]
}

export interface Trial {
  id: number
  change_desc: string
  reason: string
  observe: string
  stop_rule: string
  review_at: string | null
  outcome: string | null
  baseline?: string | null
  decision: string | null
  status: string
  created_at: string
  due_review: boolean
}

export interface ExerciseState {
  exercise_id: string
  last_weight: number | null
  last_rpe: number | null
  best_e1rm: number | null
  status: string | null
  discomfort: string | null
  preference: number | null
}

export interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

// 统一修改协议的操作（与 coach/plan_edit.py PLAN_OPS 对齐）
export type PlanOp =
  | { op: 'add_exercise'; day: string; exercise: string; sets: number | string; reps: number | string; weight_kg?: number; role?: string; note?: string; index?: number }
  | { op: 'remove_exercise'; day: string; index?: number; exercise?: string }
  | { op: 'replace_exercise'; day: string; index?: number; exercise?: string; sets?: number | string; reps?: number | string; weight_kg?: number; note?: string }
  | { op: 'reorder_exercise'; day: string; from: number; to: number }
  | { op: 'edit_set_prescription'; day: string; index: number; sets?: number | string; reps?: number | string; weight_kg?: number; note?: string }
  | { op: 'rename_day'; day: string; new_name: string }

export type ApproachOp =
  | { op: 'set_dimension'; dimension: string; value: Record<string, unknown> }
  | { op: 'upsert_exercise_choice'; exercise_id: string; set: Record<string, unknown> }
  | { op: 'remove_exercise_choice'; exercise_id: string }
  | { op: 'upsert_execution_choice'; exercise_id: string; choices: Record<string, string>; note?: string }
