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

// M6.4-A：类型化逐组记录——不同记录类型使用不同指标，绝不混用公式
export type MeasurementType =
  | 'weight_reps' | 'bodyweight_reps' | 'assisted_reps' | 'duration' | 'distance_time'

// P5-A：训练方法（与测量类型正交——method 描述执行方法，type 描述测量口径）
export type SetMethod = 'straight_set' | 'drop_set' | 'rest_pause' | 'unilateral'

// 复杂组的执行段：递减/休息暂停 = 负荷段；单侧 = 左右侧段
export type SetSegment =
  | { weight_kg: number; reps: number; rest_seconds?: number }          // drop/rest-pause
  | { side: 'left' | 'right'; weight_kg: number; reps: number }         // unilateral
  | { side: 'left' | 'right'; reps: number; added_weight_kg?: number }  // unilateral 自重

export type SetRecord =
  | { type: 'weight_reps'; weight_kg: number; reps: number; rpe?: number
      method?: SetMethod; segments?: SetSegment[] }
  | { type: 'bodyweight_reps'; reps: number; added_weight_kg?: number; rpe?: number
      method?: SetMethod; segments?: SetSegment[] }
  | { type: 'assisted_reps'; reps: number; assistance_kg: number; rpe?: number
      method?: SetMethod; segments?: SetSegment[] }
  | { type: 'duration'; duration_seconds: number }
  | { type: 'distance_time'; distance_m: number; duration_seconds: number; weight_kg?: number }

export interface SetLog {
  type?: MeasurementType            // 缺省按 weight_reps（旧记录兼容）
  method?: SetMethod                // P5-A：缺省 straight_set（旧记录兼容）
  segments?: SetSegment[]           // 复杂组的执行段（method!=straight_set 时）
  weight_kg?: number | null
  reps?: number | null
  rpe?: number | null
  warmup?: boolean
  at?: string
  added_weight_kg?: number | null
  assistance_kg?: number | null
  duration_seconds?: number | null
  distance_m?: number | null
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
  last_reason?: string | null // 最近一次修订原因（list_checkins 附带；无修订为 null）
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
  measurement?: MeasurementType   // 记录类型（缺省 weight_reps）
}

export interface TrainingTemplate {
  id: number
  name: string
  entries: {
    exercise_id: string
    name: string
    measurement?: MeasurementType
    superset_group?: string
  }[]
  note?: string
  created_at?: string
  updated_at?: string
}

// M6.4-B：三维演示（lib/demo.ts 的 Demo3D 与此同构；此处为 api 返回形状）
export interface Demo3D {
  model_url: string
  preview_url?: string
  animation_name: string
  duration: number
  loop: boolean
  supported_views: string[]
  teaching_phases: { key: string; label: string; t: [number, number] }[]
  review_status?: string
  size_bytes?: number
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
  // M6.2：knowledge_refs 教学文档（原文 + 来源元数据）
  teaching?: { path: string; topic: string; source: string[]; provenance: string; updated: string; markdown: string }[]
  // M6.4-B：结构化教学（逐节审核状态）与演示可用性
  teaching_content?: TeachingContent
  demos?: { model_3d: Demo3D | null; text: boolean; public_video: boolean }
}

export interface TeachingSection {
  status: string
  items?: unknown[]
  note?: string
}

