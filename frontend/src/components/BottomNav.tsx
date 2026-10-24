import { NavLink } from 'react-router-dom'

const TABS = [
  { to: '/today', label: '今日', icon: '☀️' },
  { to: '/training', label: '训练', icon: '🏋️' },
  { to: '/coach', label: 'AI 教练', icon: '💬' },
  { to: '/explore', label: '探索', icon: '🔍' },
  { to: '/mine', label: '我的', icon: '👤' },
]

export default function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-neutral-800 bg-neutral-950/95 backdrop-blur"
         style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
      <div className="mx-auto grid max-w-lg grid-cols-5">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to}
                   className={({ isActive }) =>
                     `flex flex-col items-center gap-0.5 py-2 text-[11px] ${
                       isActive ? 'text-accent' : 'text-neutral-500'}`}>
            <span className="text-lg leading-none">{t.icon}</span>
            {t.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
