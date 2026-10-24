// 训练方式详情页：五维度直改（走统一修改协议，不暗中重排计划）+ 版本历史 + 两版对比
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import {
  Button, Card, ErrorBox, Input, Select, Spinner, SubHeader, Tag,
} from '../components/Bits'
import { useApp } from '../store'
import { ApproachRevision, ApproachView } from '../types'

const STRUCTURE_LABEL: Record<string, string> = {
  full_body: '全身', upper_lower: '上下肢分化', ppl: '推拉腿分化',
  circuit: '循环训练', custom: '自定义',
}
const INTENSITY_LABEL: Record<string, string> = {
  linear: '线性进阶', rpe_based: 'RPE 驱动', periodized: '周期化', flexible: '灵活进阶',
}

const STRUCTURES: [string, string][] = [
  ['full_body', '全身'], ['upper_lower', '上下肢分化'], ['ppl', '推拉腿分化'],
  ['circuit', '循环训练'], ['custom', '自定义'],
]
const INTENSITIES: [string, string][] = [
  ['linear', '线性进阶'], ['rpe_based', 'RPE 驱动'], ['periodized', '周期化'], ['flexible', '灵活进阶'],
]

export default function MineApproach() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [view, setView] = useState<ApproachView | null>(null)
  const [revisions, setRevisions] = useState<ApproachRevision[] | null>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [comparePicks, setComparePicks] = useState<number[]>([])

  const load = useCallback(() => {
    api.approach(uid).then(setView).catch(() => setView({ initialized: false }))
    api.revisions(uid).then((r) => setRevisions(r.revisions)).catch(() => setRevisions([]))
  }, [uid])
  useEffect(() => { load() }, [load])

  if (!view) return <Spinner />

  const a = view.initialized ? view.approach! : null

  return (
    <div className="mx-auto w-full max-w-3xl">
      <SubHeader title="我的训练方式" sub={a ? `当前 v${a.revision} · 修改会记录新版本` : '尚未初始化'}
                 onBack={() => navigate('/mine')} />

      {note && (
        <p className="mb-3 rounded-xl bg-accent-soft px-3.5 py-2.5 text-center text-[13px] text-accent-deep">
          {note}
        </p>
      )}
      {error && <div className="mb-3"><ErrorBox message={error} /></div>}

      {!a ? (
        <div className="card">
          <p className="text-sm leading-relaxed text-muted">
            还没有「我的训练方式」——它记录你的结构/强度/动作选择/饮食/恢复/偏好，
            是 AI 教练给出建议的依据。可以从当前计划一键初始化。
          </p>
          <Button block className="mt-3"
                  onClick={() => api.initApproach(uid).then(() => load()).catch((e: ApiError) => setError(e.message))}>
            从当前计划初始化
          </Button>
        </div>
      ) : (
        <>
          {/* 当前概览 */}
          <div className="card">
            <div className="mb-2.5 flex items-center justify-between">
              <h2 className="text-[15px] font-semibold">当前版本</h2>
              <Tag tone="brand">v{a.revision}</Tag>
            </div>
            <p className="text-sm">
              结构：<b>{STRUCTURE_LABEL[a.structure.value] || a.structure.value}</b>
              {a.structure.note && <span className="text-muted"> · {a.structure.note}</span>}
            </p>
            <p className="mt-1 text-sm">
              强度风格：<b>{INTENSITY_LABEL[a.intensity_style.value] || a.intensity_style.value}</b>
            </p>
            {a.diet_approach.strategy || a.diet_approach.note ? (
              <p className="mt-1 text-sm">饮食方式：{a.diet_approach.strategy || a.diet_approach.note}</p>
            ) : null}
            {a.recovery_approach.note && (
              <p className="mt-1 text-sm">恢复方式：{a.recovery_approach.note}</p>
            )}
            {a.exercise_selection.length > 0 && (
              <div className="mt-2.5">
                <p className="label">动作选择（{a.exercise_selection.length} 项）</p>
                <div className="flex flex-wrap gap-1.5">
                  {a.exercise_selection.map((s) => (
                    <span key={s.exercise_id} className="tag bg-ink/5 text-muted">
                      {s.exercise_id}
                      {s.status !== 'active' && <b className="ml-1 text-accent-deep">{s.status}</b>}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <ApproachEditor uid={uid} view={view} onSaved={load} note={setNote} />

          {/* 版本历史（次级信息，勾选两版对比） */}
          <Card title={`版本历史（${revisions?.length ?? 0}）`} className="mt-4"
                sub="勾选两个版本可对比各维度差异；历史版本随时可恢复，不把选择永久固定">
            <ul className="space-y-2">
              {(revisions || []).map((r) => (
                <li key={r.revision} className="rounded-xl border border-line bg-canvas p-3 text-xs leading-relaxed">
                  <div className="flex items-center justify-between gap-2">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" className="size-4 accent-[#3D5A26]"
                             checked={comparePicks.includes(r.revision)}
                             disabled={comparePicks.length === 2 && !comparePicks.includes(r.revision)}
                             onChange={() => setComparePicks((p) =>
                               p.includes(r.revision) ? p.filter((x) => x !== r.revision)
                                 : p.length < 2 ? [...p, r.revision] : p)} />
                      <b className="nums text-sm">v{r.revision}</b>
                      <span className="text-muted">
                        · {r.initiator === 'system_migration' ? '初始化' : r.initiator === 'ai' ? 'AI 建议' : '本人修改'}
                      </span>
                    </label>
                    <span className="shrink-0 text-faint">{r.created_at.slice(0, 10)}</span>
                  </div>
                  <p className="mt-1 text-muted">{r.reason}</p>
                  {r.revision !== a.revision && (
                    <button className="mt-1.5 font-medium text-accent-deep hover:underline"
                            onClick={() => api.restoreRevision(uid, r.revision, `恢复到 v${r.revision}`)
                              .then(() => { setNote(`已恢复 v${r.revision} 为最新版本`); load() })
                              .catch((e: ApiError) => setError(e.message))}>
                      恢复此版本
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {comparePicks.length === 2 && <ApproachCompare uid={uid} picks={comparePicks} />}
          </Card>

          <p className="mt-4 px-1 text-xs leading-relaxed text-muted">
            直接修改结构/强度/饮食/恢复/偏好——每次修改记录版本，可随时恢复；
            <b className="text-ink">计划不会因此被自动重排</b>，需要的话去「AI 教练」商量确认。
          </p>
        </>
      )}
    </div>
  )
}

/* ---------------- 训练方式编辑器（五维度直改，走统一修改协议） ---------------- */

function ApproachEditor({ uid, view, onSaved, note }: {
  uid: string; view: ApproachView; onSaved: () => void; note: (msg: string) => void
}) {
  const a = view.approach!
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
        uid, 'approach', ops, '在「我的训练方式」页直接修改',
        { approach_revision: a.revision })
      setMsg(`已保存为 v${r.approach_revision}`)
      note(`训练方式已更新为 v${r.approach_revision}`)
      onSaved()
    } catch (e) {
      const err = e as ApiError
      setError({ message: err.message, details: err.details })
    } finally { setSaving(false) }
  }

  return (
    <div className="card mt-4">
      <h2 className="mb-3 text-[15px] font-semibold">编辑</h2>
      {error && <div className="mb-3"><ErrorBox message={error.message} details={error.details} /></div>}
      <div className="space-y-3">
        <div className="grid grid-cols-[88px_1fr] items-center gap-2.5">
          <span className="text-[13px] text-muted">结构</span>
          <Select value={structure} onChange={(e) => setStructure(e.target.value)}>
            {STRUCTURES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <Input value={structureNote} placeholder="结构备注（如：时间紧改成上下肢）"
               onChange={(e) => setStructureNote(e.target.value)} />
        <div className="grid grid-cols-[88px_1fr] items-center gap-2.5">
          <span className="text-[13px] text-muted">强度风格</span>
          <Select value={intensity} onChange={(e) => setIntensity(e.target.value)}>
            {INTENSITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </div>
        <Input value={diet} placeholder="饮食方式（如：灵活饮食，不精确计热量）"
               onChange={(e) => setDiet(e.target.value)} />
        <Input value={recovery} placeholder="恢复方式备注"
               onChange={(e) => setRecovery(e.target.value)} />
        <Input value={deload} placeholder="卸载策略（如：连续两周无进步就减半周）"
               onChange={(e) => setDeload(e.target.value)} />
        <div className="grid grid-cols-2 gap-2.5">
          <Input value={liked} placeholder="喜欢的（顿号分隔）"
                 onChange={(e) => setLiked(e.target.value)} />
          <Input value={disliked} placeholder="不喜欢的（顿号分隔）"
                 onChange={(e) => setDisliked(e.target.value)} />
        </div>
        <Button block disabled={saving} onClick={save}>
          {saving ? '保存中…' : '保存修改（记录为新版本）'}
        </Button>
        {msg && <p className="text-center text-xs text-accent-deep">{msg}</p>}
      </div>
    </div>
  )
}

/* ---------------- 两版对比（维度级） ---------------- */

function ApproachCompare({ uid, picks }: { uid: string; picks: number[] }) {
  const [data, setData] = useState<[ApproachView['approach'], ApproachView['approach']] | null>(null)
  useEffect(() => {
    Promise.all(picks.map((r) => api.approachRevision(uid, r)))
      .then((rs) => setData([rs[0].content, rs[1].content]))
      .catch(() => setData(null))
  }, [uid, picks])
  if (!data) return <Spinner label="加载对比…" />
  const [a, b] = data
  const rows: [string, string, string][] = [
    ['结构', a!.structure.value, b!.structure.value],
    ['强度风格', a!.intensity_style.value, b!.intensity_style.value],
    ['动作选择数', String(a!.exercise_selection.length), String(b!.exercise_selection.length)],
    ['饮食方式', a!.diet_approach.strategy || a!.diet_approach.note || '—',
                 b!.diet_approach.strategy || b!.diet_approach.note || '—'],
    ['恢复方式', a!.recovery_approach.note || '—', b!.recovery_approach.note || '—'],
    ['喜欢', a!.preferences.liked.join('、') || '—', b!.preferences.liked.join('、') || '—'],
    ['不喜欢', a!.preferences.disliked.join('、') || '—', b!.preferences.disliked.join('、') || '—'],
  ]
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-line">
      <p className="nums border-b border-line bg-canvas px-3 py-2 text-xs font-semibold">
        v{picks[0]} ↔ v{picks[1]} 对比
      </p>
      <table className="w-full text-xs">
        <tbody>
          {rows.map(([label, va, vb]) => (
            <tr key={label} className={va !== vb ? 'bg-amber-50 text-amber-800' : 'text-muted'}>
              <td className="w-16 py-2 pl-3 pr-1 align-top">{label}</td>
              <td className="py-2 pr-2 align-top">{va}</td>
              <td className="py-2 pr-3 align-top">{vb}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line bg-canvas px-3 py-2 text-2xs text-faint">
        差异行高亮；历史版本随时可恢复，不把选择永久固定
      </p>
    </div>
  )
}