export interface TeachingContent {
  exercise_id: string
  content_version: number
  updated: string
  review_status: string
  completeness: string
  sources: { type?: string; ref?: string; note?: string }[]
  sections: Record<string, TeachingSection>
  /** 交付/复核审查挂起的争议点（可追溯；不改写原文） */
  review_notes?: { date?: string; by?: string; pending?: string[] }[]
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

// ---- M6.3 训练数据分析（逐组口径；后端 coach/analytics） ----
export interface ExerciseSessionSet {
  weight_kg: number | null
  reps: number | null
  at?: string | null
  e1rm: number | null
  volume: number
}

export interface ExerciseSession {
  checkin_id: number
  date: string
  working_sets: number
  reps_total: number
  volume: number
  best_set: { weight_kg: number; reps: number | null } | null
  best_e1rm: number | null
  duration_min: number | null
  sets: ExerciseSessionSet[]
}

export interface ExerciseRecords {
  heaviest: { weight_kg: number; reps: number | null; date: string } | null
  best_e1rm: { e1rm: number; weight_kg: number; reps: number | null; date: string } | null
  max_reps: { reps: number; weight_kg: number | null; date: string } | null
  best_volume_session: { volume: number; working_sets: number; date: string } | null
  longest_set: { duration_seconds: number; date: string } | null
  farthest: { distance_m: number; date: string } | null
}

export interface TrainingCalendar {
  year: number
  month: number
  days: { date: string; sessions: number; working_sets: number; volume: number }[]
}

export interface PeriodSummary {
  days: number
  sessions: number
  training_days: number
  per_week: number
  working_sets: number
  volume: number
  by_muscle: Record<string, number>
  avg_duration_min: number | null
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

// ---- P0 专家平台（后端 coach/experts/） ----

export interface InsightFinding {
  finding_id: string
  kind: string                     // session-baseline / comparison / trend
  text: string
  fact_ids: string[]
  source_ids: string[]             // checkin:ID:revision:N 追溯链
  evidence?: 'verified' | 'unverified'
}

export interface InsightOption {
  option_id: string
  title: string
  detail: string
  basis: string[]
  tradeoffs: { 收益: string; 代价: string; 适用条件: string }
  action: 'proposal' | 'advisory'
  proposal_hint?: {
    target: 'plan' | 'approach'
    operations: Record<string, unknown>[]
  }
}

export interface ExpertFact {
  fact_id: string
  metric: string
  exercise_id?: string
  value: number | null
  unit: string
  measurement_type: string
  window: { start: string; end: string; days: number }
  source_ids: string[]
  calculation: string
  data_quality?: Record<string, unknown>
  status: string                   // observed / estimated / insufficient
  note?: string
}

/** 洞察列表行（轻载荷：无 findings/options/facts_snapshot） */
export interface ExpertInsightSummary {
  id: string
  specialist: string
  insight_type: string
  title: string
  summary: string
  status: string                   // ready/viewed/dismissed/expired/invalidated
  confidence: string               // high/medium/low
  confidence_basis: string
  generated_at: string
  expires_at: string | null
  status_reason?: string
  read_at?: string | null
}

export interface ExpertInsight extends ExpertInsightSummary {
  task_id: string | null
  findings: InsightFinding[]
  evidence_refs: string[]
  facts_snapshot: { window: { start: string; end: string; days: number }
                    facts: ExpertFact[]
                    exercises_covered: string[]
                    caliber: string }
  knowledge_refs: { engine: string; ref: string; title: string
                    provenance: string }[]
  options: InsightOption[]
  limitations: string[]
  source_revision: { checkins?: Record<string, number>; plan_version?: number }
  input_refs?: { checkin_id?: number; exercise_ids?: string[] }
}

export interface ExpertTask {
  id: string
  specialist: string
  task_type: string
  trigger_source: string
  input_refs: Record<string, unknown>
  status: string                   // pending/running/ready/failed/cancelled
  retry_count: number
  max_retries: number
  insight_id: string | null
  created_at: string
  completed_at: string | null
  error_code: string | null
  error: string | null
  events?: { event: string; detail: string | null; at: string }[]
}

export interface ExpertSettings {
  proactive_enabled: boolean
  min_interval_minutes: number
}

export interface ExpertSpecialistInfo {
  specialist: string
  label: string
  domain: string
  data_sources: string[]
  tools: string[]
  workbench: 'ready' | 'planned'
  workbench_path: string | null
  workbench_note?: string
  active_insights: number
}

export interface ExpertOverview {
  specialists: ExpertSpecialistInfo[]
  orchestrator: { key: string; label: string; note: string }
  shared_services: Record<string, { label: string; note: string }>
  settings: ExpertSettings
  pending_tasks: ExpertTask[]
}

// ---- P1 营养系统（后端 coach/nutrition/） ----

export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack'

export interface ServingUnit { unit: string; grams: number }

export interface FoodItem {
  id: string
  user_id: string | null
  name: string
  aliases: string[]
  brand: string | null
  category: string
  serving_units: ServingUnit[]
  energy_kcal: number | null
  protein_g: number | null
  carbohydrate_g: number | null
  fat_g: number | null
  fiber_g: number | null
  sodium_mg: number | null
  reference_amount: number
  reference_unit: string
  source_name: string | null
  source_url: string | null
  source_version: string | null
  license: string | null
  verified_status: string
}

export interface MealItem {
  food_id: string
  food_name: string
  amount: number
  unit: string
  grams: number
  nutrition_snapshot: Record<string, number | null>
  snapshot_meta: { reference_amount?: number; reference_unit?: string
                   source_name?: string; verified_status?: string }
  intake: Record<string, number | null>
}

export interface NutrientTotals {
  energy_kcal: number; protein_g: number; carbohydrate_g: number
  fat_g: number; fiber_g: number; sodium_mg: number
}

export interface NutritionSummaryBlock {
  totals: NutrientTotals
  items_count: number
  data_quality: Record<string, { known: number; unknown: number }>
}

export interface MealRecord {
  id: number
  meal_type: MealType
  notes: string
  items: MealItem[]
  /** 汇总块与服务端 summarize 输出同构（列表页由前端重算或后端给出） */
  totals?: NutrientTotals
}

export interface DayNutrition {
  user_id: string
  local_date: string
  meals: (NutritionSummaryBlock & { id: number; meal_type: MealType; notes: string
                                    items: MealItem[] })[]
  by_meal: Record<string, NutritionSummaryBlock & { meal_id: number; notes: string }>
  day: NutritionSummaryBlock
  meal_types_recorded: MealType[]
  complete_mark: boolean
  note: string
}

export interface NutritionTrendDay {
  local_date: string
  complete_mark: boolean
  meal_types: MealType[]
  totals: NutrientTotals
  data_quality: Record<string, { known: number; unknown: number }>
}

export interface NutritionTargets {
  energy_kcal: number | null
  protein_g: number | null
  carbohydrate_g: number | null
  fat_g: number | null
  preferences: Record<string, unknown>
  allergies: string[]
  budget_note: string | null
  precision_willing: string | null
  updated_at?: string
}

export interface NutritionReference {
  bmr?: number
  activity_factors?: Record<string, { label: string; tdee: number }>
  protein_reference?: { note: string; per_kg_range: number[]; at_weight_kg: number }
  goal_primary?: string
  energy_kcal?: number | null
  note: string
}

export interface Recipe {
  id: number
  name: string
  items: MealItem[]
  updated_at: string
}

// ---- P2 身体数据与恢复管理（后端 coach/body + coach/recovery） ----

export interface BodyMeasurement {
  id: number
  user_id: string
  measured_at: string
  local_date: string
  timezone: string | null
  weight_kg: number | null
  waist_cm: number | null
  hip_cm: number | null
  chest_cm: number | null
  body_fat_percent: number | null
  muscle_mass_kg: number | null
  measurement_method: string | null
  device_source: string | null
  notes: string | null
  migrated_from: string | null
  revision: number
  created_at: string
  updated_at: string
}

export type BodyMetricKey =
  | 'weight_kg' | 'waist_cm' | 'hip_cm' | 'chest_cm'
  | 'body_fat_percent' | 'muscle_mass_kg'

export interface BodyFact {
  fact_id: string
  metric: string
  value: number | null
  unit: string
  measurement_type: string
  window: Record<string, unknown>
  source_ids: string[]
  calculation: string
  data_quality: Record<string, unknown>
  status: string
  note?: string
  method?: string | null
  device_source?: string | null
}

export interface BodySummary {
  window: { start: string; end: string; days: number; label: string }
  measurement_days: number
  latest: Record<string, { value: number; measured_at: string; source_id: string
                           method: string | null; device_source: string | null }>
  facts: BodyFact[]
  observations: string[]
  limitations: string[]
  total_records: number
}

export interface BodyTrend {
  metric: BodyMetricKey
  label: string
  unit: string
  days_window: number | null
  points: { date: string; value: number }[]
  change: { first: number; last: number; delta: number; first_date: string
            last_date: string; span_days: number | null; points: number } | null
  note: string
}

export interface RecoveryCheckin {
  id: number
  user_id: string
  local_date: string
  recorded_at: string
  timezone: string | null
  sleep_hours: number | null
  sleep_quality: number | null
  fatigue: number | null
  muscle_soreness: number | null
  training_readiness: number | null
  soreness_regions: string[]
  notes: string | null
  revision: number
  updated_at: string
}

export interface RecoveryFact {
  fact_id: string
  metric: string
  value: number | null
  unit: string
  measurement_type: string    // recovery / session（负荷上下文）
  window: Record<string, unknown>
  source_ids: string[]
  calculation: string
  data_quality: Record<string, unknown>
  status: string
  note?: string
}

export interface RecoverySummary {
  window: { start: string; end: string; days: number }
  records_count: number
  records: (Pick<RecoveryCheckin, 'id' | 'local_date' | 'revision' |
    'sleep_hours' | 'sleep_quality' | 'fatigue' | 'muscle_soreness' |
    'training_readiness' | 'soreness_regions' | 'notes'>)[]
  facts: RecoveryFact[]
  observations: string[]
  data_quality: Record<string, string>
  limitations: string[]
}

export interface RecoveryBrief {
  user_id: string
  stance: 'restricted' | 'caution' | 'clear'
  headline: string
  observations: string[]
  signals: string[]
  restrictions: string[]
  options: { option_id: string; title: string }[]
  latest_recovery: { local_date: string; sleep_hours: number | null
    sleep_quality: number | null; fatigue: number | null
    muscle_soreness: number | null; training_readiness: number | null } | null
  training_load_7d: { metric: string; value: number; unit: string }[]
  plan_today: string | null
  note: string
}

// ---- P3 康复辅助（后端 coach/rehab/） ----

export interface TriageResult {
  action: 'urgent_evaluation' | 'professional_evaluation' | 'uncertain'
          | 'general_information'
  matched_rules: { rule_id: string; hits: string[]; action: string }[]
  message: string
  restriction_hint: string | null
  rules_version: string
  review_status: string
  disclaimer: string
}

export interface SymptomObservation {
  id: number
  episode_id: number
  recorded_at: string
  severity: number | null
  symptom_description: string | null
  functional_limitations: string[]
  user_notes: string | null
  triage_result: TriageResult | null
}

export interface SymptomEpisode {
  id: number
  body_region: string
  region_label?: string
  side: string | null
  onset_at: string
  onset_context: string | null
  description: string
  related_checkin_id: number | null
  professional_evaluated: number | boolean
  status: string
  updated_at: string
  observations?: SymptomObservation[]
}

export interface TrainingRestriction {
  id: number
  source_type: 'user_reported' | 'professional' | 'triage_recommended'
  source_evidence: string
  affected_activities: { regions: string[]; movements: string[]; notes?: string }
  restriction_description: string
  related_episode_id: number | null
  effective_at: string
  review_at: string | null
  status: string
  lift_evidence: string | null
  revision: number
}

export interface CareActivity {
  id: number
  name: string
  frequency: string | null
  notes: string | null
  logs: { id: number; local_date: string; completed: number
          feedback: string | null }[]
}

export interface CarePlan {
  id: number
  title: string
  professional_source: string
  applicable_conditions: string | null
  related_episode_id: number | null
  review_at: string | null
  status: string
  activities: CareActivity[]
}
