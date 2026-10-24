import { ReactNode } from 'react'

export function Card({ title, children, right }: {
  title?: ReactNode; children: ReactNode; right?: ReactNode
}) {
  return (
    <div className="card">
      {(title || right) && (
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-neutral-300">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

export function Tag({ children, tone = 'neutral' }: {
  children: ReactNode; tone?: 'neutral' | 'green' | 'amber' | 'red' | 'blue'
}) {
  const tones = {
    neutral: 'bg-neutral-800 text-neutral-300',
    green: 'bg-emerald-900/60 text-emerald-300',
    amber: 'bg-amber-900/60 text-amber-300',
    red: 'bg-red-900/60 text-red-300',
    blue: 'bg-sky-900/60 text-sky-300',
  }
  return <span className={`tag ${tones[tone]}`}>{children}</span>
}

export function ErrorBox({ message, details }: { message: string; details?: string[] }) {
  return (
    <div className="rounded-xl border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
      <p>{message}</p>
      {details && details.length > 0 && (
        <ul className="mt-1 list-disc pl-4 text-xs text-red-400/90">
          {details.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      )}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-neutral-500">{children}</p>
}

export function Spinner({ label = '加载中…' }: { label?: string }) {
  return <p className="py-10 text-center text-sm text-neutral-500">{label}</p>
}

export function PageHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <header className="mb-3 pt-1">
      <h1 className="text-xl font-bold">{title}</h1>
      {sub && <p className="mt-0.5 text-xs text-neutral-500">{sub}</p>}
    </header>
  )
}
