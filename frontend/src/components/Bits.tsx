// 设计系统 v2 — 基础组件库（视觉规范唯一入口，页面不自行定义颜色/间距）。
// 暖白画布 + 白卡片 + 深墨文字 + 青柠强调；正文 ≥14px、点击区 ≥44px。
import {
  ButtonHTMLAttributes, forwardRef, InputHTMLAttributes, ReactNode,
  SelectHTMLAttributes, TextareaHTMLAttributes, useEffect,
} from 'react'
import { AlertTriangle, CheckCircle2, Inbox, Loader2, X } from 'lucide-react'

/* ---------------- 卡片 ---------------- */

export function Card({ title, sub, right, children, className = '', pad = true, onClick }: {
  title?: ReactNode; sub?: ReactNode; right?: ReactNode
  children?: ReactNode; className?: string; pad?: boolean; onClick?: () => void
}) {
  return (
    <section className={`card ${pad ? '' : 'p-0'} ${onClick ? 'cursor-pointer transition-shadow hover:shadow-pop' : ''} ${className}`}
             onClick={onClick}>
      {(title || right) && (
        <div className={`mb-2.5 flex items-start justify-between gap-3 ${pad ? '' : 'px-4 pt-4'}`}>
          <div className="min-w-0">
            {title && <h3 className="text-[15px] font-semibold leading-snug">{title}</h3>}
            {sub && <p className="mt-0.5 text-xs leading-relaxed text-muted">{sub}</p>}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

/** 深色主视觉卡（深底文字对比已验证 ≥11:1，次级文字用 white/70） */
export function CardNight({ title, sub, right, children, className = '' }: {
  title?: ReactNode; sub?: ReactNode; right?: ReactNode; children?: ReactNode; className?: string
}) {
  return (
    <section className={`card-night ${className}`}>
      {(title || right) && (
        <div className="mb-2.5 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h3 className="text-[15px] font-semibold leading-snug text-white">{title}</h3>}
            {sub && <p className="mt-0.5 text-xs leading-relaxed text-white/70">{sub}</p>}
          </div>
          {right && <div className="shrink-0">{right}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

/* ---------------- 标签 ---------------- */

export type TagTone = 'neutral' | 'brand' | 'green' | 'amber' | 'red' | 'blue' | 'onDark' | 'onDarkSoft'

export function Tag({ children, tone = 'neutral', className = '' }: {
  children: ReactNode; tone?: TagTone; className?: string
}) {
  const tones: Record<TagTone, string> = {
    neutral: 'bg-ink/5 text-muted',
    brand: 'bg-accent-soft text-accent-deep',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    red: 'bg-red-50 text-red-600',
    blue: 'bg-sky-50 text-sky-700',
    onDark: 'bg-white/12 text-white',
    onDarkSoft: 'bg-accent/15 text-accent',
  }
  return <span className={`tag ${tones[tone]} ${className}`}>{children}</span>
}

/* ---------------- 按钮 ---------------- */

type BtnVariant = 'primary' | 'night' | 'ghost' | 'soft' | 'danger'

export function Button({ variant = 'primary', size, block, className = '', children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: BtnVariant; size?: 'sm'; block?: boolean
  }) {
  const variants: Record<BtnVariant, string> = {
    primary: 'btn-primary', night: 'btn-night', ghost: 'btn-ghost',
    soft: 'btn-soft', danger: 'btn-danger',
  }
  return (
    <button className={`${variants[variant]} ${size === 'sm' ? 'btn-sm' : ''} ${block ? 'w-full' : ''} ${className}`}
            {...rest}>
      {children}
    </button>
  )
}

/** 行内文字操作（次级链接式按钮） */
export function PlainButton({ className = '', children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`btn-plain ${className}`} {...rest}>{children}</button>
}

/* ---------------- 表单 ---------------- */

export function Field({ label, hint, children, className = '' }: {
  label?: ReactNode; hint?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <div className={className}>
      {label && <label className="label">{label}</label>}
      {children}
      {hint && <p className="mt-1.5 text-xs leading-relaxed text-muted">{hint}</p>}
    </div>
  )
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = '', ...rest }, ref) {
    return <input ref={ref} className={`input ${className}`} {...rest} />
  })

export function Textarea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`input min-h-20 py-2.5 leading-relaxed ${className}`} {...rest} />
}

export function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`select ${className}`} {...rest}>{children}</select>
}

/* ---------------- 反馈状态 ---------------- */

export function ErrorBox({ message, details, onRetry }: {
  message: string; details?: string[]; onRetry?: () => void
}) {
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 p-3.5 text-sm leading-relaxed text-red-700"
         role="alert">
      <div className="flex items-start gap-2">
        <AlertTriangle size={17} className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p>{message}</p>
          {details && details.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-red-600/90">
              {details.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          )}
          {onRetry && (
            <button className="btn-sm btn mt-2 border border-red-200 bg-white text-red-600"
                    onClick={onRetry}>重试</button>
          )}
        </div>
      </div>
    </div>
  )
}

/** 警示条（提醒/离线等非阻断信息，amber 系；安全类请用红色 ErrorBox） */
export function Notice({ children, tone = 'amber', className = '' }: {
  children: ReactNode; tone?: 'amber' | 'blue' | 'brand'; className?: string
}) {
  const tones = {
    amber: 'border-amber-200 bg-amber-50 text-amber-800',
    blue: 'border-sky-200 bg-sky-50 text-sky-800',
    brand: 'border-accent/50 bg-accent-soft text-accent-deep',
  }
  return (
    <div className={`flex items-start gap-2 rounded-2xl border p-3.5 text-sm leading-relaxed ${tones[tone]} ${className}`}>
      {children}
    </div>
  )
}

export function Empty({ icon, title, children }: {
  icon?: ReactNode; title?: ReactNode; children?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-lineStrong
                    bg-surface/60 px-6 py-10 text-center">
      <div className="flex size-11 items-center justify-center rounded-full bg-canvas text-muted">
        {icon || <Inbox size={20} />}
      </div>
      {title && <p className="text-sm font-medium text-ink">{title}</p>}
      {children && <p className="max-w-64 text-xs leading-relaxed text-muted">{children}</p>}
    </div>
  )
}

export function Spinner({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted">
      <Loader2 size={16} className="animate-spin" />
      {label}
    </div>
  )
}

/** 骨架占位（列表加载） */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse-soft rounded-xl bg-ink/6 ${className}`} />
}

/* ---------------- 页头 / 分区 ---------------- */

export function PageHeader({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <header className="mb-4 flex items-start justify-between gap-3 pt-1">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-[13px] leading-relaxed text-muted">{sub}</p>}
      </div>
      {right && <div className="shrink-0 pt-1">{right}</div>}
    </header>
  )
}

/** 次级页面顶栏：返回 + 标题（移动吸顶） */
export function SubHeader({ title, sub, onBack, right }: {
  title: ReactNode; sub?: ReactNode; onBack: () => void; right?: ReactNode
}) {
  return (
    <header className="sticky top-0 z-30 -mx-4 mb-4 flex items-center gap-2 border-b border-line
                       bg-canvas/90 px-4 py-2.5 backdrop-blur">
      <button className="-ml-2 flex size-9 items-center justify-center rounded-full text-ink
                         transition-colors hover:bg-ink/5"
              onClick={onBack} aria-label="返回">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-[17px] font-bold leading-tight">{title}</h1>
        {sub && <p className="truncate text-xs text-muted">{sub}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </header>
  )
}

export function SectionLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-2 mt-1 flex items-center justify-between">
      <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">{children}</h2>
      {right}
    </div>
  )
}

/* ---------------- 数据展示 ---------------- */

/** 关键指标块 */
export function Stat({ value, label, tone = 'default' }: {
  value: ReactNode; label: string; tone?: 'default' | 'warn'
}) {
  return (
    <div className="card flex flex-col items-center gap-0.5 px-2 py-3.5 text-center">
      <p className={`nums text-2xl font-bold leading-none ${tone === 'warn' ? 'text-amber-600' : 'text-ink'}`}>
        {value}
      </p>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </div>
  )
}

export function ProgressBar({ value, max, className = '' }: {
  value: number; max: number; className?: string
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className={`h-2 overflow-hidden rounded-full bg-ink/8 ${className}`} role="progressbar"
         aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
    </div>
  )
}

/** 分段选择器 */
export function Segmented<T extends string>({ options, value, onChange, className = '' }: {
  options: { value: T; label: ReactNode; badge?: number }[]
  value: T; onChange: (v: T) => void; className?: string
}) {
  return (
    <div className={`flex gap-1 rounded-xl bg-ink/5 p-1 ${className}`} role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value}
                onClick={() => onChange(o.value)}
                className={`relative flex min-h-[38px] flex-1 items-center justify-center gap-1.5 rounded-lg
                            px-2 text-[13px] font-medium transition-all
                            ${value === o.value ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink'}`}>
          {o.label}
          {o.badge != null && o.badge > 0 && (
            <span className="nums flex h-[18px] min-w-[18px] items-center justify-center rounded-full
                             bg-accent px-1 text-[11px] font-bold text-ink">{o.badge}</span>
          )}
        </button>
      ))}
    </div>
  )
}

