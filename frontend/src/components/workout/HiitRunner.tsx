import { useEffect, useRef, useState } from 'react'
import { Check, Flag, Pause, Play, SkipForward } from 'lucide-react'
import { Button, Input } from '../Bits'
import type { LoggedSet, SessionEntry } from '../../store'
import type { HiitBlock, HiitPlan, HiitRun } from '../../types'

const fmt = (s: number) =>
  `${String(Math.floor(Math.max(0, s) / 60)).padStart(2, '0')}:${String(Math.max(0, s) % 60).padStart(2, '0')}`

export interface HiitTransition {
  run: HiitRun
  result?: LoggedSet
}

export function createHiitRun(now = Date.now()): HiitRun {
  return {
    status: 'running_work', blockIdx: 0, round: 1, phase: 'work',
    phaseStartTs: now, pausedTotalMs: 0, pausedAt: null,
    workDone: 0, restDone: 0, completedRounds: 0, skipped: [], endedEarly: false,
  }
}

export function hiitPhaseElapsed(run: HiitRun, now = Date.now()) {
  const end = run.pausedAt ?? now
  return Math.max(0, Math.floor((end - run.phaseStartTs - run.pausedTotalMs) / 1000))
}

function phaseDuration(plan: HiitPlan, run: HiitRun) {
  const block = plan.blocks[run.blockIdx]
  return run.phase === 'work' ? block?.work_seconds ?? 0 : block?.rest_seconds ?? 0
}

function isActive(run: HiitRun) {
  return run.status === 'running_work' || run.status === 'running_rest'
}

export function needsHiitConfirmation(run: HiitRun, plan: HiitPlan, now: number, tickGap: number) {
  const duration = phaseDuration(plan, run)
  const elapsed = hiitPhaseElapsed(run, now)
  return isActive(run) && duration > 0 && elapsed >= duration
    && (tickGap > 2000 || elapsed > duration + 1)
}

export function pauseHiit(run: HiitRun, now = Date.now()): HiitRun {
  return isActive(run) ? { ...run, status: 'paused', pausedAt: now } : run
}

export function resumeHiit(run: HiitRun, now = Date.now()): HiitRun {
  if (run.status !== 'paused' || run.pendingPhaseConfirm != null) return run
  return { ...run,
    status: run.phase === 'work' ? 'running_work' : 'running_rest',
    pausedTotalMs: run.pausedTotalMs + Math.max(0, now - (run.pausedAt ?? now)),
    pausedAt: null }
}

export function restartHiitPhase(run: HiitRun, now = Date.now()): HiitRun {
  return { ...run, status: run.phase === 'work' ? 'running_work' : 'running_rest',
    phaseStartTs: now, pausedTotalMs: 0, pausedAt: null, pendingPhaseConfirm: undefined }
}

function buildHiitLog(plan: HiitPlan, run: HiitRun, now: number,
                      endedEarly: boolean, reason: string): LoggedSet {
  return {
    type: 'duration', duration_seconds: run.workDone, warmup: false,
    hiit: {
      name: plan.name, blocks: plan.blocks,
      planned_rounds: plan.blocks.reduce((n, b) => n + b.rounds, 0),
      completed_rounds: run.completedRounds,
      work_seconds_done: run.workDone,
      rest_seconds_done: run.restDone,
      skipped: run.skipped.map((s) => ({ ...s })),
      ended_early: endedEarly,
      end_reason: reason,
    },
    at: new Date(now).toISOString(),
  }
}

