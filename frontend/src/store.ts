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
  supersetGroup?: string                           // M6.4-A：超级组分组（A/B/C…）
  target: { sets: number | string; reps: number | string; weight: number | null }
  note?: string
  logged: LoggedSet[]
  replaced_with?: string // 训练中临时替换（只影响本次记录，不改计划）
  replace_exercise_id?: string // M6.3：临时替换后动作的稳定 ID（保存时随记录提交）
}

export interface WorkoutSession {
  id: string                       // 会话稳定身份（M6.3：保存/恢复/统计都按会话）
  mode: 'planned' | 'free'         // planned=按计划训练日；free=自由训练（不依赖计划）
  day: string                      // planned=训练日名；free='free'（展示层用"自由训练"）
  date: string
  entries: SessionEntry[]
  started_at: string
  notes: string
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
  !!s && s.entries.some((e) => e.logged.length > 0)

/** 兼容旧持久化数据：补 id / mode（升级前创建的进行中会话） */
function normalizeSession(s: WorkoutSession | null): WorkoutSession | null {
  if (!s) return null
  return { ...s, id: s.id || newSessionId(), mode: s.mode || 'planned' }
}

interface AppState {
  uid: string
  setUid: (uid: string) => void

  session: WorkoutSession | null
  /** 开始计划训练。kept=true 表示未创建新会话：
   *  resumed=true 为同目标恢复（已记录组原样保留）；否则是冲突等待用户选择（P0-1）。 */
  startSession: (day: string, entries: SessionEntry[]) => { kept: boolean; resumed?: boolean }
  /** 开始自由训练。语义同上。 */
  startFreeSession: (label?: string) => { kept: boolean; resumed?: boolean }
  addFreeExercise: (entry: SessionEntry) => void
  setEntryGroup: (entryIdx: number, group?: string) => void
  removeEntry: (entryIdx: number) => void
  logSet: (entryIdx: number, s: LoggedSet) => void
  removeLastSet: (entryIdx: number) => void
  replaceExercise: (entryIdx: number, newName: string, exerciseId?: string) => void
  setSessionNotes: (notes: string) => void
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
  startSession: (day, entries) => {
    const cur = useApp.getState().session
    // 同目标重复启动：直接恢复现有会话，绝不重新初始化（P1）
    if (cur && cur.mode === 'planned' && cur.day === day) return { kept: true, resumed: true }
    // 目标不同且已有记录：保留现有会话，由调用方提示用户选择（P0-1）
    if (cur && hasProgress(cur)) return { kept: true }
    set({ session: { id: newSessionId(), mode: 'planned', day, date: today(),
                     entries, started_at: new Date().toISOString(), notes: '' } })
    return { kept: false }
  },
  startFreeSession: (label?: string) => {
    const cur = useApp.getState().session
    if (cur && cur.mode === 'free') return { kept: true, resumed: true }
    if (cur && hasProgress(cur)) return { kept: true }
    set({ session: { id: newSessionId(), mode: 'free', day: label || 'free', date: today(),
                     entries: [], started_at: new Date().toISOString(), notes: '' } })
    return { kept: false }
  },
  addFreeExercise: (entry) =>
    set((st) => (st.session && st.session.mode === 'free'
      ? { session: { ...st.session, entries: [...st.session.entries, entry] } } : st)),
  setEntryGroup: (entryIdx, group) =>
    set((st) => (st.session
      ? { session: { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, supersetGroup: group } : e) } }
      : st)),
  removeEntry: (entryIdx) =>
    set((st) => (st.session
      ? { session: { ...st.session, entries: st.session.entries.filter((_, i) => i !== entryIdx) } }
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
  replaceExercise: (entryIdx, newName, exerciseId) =>
    set((st) => ({
      session: st.session
        ? { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, replaced_with: newName,
                               replace_exercise_id: exerciseId } : e) }
        : st.session,
    })),
  setSessionNotes: (notes) =>
    set((st) => (st.session ? { session: { ...st.session, notes } } : st)),
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