/** 筛选 chip（横滑） */
export function Chip({ active, children, onClick }: {
  active: boolean; children: ReactNode; onClick: () => void
}) {
  return (
    <button onClick={onClick}
            className={`tag shrink-0 border transition-colors ${
              active ? 'border-accent-deep/30 bg-night text-white'
                     : 'border-line bg-surface text-muted hover:border-lineStrong hover:text-ink'}`}>
      {children}
    </button>
  )
}

/* ---------------- 弹层 ---------------- */

/** 底部抽屉（移动）/ 居中对话框（桌面）；滚动锁定 + Esc 关闭 */
export function Sheet({ open, onClose, title, children, footer, wide }: {
  open: boolean; onClose: () => void; title?: ReactNode
  children: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = prev; window.removeEventListener('keydown', onKey) }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/45 sm:items-center sm:p-6"
         onClick={onClose} role="dialog" aria-modal="true">
      <div className={`flex max-h-[90dvh] w-full flex-col overflow-hidden rounded-t-3xl bg-surface shadow-pop
                       animate-sheet-up sm:max-h-[82vh] sm:rounded-3xl ${wide ? 'sm:max-w-2xl' : 'sm:max-w-md'}`}
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="mx-auto h-1 w-9 rounded-full bg-lineStrong sm:hidden" aria-hidden />
          {title && <h3 className="flex-1 text-[15px] font-semibold">{title}</h3>}
          <button className="-mr-1 flex size-8 items-center justify-center rounded-full text-muted
                             transition-colors hover:bg-canvas hover:text-ink"
                  onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4">{children}</div>
        {footer && <div className="border-t border-line bg-surface px-4 py-3 pb-[max(12px,env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </div>
  )
}

/* ---------------- 结果反馈 ---------------- */

export function SuccessBlock({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <div className="flex size-16 items-center justify-center rounded-full bg-accent-soft">
        <CheckCircle2 size={32} className="text-accent-deep" />
      </div>
      <h2 className="text-xl font-bold">{title}</h2>
      {children}
    </div>
  )
}
