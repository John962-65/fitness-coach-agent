import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ArrowRight, Building2, Check, Dumbbell, FlaskConical, Flame,
  HeartPulse, Home, ShieldCheck, Sparkles, Target, UserRound, Zap,
} from 'lucide-react'
import { api, ApiError, OnboardingResult } from '../api'
import { ErrorBox, Field, Input, Select, SuccessBlock } from '../components/Bits'
import { useApp } from '../store'

const GOALS = [
  { id: 'fat_loss', label: '减脂', desc: '降低体脂、更精干', icon: Flame },
  { id: 'muscle_gain', label: '增肌', desc: '增加肌肉与围度', icon: Dumbbell },
  { id: 'strength', label: '力量', desc: '举起更大的重量', icon: Zap },
  { id: 'health', label: '健康', desc: '精力与身体状态', icon: HeartPulse },
  { id: 'shaping', label: '塑形', desc: '线条与体态', icon: Sparkles },
]

const STEPS = [
  { label: '基本信息', icon: UserRound },
  { label: '目标与经验', icon: Target },
  { label: '训练条件', icon: Dumbbell },
  { label: '健康筛查', icon: ShieldCheck },
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
    const newUid = uidInput.trim() || `web-${Date.now().toString(36)}`
    const injuries = f.injuriesNone ? []
      : f.injuries.split(/[、,，;；\n]/).map((s) => s.trim()).filter(Boolean)
    try {
      const r = await api.onboard(newUid, {
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
      setUid(newUid)
      setResult(r)
    } catch (e) {
      const err = e as ApiError
      setError({ message: err.message, details: err.details })
    } finally { setSaving(false) }
  }

  if (result) {
    return (
      <div className="mx-auto min-h-dvh w-full max-w-lg px-4 pb-10 pt-14">
        {result.suspended ? (
          <div className="card border-2 border-red-300 !p-6 text-center">
            <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-red-50">
              <ShieldCheck size={30} className="text-red-500" />
            </span>
            <h1 className="mt-3 text-xl font-bold">建档完成，需要先确认健康状态</h1>
            <p className="mx-auto mt-2 max-w-80 text-sm leading-relaxed text-muted">
              健康筛查有需要关注项，训练处方已暂停（这不是诊断）。请先与医疗专业人员确认可以做什么运动，
              然后到「AI 教练」页告知医生结论，确认后恢复安排。
            </p>
          </div>
        ) : (
          <>
            <SuccessBlock title={`建档完成 · 定级 ${result.level === 'beginner' ? '新手' : result.level === 'intermediate' ? '进阶' : '老炮'}`}>
              <p className="max-w-72 text-sm leading-relaxed text-muted">
                初始计划已生成，随时可以和 AI 教练商量调整。
              </p>
            </SuccessBlock>
            <pre className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-2xl border border-line
                            bg-surface p-4 text-xs leading-relaxed text-ink/90">
              {result.text}
            </pre>
          </>
        )}
        <button className="btn-primary mt-6 w-full" onClick={() => navigate('/today')}>
          进入今日 <ArrowRight size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="mx-auto min-h-dvh w-full max-w-lg px-4 pb-8">
      {/* 品牌头 */}
      <header className="flex items-center gap-2.5 pb-5 pt-8">
        <span className="flex size-10 items-center justify-center rounded-xl bg-night">
          <Dumbbell size={19} className="text-accent" />
        </span>
        <div>
          <p className="text-[17px] font-bold leading-tight">Fitness Coach</p>
          <p className="text-xs text-muted">遵循自身，找到契合自己的训练方式</p>
        </div>
      </header>

      {/* 可视化进度条 */}
      <ol className="mb-5 flex items-center gap-1.5" aria-label={`第 ${step + 1} 步，共 4 步`}>
        {STEPS.map((s, i) => (
          <li key={s.label} className="flex flex-1 flex-col gap-1.5">
            <div className={`h-1.5 rounded-full transition-colors ${
              i < step ? 'bg-accent' : i === step ? 'bg-night' : 'bg-ink/10'}`} />
            <span className={`flex items-center gap-1 text-2xs ${
              i <= step ? 'font-medium text-ink' : 'text-faint'}`}>
              <s.icon size={12} /> {s.label}
            </span>
          </li>
        ))}
      </ol>

      {error && <div className="mb-3"><ErrorBox message={error.message} details={error.details} /></div>}

      <div key={step} className="animate-fade-up">
        {step === 0 && (
          <div className="card space-y-4">
            <h2 className="text-lg font-bold">先认识一下你</h2>
            <Field label="怎么称呼你（用户 ID，可自己起）" hint="它也是你的数据标识，建档后不可更改">
              <Input value={uidInput} placeholder="例如 xiaowang"
                     onChange={(e) => setUidInput(e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="年龄">
                <Input inputMode="numeric" value={f.age} onChange={(e) => set({ age: e.target.value })} />
              </Field>
              <Field label="性别">
                <Select value={f.gender} onChange={(e) => set({ gender: e.target.value })}>
                  <option>男</option><option>女</option><option>其他</option>
                </Select>
              </Field>
              <Field label="身高（cm）">
                <Input inputMode="numeric" value={f.height} onChange={(e) => set({ height: e.target.value })} />
              </Field>
              <Field label="体重（kg）">
                <Input inputMode="decimal" value={f.weight} onChange={(e) => set({ weight: e.target.value })} />
              </Field>
            </div>
            {uid && <p className="text-xs text-muted">当前用户 {uid}，建档将创建一个新用户档案。</p>}
          </div>
        )}

        {step === 1 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-lg font-bold">你最想达成什么？</h2>
              <p className="mt-0.5 text-xs text-muted">拿不准没关系，之后可以和 AI 教练商量再切换。</p>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              {GOALS.map((g) => (
                <button key={g.id} onClick={() => set({ goal: g.id })}
                        className={`flex min-h-[76px] flex-col justify-center gap-0.5 rounded-2xl border-2
                                    p-3 text-left transition-colors ${
                          f.goal === g.id
                            ? 'border-accent-deep/60 bg-accent-soft'
                            : 'border-line bg-surface hover:border-lineStrong'}`}>
                  <span className="flex items-center gap-2">
                    <g.icon size={17} className={f.goal === g.id ? 'text-accent-deep' : 'text-muted'} />
                    <span className="text-sm font-semibold">{g.label}</span>
                    {f.goal === g.id && <Check size={14} className="ml-auto text-accent-deep" />}
                  </span>
                  <span className="text-2xs text-muted">{g.desc}</span>
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="训练年限（年，0 表示新手）">
                <Input inputMode="numeric" value={f.years} onChange={(e) => set({ years: e.target.value })} />
              </Field>
              <Field label="最近停训了多久（周）">
                <Input inputMode="numeric" value={f.layoff} onChange={(e) => set({ layoff: e.target.value })} />
              </Field>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-lg font-bold">在哪里练、练多久？</h2>
              <p className="mt-0.5 text-xs text-muted">计划会按你的条件安排。</p>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              {([['gym', '健身房', Building2], ['home', '居家', Home]] as const).map(([v, label, Icon]) => (
                <button key={v} onClick={() => set({ location: v })}
                        className={`flex min-h-[64px] items-center justify-center gap-2 rounded-2xl border-2
                                    text-sm font-semibold transition-colors ${
                          f.location === v
                            ? 'border-accent-deep/60 bg-accent-soft text-accent-deep'
                            : 'border-line bg-surface text-muted hover:border-lineStrong'}`}>
                  <Icon size={18} /> {label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="每周练几次（1-7）">
                <Input inputMode="numeric" value={f.days} onChange={(e) => set({ days: e.target.value })} />
              </Field>
              <Field label="每次多少分钟">
                <Input inputMode="numeric" value={f.minutes} onChange={(e) => set({ minutes: e.target.value })} />
              </Field>
            </div>
            <div>
              <Field label="有没有伤病或不适的部位？">
                <label className="flex min-h-11 items-center gap-2.5 rounded-xl border border-line bg-surface
                                  px-3.5 text-sm">
                  <input type="checkbox" className="size-4 accent-[#3D5A26]" checked={f.injuriesNone}
                         onChange={(e) => set({ injuriesNone: e.target.checked })} />
                  我没有伤病
                </label>
              </Field>
              {!f.injuriesNone && (
                <textarea className="input mt-2 min-h-20" value={f.injuries}
                          placeholder="例如：膝盖旧伤、腰偶尔酸（用顿号或换行分隔）"
                          onChange={(e) => set({ injuries: e.target.value })} />
              )}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="card space-y-4">
            <div>
              <h2 className="text-lg font-bold">最后：健康筛查</h2>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                四项都需要你亲自作答，<b className="text-ink">不会替你默认</b>。
                答案只用于确定训练强度边界，不构成医学判断；有疑问请咨询医生。
              </p>
            </div>
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
                              className={`tag min-h-9 px-3 transition-colors ${
                                p !== '有' && f[key] === p
                                  ? 'bg-night text-white'
                                  : 'border border-line bg-surface text-muted'}`}>
                        {p === '有' ? '有（需说明）' : p}
                      </button>
                    ))}
                  </div>
                  <Input value={f[key]} ref={(el) => { parqRef.current[key] = el }}
                         placeholder={f[key] === '' ? '未回答——请选择或填写' : '具体说明（如实填写）'}
                         onChange={(e) => set({ [key]: e.target.value } as Partial<typeof f>)} />
                </div>
              ))}
            {parqPositive && (
              <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50
                              p-3.5 text-xs leading-relaxed text-amber-800">
                <FlaskConical size={15} className="mt-0.5 shrink-0" />
                <span>有需要关注项：建档后训练处方会先暂停或降级，先确认医生意见再上强度。</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部导航按钮 */}
      <div className="mt-5 flex gap-3">
        {step > 0 && (
          <button className="btn-ghost flex-1" onClick={() => setStep((s) => s - 1)}>
            <ArrowLeft size={15} /> 上一步
          </button>
        )}
        {step < 3
          ? <button className="btn-primary flex-[2]" onClick={() => setStep((s) => s + 1)}>
              下一步 <ArrowRight size={15} />
            </button>
          : <button className="btn-primary flex-[2]" disabled={saving} onClick={submit}>
              {saving ? '生成计划中…' : '完成建档'}
            </button>}
      </div>
      <p className="pb-4 pt-3 text-center text-2xs leading-relaxed text-faint">
        建档不经过大模型：所有字段确定性校验落库；计划由规则引擎生成。
      </p>
    </div>
  )
}