function nextRound(plan: HiitPlan, run: HiitRun, now: number): HiitTransition {
  const block = plan.blocks[run.blockIdx]
  if (!block) return { run }
  let blockIdx = run.blockIdx
  let round = run.round + 1
  if (round > block.rounds) {
    blockIdx += 1
    round = 1
  }
  const base = { ...run, blockIdx, round, phaseStartTs: now,
    pausedTotalMs: 0, pausedAt: null, pendingPhaseConfirm: undefined }
  if (blockIdx >= plan.blocks.length) {
    const completed = { ...base, status: 'completed' as const }
    const reason = completed.skipped.length ? '全部计划完成（含跳过）' : '全部计划完成'
    return { run: completed,
      result: buildHiitLog(plan, completed, now, false, reason) }
  }
  return { run: { ...base, phase: 'work', status: 'running_work' } }
}

export function completeHiitPhase(plan: HiitPlan, run: HiitRun, now = Date.now()): HiitTransition {
  if (!isActive(run) && run.status !== 'paused') return { run }
  const duration = phaseDuration(plan, run)
  if (run.phase === 'work') {
    const next = { ...run, workDone: run.workDone + duration,
      completedRounds: run.completedRounds + 1,
      pausedTotalMs: 0, pausedAt: null, pendingPhaseConfirm: undefined }
    if ((plan.blocks[run.blockIdx]?.rest_seconds ?? 0) > 0) {
      return { run: { ...next, phase: 'rest', status: 'running_rest', phaseStartTs: now } }
    }
    return nextRound(plan, next, now)
  }
  return nextRound(plan, { ...run, restDone: run.restDone + duration,
    pausedTotalMs: 0, pausedAt: null, pendingPhaseConfirm: undefined }, now)
}

export function skipHiitPhase(plan: HiitPlan, run: HiitRun, now = Date.now()): HiitTransition {
  if (!isActive(run)) return { run }
  if (run.phase === 'rest') return nextRound(plan, run, now)
  return nextRound(plan, {
    ...run,
    skipped: [...run.skipped, { block: run.blockIdx, round: run.round }],
  }, now)
}

export function stopHiitEarly(plan: HiitPlan, run: HiitRun, now = Date.now()): HiitTransition {
  if (run.status === 'completed' || run.status === 'stopped_early') return { run }
  const partial = Math.min(phaseDuration(plan, run), hiitPhaseElapsed(run, now))
  const next = { ...run,
    workDone: run.workDone + (run.phase === 'work' ? partial : 0),
    restDone: run.restDone + (run.phase === 'rest' ? partial : 0),
    status: 'stopped_early' as const, endedEarly: true, endReason: '用户提前结束',
    phaseStartTs: now, pausedAt: null, pendingPhaseConfirm: undefined }
  return { run: next, result: buildHiitLog(plan, next, now, true, '用户提前结束') }
}

