import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Card, Empty, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { discardFailed, exportFailedJSON, failedItems, retryFailed } from '../offline'
import { useApp } from '../store'
import { ApproachRevision, ApproachView, Profile, Trial } from '../types'

const STRUCTURE_LABEL: Record<string, string> = {
  full_body: '全身', upper_lower: '上下肢分化', ppl: '推拉腿分化',
  circuit: '循环训练', custom: '自定义',
}

export default function Mine() {
  const uid = useApp((s) => s.uid)
  const setUid = useApp((s) => s.setUid)
  const navigate = useNavigate()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [summary, setSummary] = useState('')
  const [view, setView] = useState<ApproachView | null>(null)
  const [revisions, setRevisions] = useState<ApproachRevision[] | null>(null)
  const [trials, setTrials] = useState<Trial[] | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [showRevisions, setShowRevisions] = useState(false)

  const load = useCallback(() => {
    api.profile(uid).then((r) => { setProfile(r.profile); setSummary(r.summary) })
      .catch((e) => setError(e.message))
    api.approach(uid).then(setView).catch(() => setView({ initialized: false }))
    api.revisions(uid).then((r) => setRevisions(r.revisions)).catch(() => setRevisions([]))
    api.trials(uid).then((r) => setTrials(r.trials)).catch(() => setTrials([]))
  }, [uid])
  useEffect(() => { load() }, [load])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!profile) return <Spinner />

  const exportData = () => {
    const blob = new Blob([JSON.stringify({ profile, approach: view, trials, exported_at: new Date().toISOString() }, null, 2)],
      { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `fitness-coach-${uid}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="我的" sub={`用户 ${uid}`} />

      <Card title="档案">
        <p className="whitespace-pre-wrap text-sm text-neutral-300">{summary}</p>
      </Card>

      <Card title="我的训练方式"
            right={view?.initialized
              ? <Tag tone="green">v{view.approach!.revision}</Tag>
              : undefined}>
        {!view?.initialized ? (
          <div>
            <Empty>还没建立「我的训练方式」——从现有计划一键初始化。</Empty>
            <button className="btn-ghost w-full"
                    onClick={() => api.initApproach(uid).then(() => load()).catch((e) => setNote(e.message))}>
              从当前计划初始化
            </button>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            <p>结构：<b>{STRUCTURE_LABEL[view.approach!.structure.value]}</b>
              {view.approach!.structure.note && <span className="text-neutral-500"> · {view.approach!.structure.note}</span>}
            </p>
            <p>强度风格：{view.approach!.intensity_style.value}</p>
            {view.approach!.exercise_selection.length > 0 && (
              <div>
                <p className="label">动作选择（{view.approach!.exercise_selection.length} 项）</p>
                <div className="flex flex-wrap gap-1.5">
                  {view.approach!.exercise_selection.map((s) => (
                    <span key={s.exercise_id} className="tag bg-neutral-800 text-neutral-300">
                      {s.exercise_id}
                      {s.status !== 'active' && <b className="ml-1 text-accent">{s.status}</b>}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {(view.approach!.diet_approach.strategy || view.approach!.diet_approach.note) && (
              <p>饮食方式：{view.approach!.diet_approach.strategy || view.approach!.diet_approach.note}</p>
            )}
            {view.referenced?.active_trial && (
              <p className="text-xs text-sky-300">进行中的尝试：{view.referenced.active_trial.change_desc}</p>
            )}
            {view.referenced?.active_plan && view.referenced.active_plan.approach_revision != null
              && view.referenced.active_plan.approach_revision < view.approach!.revision && (
              <p className="text-xs text-amber-300">
                当前计划基于训练方式 v{view.referenced.active_plan.approach_revision}，落后于最新 v{view.approach!.revision}；
                去 AI 教练页商量是否重排。
              </p>
            )}
            <button className="btn-ghost w-full !py-2 text-xs"
                    onClick={() => setShowRevisions((s) => !s)}>
              {showRevisions ? '收起版本历史' : `版本历史（${revisions?.length ?? 0}）`}
            </button>
            {showRevisions && (
              <ul className="space-y-1.5">
                {(revisions || []).map((r) => (
                  <li key={r.revision} className="rounded-lg bg-neutral-800/60 p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span><b>v{r.revision}</b> · {r.initiator === 'system_migration' ? '初始化' : r.initiator === 'ai' ? 'AI 建议' : '本人修改'}</span>
                      <span className="text-neutral-500">{r.created_at.slice(0, 10)}</span>
                    </div>
                    <p className="mt-0.5 text-neutral-400">{r.reason}</p>
                    {r.revision !== view.approach!.revision && (
                      <button className="mt-1 text-accent underline"
                              onClick={() => api.restoreRevision(uid, r.revision, `恢复到 v${r.revision}`)
                                .then(() => { setNote(`已恢复 v${r.revision} 为最新版本`); load() })
                                .catch((e: ApiError) => setNote(e.message))}>
                        恢复此版本
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>

      {view?.initialized && <ApproachEditor uid={uid} view={view} onSaved={load} />}

      <FailedSyncCard onChanged={() => load()} />

      {note && <p className="text-center text-xs text-accent">{note}</p>}

      <Card title="个人尝试">
        {!trials?.length ? <Empty>暂无记录（可在 AI 教练页发起一次有边界的尝试）</Empty> : (
          <ul className="space-y-2 text-sm">
            {trials.map((t) => (
              <li key={t.id} className="rounded-lg bg-neutral-800/60 p-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{t.change_desc}</span>
                  {t.status === 'active'
                    ? <Tag tone={t.due_review ? 'amber' : 'blue'}>{t.due_review ? '该复盘了' : '进行中'}</Tag>
                    : <Tag tone="neutral">{({ keep: '保留', stop: '停止', adjust: '调整' } as Record<string, string>)[t.decision || ''] || t.decision}</Tag>}
                </div>
                <p className="mt-0.5 text-xs text-neutral-500">观察：{t.observe} · 停止条件：{t.stop_rule}</p>
                {t.outcome && <p className="mt-0.5 text-xs text-neutral-400">结果：{t.outcome}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="数据与设置">
        <div className="space-y-2">
          <button className="btn-ghost w-full !py-2 text-sm" onClick={exportData}>导出我的数据（JSON）</button>
          <div className="flex gap-2">
            <input className="input text-sm" placeholder="切换到其他用户 ID"
                   onKeyDown={(e) => {
                     if (e.key === 'Enter') {
                       const v = (e.target as HTMLInputElement).value.trim()
                       if (v) { setUid(v); navigate('/today') }
                     } }} />
            <button className="btn-ghost shrink-0 text-sm"
                    onClick={() => { setUid(''); navigate('/welcome') }}>新用户建档</button>
          </div>
          <div>
            <label className="label">访问令牌（仅当服务设置了 API_ACCESS_TOKEN 时需要）</label>
            <div className="flex gap-2">
              <input className="input text-sm" type="password" id="fc-token-input"
                     defaultValue={localStorage.getItem('fc-access-token') || ''}
                     placeholder="X-Access-Token" />
              <button className="btn-ghost shrink-0 text-sm"
                      onClick={() => {
                        const v = (document.getElementById('fc-token-input') as HTMLInputElement).value.trim()
                        if (v) localStorage.setItem('fc-access-token', v)
                        else localStorage.removeItem('fc-access-token')
                        setNote(v ? '访问令牌已保存，后续请求自动携带' : '访问令牌已清除')
                      }}>保存</button>
            </div>
          </div>
        </div>
      </Card>

      <p className="px-2 pb-2 text-[11px] leading-relaxed text-neutral-600">
        本系统不提供医疗诊断或治疗建议；涉及伤病、疾病、孕期、用药的内容默认隔离并建议咨询专业人员。
        视频估计与模型推断不构成医学结论。
      </p>
    </div>
  )
}


// ---- P1-3：训练方式编辑器（五维度直改，走统一修改协议；不暗中重排计划）----
const STRUCTURES: [string, string][] = [
  ['full_body', '全身'], ['upper_lower', '上下肢分化'], ['ppl', '推拉腿分化'],
  ['circuit', '循环训练'], ['custom', '自定义'],
]
const INTENSITIES: [string, string][] = [
  ['linear', '线性进阶'], ['rpe_based', 'RPE 驱动'], ['periodized', '周期化'], ['flexible', '灵活进阶'],
]

function ApproachEditor({ uid, view, onSaved }: {
  uid: string; view: ApproachView; onSaved: () => void
}) {
  const a = view.approach!
  const [open, setOpen] = useState(false)
  const [structure, setStructure] = useState(a.structure.value)
  const [structureNote, setStructureNote] = useState(a.structure.note || '')
  const [intensity, setIntensity] = useState(a.intensity_style.value)
  const [diet, setDiet] = useState(a.diet_approach.strategy || a.diet_approach.note || '')
  const [recovery, setRecovery] = useState(a.recovery_approach.note || '')
  const [deload, setDeload] = useState(a.recovery_approach.deload_policy || '')
  const [liked, setLiked] = useState(a.preferences.liked.join('、'))
  const [disliked, setDisliked] = useState(a.preferences.disliked.join('、'))
  const [error, setError] = useState<{ message: string; details?: string[] } | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const save = async () => {
    setSaving(true); setError(null); setMsg('')
    const ops: { op: string; dimension: string; value: Record<string, unknown> }[] = []
    if (structure !== a.structure.value || structureNote !== (a.structure.note || '')) {
      ops.push({ op: 'set_dimension', dimension: 'structure',
                 value: { value: structure, note: structureNote } })
    }
    if (intensity !== a.intensity_style.value) {
      ops.push({ op: 'set_dimension', dimension: 'intensity_style', value: { value: intensity } })
    }
    if (diet !== (a.diet_approach.strategy || a.diet_approach.note || '')) {
      ops.push({ op: 'set_dimension', dimension: 'diet_approach', value: { strategy: diet } })
    }
    if (recovery !== (a.recovery_approach.note || '')
        || deload !== (a.recovery_approach.deload_policy || '')) {
      ops.push({ op: 'set_dimension', dimension: 'recovery_approach',
                 value: { note: recovery, deload_policy: deload } })
    }
    if (liked !== a.preferences.liked.join('、') || disliked !== a.preferences.disliked.join('、')) {
      ops.push({ op: 'set_dimension', dimension: 'preferences',
                 value: { liked: liked.split(/[、,，]/).map((x) => x.trim()).filter(Boolean),
                          disliked: disliked.split(/[、,，]/).map((x) => x.trim()).filter(Boolean) } })
    }
    if (!ops.length) { setMsg('没有修改'); setSaving(false); return }
    try {
      const r = await api.submitChange<{ approach_revision: number }>(
        uid, 'approach', ops, '在「我的」页直接修改',
        { approach_revision: a.revision })
      setMsg(`已保存为 v${r.approach_revision}`)
      onSaved()
    } catch (e) {
      const err = e as ApiError
      setError({ message: err.message, details: err.details })
    } finally { setSaving(false) }
  }

  return (
    <Card title="编辑我的训练方式"
          right={<button className="text-xs text-accent underline"
                         onClick={() => setOpen((o) => !o)}>{open ? '收起' : '展开编辑'}</button>}>
      {!open ? (
        <p className="text-xs text-neutral-500">
          直接修改结构/强度/饮食/恢复/偏好——每次修改记录版本，可随时恢复；
          <b className="text-neutral-400">计划不会因此被自动重排</b>，
          需要的话去「AI 教练」商量确认。
        </p>
      ) : (
        <div className="space-y-2.5">
          {error && <ErrorBox message={error.message} details={error.details} />}
          <div className="grid grid-cols-[80px_1fr] items-center gap-2">
            <span className="text-xs text-neutral-400">结构</span>
            <select className="input !py-1.5 text-sm" value={structure}
                    onChange={(e) => setStructure(e.target.value)}>
              {STRUCTURES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <input className="input text-xs" value={structureNote} placeholder="结构备注（如：时间紧改成上下肢）"
                 onChange={(e) => setStructureNote(e.target.value)} />
          <div className="grid grid-cols-[80px_1fr] items-center gap-2">
            <span className="text-xs text-neutral-400">强度风格</span>
            <select className="input !py-1.5 text-sm" value={intensity}
                    onChange={(e) => setIntensity(e.target.value)}>
              {INTENSITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <input className="input text-xs" value={diet} placeholder="饮食方式（如：灵活饮食，不精确计热量）"
                 onChange={(e) => setDiet(e.target.value)} />
          <input className="input text-xs" value={recovery} placeholder="恢复方式备注"
                 onChange={(e) => setRecovery(e.target.value)} />
          <input className="input text-xs" value={deload} placeholder="卸载策略（如：连续两周无进步就减半周）"
                 onChange={(e) => setDeload(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <input className="input text-xs" value={liked} placeholder="喜欢的（顿号分隔）"
                   onChange={(e) => setLiked(e.target.value)} />
            <input className="input text-xs" value={disliked} placeholder="不喜欢的（顿号分隔）"
                   onChange={(e) => setDisliked(e.target.value)} />
          </div>
          <button className="btn-primary w-full" disabled={saving} onClick={save}>
            {saving ? '保存中…' : '保存修改（记录为新版本）'}
          </button>
          {msg && <p className="text-center text-xs text-accent">{msg}</p>}
        </div>
      )}
    </Card>
  )
}

// ---- P0-2：同步失败记录（可重试/丢弃/导出，绝不静默删除）----
function FailedSyncCard({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof failedItems>> | null>(null)
  const [msg, setMsg] = useState('')
  const refresh = useCallback(() => { failedItems().then(setItems) }, [])
  useEffect(() => { refresh() }, [refresh])

  if (items === null || items.length === 0) return null
  return (
    <Card title={<span><Tag tone="amber">同步失败</Tag> <span className="ml-1">{items.length} 条待处理</span></span>}>
      <p className="mb-2 text-xs text-neutral-500">
        这些训练记录因数据校验未通过而未能同步，已保留在本机——可修正后重试、导出备份或丢弃。
      </p>
      <ul className="space-y-2">
        {items.map((f) => (
          <li key={f.id} className="rounded-lg bg-neutral-800/60 p-2 text-xs">
            <p className="text-neutral-300">{new Date(f.at).toLocaleString('zh-CN')} · {f.type}</p>
            <p className="mt-0.5 text-red-400">失败原因：{f.error}</p>
            <div className="mt-1 flex gap-2">
              <button className="text-accent underline"
                      onClick={async () => { await discardFailed(f.id); refresh() }}>丢弃这条</button>
            </div>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex gap-2">
        <button className="btn-ghost flex-1 !py-2 text-xs"
                onClick={async () => {
                  const r = await retryFailed(async (u, t, d, sid) => {
                    await api.saveCheckin(u, t, d, sid)
                  })
                  setMsg(`重试完成：成功 ${r.synced}，仍失败 ${r.failed}，待网络 ${r.remaining}`)
                  refresh(); onChanged()
                }}>全部重试</button>
        <button className="btn-ghost flex-1 !py-2 text-xs"
                onClick={async () => {
                  const blob = new Blob([await exportFailedJSON()], { type: 'application/json' })
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(blob)
                  a.download = `fitness-coach-sync-failed-${Date.now()}.json`
                  a.click(); URL.revokeObjectURL(a.href)
                }}>导出失败记录</button>
      </div>
      {msg && <p className="mt-2 text-center text-xs text-accent">{msg}</p>}
    </Card>
  )
}
