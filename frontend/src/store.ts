// 客户端状态：当前用户、训练执行会话（刷新不丢）、休息计时、离线队列计数。
// 持久化用显式 localStorage 读写（zustand persist 中间件与严格 TS 的泛型
// 推断在重现问题，显式化反而更简单可靠）。
import { create } from 'zustand'

// M6.4-A：逐组记录 = 类型化 SetRecord + 会话字段（旧字段 weight/reps 由 weight_reps 类型承载）
export type LoggedSet = import('./types').SetRecord & {
  warmup: boolean
  at?: string
}

export interface SessionEntry {
  exercise_id: string
  name: string
  measurement?: import('./types').MeasurementType  // 记录类型（缺省 weight_reps）
  activity?: import('./types').ActivityMode        // P5-B：活动类别
  cardio?: import('./types').SessionEntryCardio    // P5-B：有氧执行状态
  hiitPlan?: import('./types').HiitPlan            // P5-B：HIIT 编排
  hiitRun?: import('./types').HiitRun              // P5-B：HIIT 执行状态
  supersetGroup?: string                           // M6.4-A：超级组分组（A/B/C…）
  target: { sets: number | string; reps: number | string; weight: number | null }
  note?: string
  logged: LoggedSet[]
  replaced_with?: string // 训练中临时替换（只影响本次记录，不改计划）
  replace_exercise_id?: string // M6.3：临时替换后动作的稳定 ID（保存时随记录提交）
  replaced_from_id?: string // P5-B2：本次替换的原动作 ID（只用于本次会话）
  planIndex?: number // P5-B2：计划日内原下标（长期替换提案定位）
}

/** M6.4-B B4.2：逐组输入草稿（进教学页返回后不丢；随会话持久化）。
 *  P5-A：method/segments（JSON 字符串）随草稿镜像。 */
export interface SetDraftValues {
  weight?: string; reps?: string; added?: string; assist?: string
  minutes?: string; seconds?: string; distance?: string; rpe?: string
  warmup?: boolean
  method?: string; segments?: string
}

/** P5-A：超级组执行配置（按组标签 A/B/C；轮次状态派生自已记录组数，
 *  刷新恢复=store 持久化天然带回）。 */
export interface SupersetConfig {
  rounds: number            // 目标轮次（默认=组内最少目标组数）
  restBetween: number       // 动作间休息（秒）
  restRounds: number        // 轮间休息（秒）
}

export interface WorkoutSession {
  id: string                       // 会话稳定身份（M6.3：保存/恢复/统计都按会话）
  mode: 'planned' | 'free'         // planned=按计划训练日；free=自由训练（不依赖计划）
  day: string                      // planned=训练日名；free='free'（展示层用"自由训练"）
  date: string
  entries: SessionEntry[]
  started_at: string
  notes: string
  templateId?: number              // M6.4-A.1：来源模板（纯自由训练无）
  planId?: number                  // 来源计划与版本（会话级溯源）
  planVersion?: number
  drafts?: Record<number, SetDraftValues>  // M6.4-B：entryIdx → 未提交输入
  supersetConfig?: Record<string, SupersetConfig>  // P5-A：按组标签
  /** P5-C2：仅本次采用的目标调整（entryIdx → 原目标 + 来源候选）。
   *  只覆盖 entry.target，绝不触碰已记录组/组法/超组/计时器/有氧 HIIT 状态；
   *  随会话持久化（刷新恢复），撤销后移除。仅本次——不写长期计划。 */
  appliedTargets?: Record<number, AppliedTargetRecord>
}

export interface AppliedTargetRecord {
  from: SessionEntry['target']
  optionId: string
}

export interface Settings {
  restSeconds: number
}