export default function HiitRunner({ idx, entry, onUpdate, onLog }: {
  idx: number
  entry: SessionEntry
  onUpdate: (patch: Partial<SessionEntry>) => void
  onLog: (idx: number, s: LoggedSet) => void
}) {
  const plan = entry.hiitPlan
  const run = entry.hiitRun
  const [now, setNow] = useState(Date.now())
  const lastTick = useRef(Date.now())
  const handledPhase = useRef('')
  const loggedRef = useRef(entry.logged.some((l) => 'hiit' in l && !!l.hiit))

  useEffect(() => {
    loggedRef.current = entry.logged.some((l) => 'hiit' in l && !!l.hiit)
  }, [entry.logged])

  useEffect(() => {
    if (!run || !isActive(run)) return
    const h = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(h)
  }, [run?.status])

  useEffect(() => {
    const update = () => setNow(Date.now())
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])

  useEffect(() => {
    if (!plan || !run || !isActive(run)) return
    const gap = Math.max(0, now - lastTick.current)
    lastTick.current = now
    const elapsed = hiitPhaseElapsed(run, now)
    const duration = phaseDuration(plan, run)
    if (elapsed < duration) return
    const key = `${run.phaseStartTs}:${run.blockIdx}:${run.round}:${run.phase}`
    if (handledPhase.current === key) return
    handledPhase.current = key
    if (needsHiitConfirmation(run, plan, now, gap)) {
      onUpdate({ hiitRun: { ...run, status: 'paused', pausedAt: now,
        pendingPhaseConfirm: elapsed } })
      return
    }
    commit(completeHiitPhase(plan, run, now))
    // 阶段推进只由时间戳触发；run 更新会等待下一次 now tick。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [now])

  if (!plan || !run) return null

  function commit(transition: HiitTransition) {
    lastTick.current = Date.now()
    onUpdate({ hiitRun: transition.run })
    if (transition.result && !loggedRef.current) {
      loggedRef.current = true
      onLog(idx, transition.result)
    }
  }

  const block: HiitBlock | undefined = plan.blocks[run.blockIdx]
  const phaseLeft = Math.max(0, phaseDuration(plan, run) - hiitPhaseElapsed(run, now))
  const statusText = {
    running_work: '工作阶段', running_rest: '休息阶段',
    paused: '已暂停', completed: '已完成', stopped_early: '已提前结束',
  }[run.status]

  return (
    <div className="border-t border-line bg-canvas/60 px-4 pb-4 pt-3">
      <div className="rounded-xl bg-night p-4 text-center text-white">
        <p className="text-2xs text-white/60">
          HIIT · {plan.name}
          {run.status !== 'completed' && ` · 第 ${run.round}/${block?.rounds ?? '—'} 轮（块 ${run.blockIdx + 1}/${plan.blocks.length}）`}
        </p>
        <p className="mt-1 text-lg font-bold">{block?.name ?? '—'}</p>
        <p className="nums mt-2 text-4xl font-bold tabular-nums">{fmt(phaseLeft)}</p>
        <p className="mt-1 text-2xs text-white/60">
          {statusText} · 已完成 {run.completedRounds} 轮 ·
          工作 {fmt(run.workDone)} / 休息 {fmt(run.restDone)}
        </p>
        {run.status === 'running_rest' && (
          <p className="mt-1 text-2xs text-accent">休息结束后进入下一轮工作</p>
        )}
        {run.status === 'running_work' && (
          <p className="mt-1 text-2xs text-white/50">
            下一阶段：{(block?.rest_seconds ?? 0) > 0
              ? `休息 ${block?.rest_seconds}s` : '下一轮'}
          </p>
        )}
      </div>

      {run.pendingPhaseConfirm != null && (
        <div className="mt-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs leading-relaxed text-amber-800">
          后台期间可能错过了阶段切换（已经过约 {fmt(run.pendingPhaseConfirm)}）。
          为避免把未执行的阶段记成完成，请确认实际情况：
          <div className="mt-2 flex gap-2">
            <Button className="text-xs" onClick={() => {
              commit(completeHiitPhase(plan, run, Date.now()))
              setNow(Date.now())
            }}>
              本阶段已完成
            </Button>
            <Button variant="ghost" className="text-xs" onClick={() => {
              onUpdate({ hiitRun: restartHiitPhase(run, Date.now()) })
              lastTick.current = Date.now()
              setNow(Date.now())
            }}>
              本阶段重新计时
            </Button>
          </div>
        </div>
      )}

      {run.status === 'paused' && run.pendingPhaseConfirm == null ? (
        <div className="mt-2.5 flex gap-2">
          <button className="btn-primary btn flex-1" onClick={() => {
            const at = Date.now()
            lastTick.current = at
            onUpdate({ hiitRun: resumeHiit(run, at) })
            setNow(at)
          }}>
            <Play size={15} /> 恢复
          </button>
          <button className="btn-ghost btn flex-1 !text-red-600"
                  onClick={() => commit(stopHiitEarly(plan, run, Date.now()))}>
            <Flag size={15} /> 提前结束
          </button>
        </div>
      ) : run.status === 'completed' || run.status === 'stopped_early' ? (
        <p className="mt-2.5 rounded-xl bg-emerald-50 p-2.5 text-xs leading-relaxed text-emerald-700">
          <Check size={13} className="mr-1 inline" />
          执行结果已记录到本会话（实际完成 {run.completedRounds} 轮
          {run.skipped.length ? ` · 跳过 ${run.skipped.length} 轮` : ''}
          {run.endedEarly ? ` · ${run.endReason}` : ''}），未执行轮次不计完成。
        </p>
      ) : run.pendingPhaseConfirm == null ? (
        <div className="mt-2.5 space-y-2">
          <div className="flex gap-2">
            <button className="btn-soft btn flex-1"
                    onClick={() => onUpdate({ hiitRun: pauseHiit(run, Date.now()) })}>
              <Pause size={15} /> 暂停
            </button>
            <button className="btn-ghost btn flex-1"
                    onClick={() => commit(skipHiitPhase(plan, run, Date.now()))}>
              <SkipForward size={15} /> 跳过阶段
            </button>
            <button className="btn-ghost btn flex-1 !text-red-600"
                    onClick={() => commit(stopHiitEarly(plan, run, Date.now()))}>
              <Flag size={15} /> 提前结束
            </button>
          </div>
          <p className="text-center text-xs text-muted">
            计划共 {plan.blocks.reduce((n, b) => n + b.rounds, 0)} 轮
          </p>
        </div>
      ) : null}
      <p className="mt-2 text-2xs leading-relaxed text-faint">
        状态随会话持久化；后台跨过阶段时需确认，不自动补记。结果随会话保存。
      </p>
    </div>
  )
}

export function HiitPlanner({ onStart }: {
  onStart: (plan: HiitPlan) => void
}) {
  const [name, setName] = useState('四轮间歇训练')
  const [exerciseName, setExerciseName] = useState('开合跳')
  const [work, setWork] = useState('30')
  const [rest, setRest] = useState('30')
  const [rounds, setRounds] = useState('4')
  const workSeconds = Number(work)
  const restSeconds = Number(rest)
  const roundCount = Number(rounds)
  const valid = !!name.trim() && !!exerciseName.trim()
    && Number.isInteger(workSeconds) && workSeconds > 0 && workSeconds <= 86400
    && Number.isInteger(restSeconds) && restSeconds >= 0 && restSeconds <= 86400
    && Number.isInteger(roundCount) && roundCount >= 1 && roundCount <= 99
    && workSeconds * roundCount <= 86400 && restSeconds * roundCount <= 86400

  return (
    <div className="space-y-2 border-t border-line bg-canvas/60 px-4 pb-4 pt-3">
      <p className="text-sm font-semibold">编排间歇训练</p>
      <label className="block"><span className="mb-1 block text-xs text-muted">名称</span>
        <Input value={name} onChange={(e) => setName(e.target.value)} /></label>
      <div className="grid grid-cols-2 gap-2">
        <label><span className="mb-1 block text-xs text-muted">动作名</span>
          <Input value={exerciseName} onChange={(e) => setExerciseName(e.target.value)} /></label>
        <label><span className="mb-1 block text-xs text-muted">轮次</span>
          <Input inputMode="numeric" value={rounds} onChange={(e) => setRounds(e.target.value)} /></label>
        <label><span className="mb-1 block text-xs text-muted">工作（秒）</span>
          <Input inputMode="numeric" value={work} onChange={(e) => setWork(e.target.value)} /></label>
        <label><span className="mb-1 block text-xs text-muted">休息（秒）</span>
          <Input inputMode="numeric" value={rest} onChange={(e) => setRest(e.target.value)} /></label>
      </div>
      <Button block disabled={!valid} onClick={() => onStart({
        name: name.trim(),
        blocks: [{ name: exerciseName.trim(), exercise_id: 'jumping_jack',
          work_seconds: workSeconds, rest_seconds: restSeconds, rounds: roundCount }],
      })}>
        开始间歇训练
      </Button>
    </div>
  )
}
