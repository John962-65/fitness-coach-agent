import { ArrowRight, Activity, HeartPulse, PersonStanding,
         Salad, Stethoscope, Dumbbell } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ExpertSpecialistInfo } from '../../types'

const ICONS: Record<string, typeof Activity> = {
  training_science: Activity,
  nutrition: Salad,
  recovery: HeartPulse,
  rehabilitation: Stethoscope,
  movement: PersonStanding,
}

/** 专家中心页的顾问卡：真实状态如实标注（ready=工作台已上线；planned=建设中） */
export default function ExpertCard({ spec }: { spec: ExpertSpecialistInfo }) {
  const Icon = ICONS[spec.specialist] ?? Dumbbell
  const ready = spec.workbench === 'ready'
  const body = (
    <div className={`card flex items-start gap-3.5 transition-shadow
                    ${ready ? 'hover:shadow-pop' : ''}`}>
      <span className={`flex size-11 shrink-0 items-center justify-center rounded-xl
                        ${ready ? 'bg-accent-soft' : 'bg-ink/4'}`}>
        <Icon size={21} className={ready ? 'text-accent-deep' : 'text-faint'} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-[15px] font-semibold">{spec.label}</p>
          {ready ? (
            <span className="tag bg-emerald-50 text-emerald-700">工作台</span>
          ) : (
            <span className="tag bg-ink/5 text-faint">建设中</span>
          )}
          {spec.active_insights > 0 && (
            <span className="tag bg-accent-soft text-accent-deep">
              {spec.active_insights} 条新分析
            </span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-muted">{spec.domain}</p>
        <p className="mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-ink/70">
          {ready
            ? `数据来源：${spec.data_sources.join('；')}`
            : (spec.workbench_note ?? '')}
        </p>
      </div>
      {ready && <ArrowRight size={18} className="mt-1 shrink-0 text-muted" />}
    </div>
  )
  return ready && spec.workbench_path
    ? <Link to={spec.workbench_path}>{body}</Link>
    : body
}