const newSessionId = (): string =>
  `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

/** 用户本地日期（复查 P1：UTC ISO 日期在临近午夜时不是用户所在日期） */
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const hasProgress = (s: WorkoutSession | null) =>
  !!s && s.entries.some((e) => e.logged.length > 0 || !!e.cardio || !!e.hiitRun)

/** P5-C2：候选目标 → 适用于该动作卡结构的目标补丁。
 *
 *  不兼容字段被剔除而不是硬套（普通力量负重不能覆盖递减组各段重量，
 *  次数/负重目标不适用于有氧/HIIT/时长/距离记录）。返回 patch 为空 +
 *  incompatible 非空 = 该候选对当前结构只能看方向。 */
export function compatibleTargetPatch(
  entry: Pick<SessionEntry, 'activity' | 'measurement' | 'logged'> | undefined,
  targets: Record<string, number | string>,
  draftMethod?: string,
): { patch: Partial<SessionEntry['target']>; incompatible: string[] } {
  const patch: Partial<SessionEntry['target']> = {}
  const incompatible: string[] = []
  if (!entry) return { patch, incompatible }
  const strengthLike = !entry.activity || entry.activity === 'strength'
  const measurement = entry.measurement || 'weight_reps'
  const logged = entry.logged.filter((l) => !l.warmup)
  const lastMethod =
    (logged[logged.length - 1] as { method?: string } | undefined)?.method
  const complex = !!draftMethod && draftMethod !== 'straight_set'
    ? draftMethod : lastMethod && lastMethod !== 'straight_set' ? lastMethod : ''
  if (targets.sets != null && targets.sets !== '') {
    if (strengthLike) patch.sets = targets.sets
    else incompatible.push('sets')
  }
  if (targets.reps != null && targets.reps !== '') {
    if (strengthLike && measurement !== 'duration'
        && measurement !== 'distance_time' && !complex) patch.reps = targets.reps
    else incompatible.push('reps')
  }
  if (targets.weight_kg != null) {
    if (strengthLike && measurement === 'weight_reps' && !complex) {
      patch.weight = Number(targets.weight_kg)
    } else incompatible.push('weight_kg')
  }
  if (targets.assistance_kg != null) {
    // 辅助重量走同一个"建议重量"通道（SetForm 的辅助输入预填）
    if (strengthLike && measurement === 'assisted_reps' && !complex) {
      patch.weight = Number(targets.assistance_kg)
    } else incompatible.push('assistance_kg')
  }
  return { patch, incompatible }
}

/** 兼容旧持久化数据：补 id / mode / drafts（升级前创建的进行中会话） */
export function normalizeSession(s: WorkoutSession | null): WorkoutSession | null {
  if (!s) return null
  const entries = (s.entries || []).map((entry) => {
    const cardio = entry.cardio
    if (!cardio) return entry
    const status = cardio.status
      ?? (cardio.endedAt != null ? 'ended'
        : cardio.pausedAt != null ? 'paused'
          : cardio.startedAt != null ? 'running' : 'idle')
    return { ...entry, cardio: { ...cardio, status,
      startedAt: cardio.startedAt ?? null, pausedAt: cardio.pausedAt ?? null,
      endedAt: cardio.endedAt ?? null, pausedTotalMs: cardio.pausedTotalMs ?? 0 } }
  })
  return { ...s, entries, id: s.id || newSessionId(), mode: s.mode || 'planned',
           drafts: s.drafts || {} }
}

interface AppState {
  uid: string
  setUid: (uid: string) => void

  session: WorkoutSession | null
  /** 开始计划训练。kept=true 表示未创建新会话：
   *  resumed=true 为同目标恢复（已记录组原样保留）；否则是冲突等待用户选择（P0-1）。 */
  startSession: (day: string, entries: SessionEntry[],
                 meta?: { planId?: number; planVersion?: number }) =>
    { kept: boolean; resumed?: boolean }
  /** 开始自由/模板训练。templateId 为会话身份：同模板恢复，不同模板视为不同目标。 */
  startFreeSession: (opts?: { label?: string; templateId?: number }) =>
    { kept: boolean; resumed?: boolean }
  addFreeExercise: (entry: SessionEntry) => void
  updateEntry: (entryIdx: number, patch: Partial<SessionEntry>) => void  // P5-B：有氧/HIIT 状态写入
  setEntryGroup: (entryIdx: number, group?: string) => void
  removeEntry: (entryIdx: number) => void
  logSet: (entryIdx: number, s: LoggedSet) => void
  removeLastSet: (entryIdx: number) => void
  replaceExercise: (entryIdx: number, newName: string, exerciseId?: string,
                    measurement?: import('./types').MeasurementType) => void
  /** P5-C2：仅本次采用候选目标（只改目标，不碰已记录组/组法/超组/计时器/
   *  有氧 HIIT 状态；不兼容字段被拒绝；可撤销；随会话持久化；不改长期计划）。 */
  applySessionTarget: (entryIdx: number,
                       targets: Record<string, number | string>,
                       optionId: string) =>
    { applied: boolean; incompatible: string[] }
  revertSessionTarget: (entryIdx: number) => boolean
  setSessionNotes: (notes: string) => void
  setSupersetConfig: (group: string, cfg: Partial<SupersetConfig>) => void
  /** M6.4-B B4.2：逐组输入草稿写入（教学页往返/刷新不丢） */
  setEntryDraft: (entryIdx: number, patch: Partial<SetDraftValues>) => void
  clearSession: () => void

  restEndsAt: number | null
  startRest: () => void
  stopRest: () => void

  settings: Settings
  setRestSeconds: (n: number) => void

  offlineCount: number
  setOfflineCount: (n: number) => void
}

const STORAGE_KEY = 'fc-app-v1'
const PERSISTED_KEYS = ('uid session settings offlineCount').split(' ')

function loadPersisted(): Partial<AppState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const key of PERSISTED_KEYS) {
      if (key in parsed) out[key] = parsed[key]
    }
    if (out.session) out.session = normalizeSession(out.session as WorkoutSession)
    return out as Partial<AppState>
  } catch {
    return {}
  }
}

export const useApp = create<AppState>()((set) => ({
  uid: '',
  setUid: (uid) => set({ uid, session: null }),

  session: null,
  startSession: (day, entries, meta) => {
    const cur = useApp.getState().session
    // 同目标重复启动：直接恢复现有会话，绝不重新初始化（P1）
    if (cur && cur.mode === 'planned' && cur.day === day) return { kept: true, resumed: true }
    // 目标不同且已有记录：保留现有会话，由调用方提示用户选择（P0-1）
    if (cur && hasProgress(cur)) return { kept: true }
    set({ session: { id: newSessionId(), mode: 'planned', day, date: today(),
                     entries, started_at: new Date().toISOString(), notes: '',
                     planId: meta?.planId, planVersion: meta?.planVersion } })
    return { kept: false }
  },
  startFreeSession: (opts) => {
    const cur = useApp.getState().session
    // 模板/自由身份一致（含同为"无模板"的自由训练）→ 恢复
    if (cur && cur.mode === 'free' && cur.templateId === opts?.templateId)
      return { kept: true, resumed: true }
    if (cur && hasProgress(cur)) return { kept: true }
    set({ session: { id: newSessionId(), mode: 'free', day: opts?.label || 'free',
                     date: today(), entries: [],
                     started_at: new Date().toISOString(), notes: '',
                     templateId: opts?.templateId } })
    return { kept: false }
  },
  addFreeExercise: (entry) =>
    set((st) => (st.session && st.session.mode === 'free'
      ? { session: { ...st.session, entries: [...st.session.entries, entry] } } : st)),
  updateEntry: (entryIdx, patch) =>
    set((st) => (st.session
      ? { session: { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, ...patch } : e) } }
      : st)),
  setEntryGroup: (entryIdx, group) =>
    set((st) => (st.session
      ? { session: { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, supersetGroup: group } : e) } }
      : st)),
  removeEntry: (entryIdx) =>
    set((st) => {
      if (!st.session) return st
      // M6.4-B：同步平移逐组草稿键，保持与 entries 索引一致
      const drafts: Record<number, SetDraftValues> = {}
      for (const [k, v] of Object.entries(st.session.drafts || {})) {
        const i = Number(k)
        if (i === entryIdx) continue
        drafts[i > entryIdx ? i - 1 : i] = v
      }
      // P5-C2：仅本次目标调整同样按索引平移
      const appliedTargets: Record<number, AppliedTargetRecord> = {}
      for (const [k, v] of Object.entries(st.session.appliedTargets || {})) {
        const i = Number(k)
        if (i === entryIdx) continue
        appliedTargets[i > entryIdx ? i - 1 : i] = v
      }
      return { session: { ...st.session, drafts, appliedTargets,
        entries: st.session.entries.filter((_, i) => i !== entryIdx) } }
    }),
  setEntryDraft: (entryIdx, patch) =>
    set((st) => (st.session
      ? { session: { ...st.session, drafts: {
            ...(st.session.drafts || {}),
            [entryIdx]: { ...(st.session.drafts?.[entryIdx] || {}), ...patch } } } }
      : st)),
  logSet: (entryIdx, s) =>
    set((st) => ({
      session: st.session
        ? { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, logged: [...e.logged, s] } : e) }
        : st.session,
    })),
  removeLastSet: (entryIdx) =>
    set((st) => ({
      session: st.session
        ? { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, logged: e.logged.slice(0, -1) } : e) }
        : st.session,
    })),
  replaceExercise: (entryIdx, newName, exerciseId, measurement) =>
    set((st) => {
      const session = st.session
      if (!session) return { session }
      const rec = session.appliedTargets?.[entryIdx]
      const appliedTargets = rec
        ? Object.fromEntries(
            Object.entries(session.appliedTargets || {}).filter(([k]) => Number(k) !== entryIdx))
        : session.appliedTargets
      const revertedTarget = rec?.from
      const entries = session.entries.map((e, i) => {
        if (i !== entryIdx) return e
        const measurementChanged = !!measurement && measurement !== e.measurement
        return { ...e, replaced_with: newName,
          replace_exercise_id: exerciseId,
          replaced_from_id: e.replaced_from_id ?? e.exercise_id,
          ...(measurement ? { measurement } : {}),
          ...(revertedTarget ? { target: revertedTarget } : {}),
          ...(measurementChanged
            ? { target: { ...(revertedTarget || e.target), weight: null } } : {})
        }
      })
      return { session: { ...session, appliedTargets, entries } }
    }),
  applySessionTarget: (entryIdx, targets, optionId) => {
    const st = useApp.getState()
    const session = st.session
    const entry = session?.entries[entryIdx]
    if (!session || !entry) return { applied: false, incompatible: ['no-entry'] }
    const { patch, incompatible } = compatibleTargetPatch(
      entry, targets, session.drafts?.[entryIdx]?.method)
    if (Object.keys(patch).length === 0) {
      return { applied: false, incompatible }
    }
    set((s) => (s.session
      ? { session: {
          ...s.session,
          appliedTargets: {
            ...(s.session.appliedTargets || {}),
            [entryIdx]: { from: entry.target, optionId } },
          entries: s.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, target: { ...e.target, ...patch } } : e),
        } }
      : s))
    return { applied: true, incompatible }
  },
  revertSessionTarget: (entryIdx) => {
    const st = useApp.getState()
    const record = st.session?.appliedTargets?.[entryIdx]
    if (!st.session || !record) return false
    set((s) => {
      if (!s.session) return s
      const appliedTargets = { ...(s.session.appliedTargets || {}) }
      delete appliedTargets[entryIdx]
      return { session: {
        ...s.session,
        appliedTargets,
        entries: s.session.entries.map((e, i) =>
          i === entryIdx ? { ...e, target: record.from } : e),
      } }
    })
    return true
  },
  setSessionNotes: (notes) =>
    set((st) => (st.session ? { session: { ...st.session, notes } } : st)),
  setSupersetConfig: (group, cfg) =>
    set((st) => (st.session
      ? { session: { ...st.session,
          supersetConfig: { ...(st.session.supersetConfig || {}),
            [group]: Object.assign(
              { rounds: 3, restBetween: 30, restRounds: 90 },
              (st.session.supersetConfig || {})[group] ?? {}, cfg) } } }
      : st)),
  clearSession: () => set({ session: null }),

  restEndsAt: null,
  startRest: () => set({ restEndsAt: Date.now() + useApp.getState().settings.restSeconds * 1000 }),
  stopRest: () => set({ restEndsAt: null }),

  settings: { restSeconds: 90 },
  setRestSeconds: (n: number) => set({ settings: { restSeconds: n } }),

  offlineCount: 0,
  setOfflineCount: (n: number) => set({ offlineCount: n }),

  ...loadPersisted(),
}))

// 每次状态变化后把需要跨会话保留的部分写回 localStorage
useApp.subscribe((state) => {
  try {
    const slim: Record<string, unknown> = {}
    for (const key of PERSISTED_KEYS) slim[key] = (state as unknown as Record<string, unknown>)[key]
    if (slim.session) slim.session = normalizeSession(slim.session as WorkoutSession)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  } catch { /* 隐私模式等场景下持久化不可用，不影响功能 */ }
})
