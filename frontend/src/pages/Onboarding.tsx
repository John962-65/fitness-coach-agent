import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, OnboardingResult } from '../api'
import { ErrorBox, PageHeader, Tag } from '../components/Bits'
import { useApp } from '../store'

const GOALS = [
  { id: 'fat_loss', label: '减脂' }, { id: 'muscle_gain', label: '增肌' },
  { id: 'strength', label: '力量' }, { id: 'health', label: '健康' },
  { id: 'shaping', label: '塑形' },
]

// 表单化建档（M1：建档不经过 LLM）：PAR-Q 四项必答，体检依据=用户自述文本，
// 后端同一套确定性校验；阳性自动落医疗暂停模板，如实呈现。
export default function Onboarding() {
  const setUid = useApp((s) => s.setUid)
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [uidInput, setUidInput] = useState('')
  const [error, setError] = useState<{ message: string; details?: string[] } | null>(null)
  const [result, setResult] = useState<OnboardingResult | null>(null)
  const [saving, setSaving] = useState(false)
  const uid = useApp((s) => s.uid)

  const [f, setF] = useState({
    age: '', gender: '男', height: '', weight: '',
    goal: 'muscle_gain', years: '', layoff: '0',
    location: 'gym', days: '3', minutes: '60',
    injuries: '', injuriesNone: false,
    // P0-5：健康筛查初始为"未回答"，必须由用户主动选择/填写
    heart: '', pregnancy: '', medication: '', clearance: '',
  })
  const set = (patch: Partial<typeof f>) => setF((s) => ({ ...s, ...patch }))

  const parqPositive = useMemo(() =>
    [f.heart, f.pregnancy, f.medication, f.clearance].some((v) =>
      v.trim() !== '' && v !== '无' && v !== '不适用'), [f])
  const parqRef = useRef<Record<string, HTMLInputElement | null>>({})

  const submit = async () => {
    setSaving(true); setError(null)
    // P0-5：四项筛查必须由用户主动作答；伤病必须勾选"无"或如实填写
    const parq: ['heart' | 'pregnancy' | 'medication' | 'clearance', string][] = [
      ['heart', '心血管疾病'], ['pregnancy', '怀孕/备孕'],
      ['medication', '长期用药'], ['clearance', '医生运动限制']]
    const unanswered = parq.filter(([k]) => !f[k].trim()).map(([, label]) => label)
    if (unanswered.length) {
      setError({ message: '健康筛查必须逐项作答（不做默认假设）', details: unanswered })
      setSaving(false); setStep(3)
      return
    }
    if (!f.injuriesNone && !f.injuries.trim()) {
      setError({ message: '请勾选「我没有伤病」，或填写你的伤病情况' })
      setSaving(false); setStep(2)
      return
    }
    const uid = uidInput.trim() || `web-${Date.now().toString(36)}`
    const injuries = f.injuriesNone ? []
      : f.injuries.split(/[、,，;；\n]/).map((s) => s.trim()).filter(Boolean)
    try {
      const r = await api.onboard(uid, {
        basic: { age: Number(f.age), gender: f.gender,
                 height_cm: Number(f.height), weight_kg: Number(f.weight) },
        goal: { primary: f.goal },
        experience: { training_years: Number(f.years || 0), recent_layoff_weeks: Number(f.layoff || 0) },
        resources: { location: f.location, days_per_week: Number(f.days), session_minutes: Number(f.minutes) },
        conditions: {
          injuries,
          injuries_evidence: f.injuriesNone
            ? '本人勾选确认：没有伤病（建档表单）'
            : `伤病（建档表单自述）：${f.injuries.trim()}`,
          health_screen: { heart: f.heart, pregnancy: f.pregnancy,
                           medication: f.medication, clearance: f.clearance },
          health_screen_evidence: `健康筛查（建档表单逐项作答）：心血管=${f.heart}；怀孕/备孕=${f.pregnancy}；长期用药=${f.medication}；医生运动限制=${f.clearance}`,
        },
      })
      setUid(uid)
      setResult(r)
    } catch (e) {
      const err = e as ApiError
      setError({ message: err.message, details: err.details })
    } finally { setSaving(false) }
  }

  if (result) {
    return (
      <div className="mx-auto max-w-lg space-y-4 px-4 pt-8">
        <p className="text-center text-4xl">🏋️</p>
        <h1 className="text-center text-lg font-bold">
          建档完成，定级 {result.level === 'beginner' ? '新手' : result.level === 'intermediate' ? '进阶' : '老炮'}
        </h1>
        {result.suspended ? (
          <div className="rounded-xl border border-red-900 bg-red-950/40 p-4 text-sm leading-relaxed text-red-300">
            ⏸️ 健康筛查有需要关注项，训练处方已暂停（这不是诊断）。<br />
            请先与医疗专业人员确认可以做什么运动，然后到「AI 教练」页告知医生结论，确认后恢复安排。
          </div>
        ) : (
          <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-2xl bg-neutral-900 p-4 text-xs leading-relaxed text-neutral-300">
            {result.text}
          </pre>
        )}
        <button className="btn-primary w-full" onClick={() => navigate('/today')}>进入今日</button>
      </div>
    )
  }

  const steps = ['基本信息', '目标与经验', '训练条件', '健康筛查']

  return (
    <div className="mx-auto max-w-lg space-y-4 px-4 pt-6">
      <PageHeader title="开始建档" sub="四步建立你的初始档案 · 健康筛查必答" />
      {uid && (
        <p className="text-xs text-neutral-500">当前用户 {uid}，建档将创建一个新用户档案。</p>
      )}

      <div className="flex gap-1.5">
        {steps.map((s, i) => (
          <div key={s} className={`tag flex-1 justify-center ${i === step ? 'bg-accent text-neutral-950' : i < step ? 'bg-neutral-700 text-neutral-200' : 'bg-neutral-800 text-neutral-500'}`}>
            {i + 1}. {s}
          </div>
        ))}
      </div>

      {error && <ErrorBox message={error.message} details={error.details} />}

      {step === 0 && (
        <div className="card space-y-3">
          <div><label className="label">用户 ID（唯一标识，可自己起）</label>
            <input className="input" value={uidInput} placeholder="例如 xiaowang"
                   onChange={(e) => setUidInput(e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label">年龄</label>
              <input className="input" inputMode="numeric" value={f.age}
                     onChange={(e) => set({ age: e.target.value })} /></div>
            <div><label className="label">性别</label>
              <select className="input" value={f.gender} onChange={(e) => set({ gender: e.target.value })}>
                <option>男</option><option>女</option><option>其他</option>
              </select></div>
            <div><label className="label">身高 cm</label>
              <input className="input" inputMode="numeric" value={f.height}
                     onChange={(e) => set({ height: e.target.value })} /></div>
            <div><label className="label">体重 kg</label>
              <input className="input" inputMode="decimal" value={f.weight}
                     onChange={(e) => set({ weight: e.target.value })} /></div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="card space-y-3">
          <div><label className="label">主要目标</label>
            <div className="flex flex-wrap gap-2">
              {GOALS.map((g) => (
                <button key={g.id} onClick={() => set({ goal: g.id })}
                        className={`btn ${f.goal === g.id ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-200'}`}>
                  {g.label}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-[11px] text-neutral-500">拿不准没关系，之后可以和 AI 教练商量再切换。</p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label">训练年限（年，0 表示新手）</label>
              <input className="input" inputMode="numeric" value={f.years}
                     onChange={(e) => set({ years: e.target.value })} /></div>
            <div><label className="label">停训周数（最近）</label>
              <input className="input" inputMode="numeric" value={f.layoff}
                     onChange={(e) => set({ layoff: e.target.value })} /></div>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="card space-y-3">
          <div><label className="label">训练场地</label>
            <div className="flex gap-2">
              {[['gym', '健身房'], ['home', '居家']].map(([v, label]) => (
                <button key={v} onClick={() => set({ location: v })}
                        className={`btn ${f.location === v ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-200'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label">每周几次（1-7）</label>
              <input className="input" inputMode="numeric" value={f.days}
                     onChange={(e) => set({ days: e.target.value })} /></div>
            <div><label className="label">每次多少分钟</label>
              <input className="input" inputMode="numeric" value={f.minutes}
                     onChange={(e) => set({ minutes: e.target.value })} /></div>
          </div>
          <div>
            <label className="label">伤病（没有可跳过）</label>
            <label className="mb-1.5 flex items-center gap-2 text-sm text-neutral-300">
              <input type="checkbox" checked={f.injuriesNone}
                     onChange={(e) => set({ injuriesNone: e.target.checked })} />
              我没有伤病
            </label>
            {!f.injuriesNone && (
              <textarea className="input min-h-16" value={f.injuries}
                        placeholder="例如：膝盖旧伤、腰偶尔酸（用顿号或换行分隔）"
                        onChange={(e) => set({ injuries: e.target.value })} />
            )}
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="card space-y-3">
          <p className="text-xs leading-relaxed text-neutral-400">
            PAR-Q 健康筛查四项必答，<b>不会默认补全</b>。答案只用于确定训练强度边界，
            不构成医学判断；有疑问请咨询医生。
          </p>
          {([['heart', '心血管疾病（高血压/冠心病等）', ['无', '有']],
             ['pregnancy', '怀孕或备孕', ['不适用', '无', '有']],
             ['medication', '长期用药', ['无', '有']],
             ['clearance', '医生是否限制过你的运动', ['无', '有']]] as const).map(
            ([key, label, presets]) => (
              <div key={key}>
                <label className="label">{label}</label>
                <div className="mb-1.5 flex flex-wrap gap-1.5">
                  {presets.map((p) => (
                    <button key={p}
                            onClick={() => {
                              if (p === '有') {
                                // 选「有」→ 聚焦输入框引导具体说明，不写入占位文字
                                set({ [key]: '' } as Partial<typeof f>)
                                parqRef.current[key]?.focus()
                              } else {
                                set({ [key]: p } as Partial<typeof f>)
                              }
                            }}
                            className={`tag ${p !== '有' && f[key] === p ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-300'}`}>
                      {p === '有' ? '有（需说明）' : p}
                    </button>
                  ))}
                </div>
                <input className="input" value={f[key]} ref={(el) => { parqRef.current[key] = el }}
                       placeholder={f[key] === '' ? '未回答——请选择或填写' : '具体说明（如实填写）'}
                       onChange={(e) => set({ [key]: e.target.value } as Partial<typeof f>)} />
              </div>
            ))}
          {parqPositive && (
            <div className="flex items-start gap-2 rounded-xl bg-amber-950/40 p-3 text-xs text-amber-300">
              <Tag tone="amber">注意</Tag>
              <span>有需要关注项：建档后训练处方会先暂停或降级，先确认医生意见再上强度。</span>
            </div>
          )}
        </div>
      )}

      <div className="flex gap-2">
        {step > 0 && <button className="btn-ghost flex-1" onClick={() => setStep((s) => s - 1)}>上一步</button>}
        {step < 3
          ? <button className="btn-primary flex-[2]" onClick={() => setStep((s) => s + 1)}>下一步</button>
          : <button className="btn-primary flex-[2]" disabled={saving} onClick={submit}>
              {saving ? '生成计划中…' : '完成建档'}
            </button>}
      </div>
      <p className="pb-6 text-center text-[11px] text-neutral-600">
        建档不经过大模型：所有字段确定性校验落库；计划由规则引擎生成。
      </p>
    </div>
  )
}
