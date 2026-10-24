import { NavLink } from 'react-router-dom'
import {
  CalendarRange, Compass, Dumbbell, MessageCircleHeart, Settings,
  Sun, UserRound,
} from 'lucide-react'
import { useApp } from '../store'

const NAV = [
  { to: '/today', label: '今日', icon: Sun },
  { to: '/training', label: '训练', icon: Dumbbell },
  { to: '/coach', label: 'AI 教练', icon: MessageCircleHeart },
  { to: '/explore', label: '探索', icon: Compass },
  { to: '/mine', label: '我的', icon: UserRound },
]

const SUB = [
  { to: '/history', label: '训练历史', icon: CalendarRange },
  { to: '/mine/settings', label: '设置与数据', icon: Settings },
]

/** 桌面端侧边栏（lg+），与移动端底部导航同一套信息架构 */
export default function SideNav() {
  const uid = useApp((s) => s.uid)
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-line bg-surface lg:flex">
      <div className="flex items-center gap-2.5 px-5 pb-5 pt-6">
        <span className="flex size-9 items-center justify-center rounded-xl bg-night">
          <Dumbbell size={18} className="text-accent" />
        </span>
        <div className="leading-tight">
          <p className="text-[15px] font-bold">Fitness Coach</p>
          <p className="text-xs text-muted">遵循自身 · 科学训练</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3" aria-label="主导航">
        {NAV.map((t) => (
          <NavLink key={t.to} to={t.to}
                   className={({ isActive }) =>
                     `flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors ${
                       isActive ? 'bg-accent-soft text-accent-deep' : 'text-muted hover:bg-canvas hover:text-ink'}`}>
            <t.icon size={19} strokeWidth={1.9} />
            {t.label}
          </NavLink>
        ))}
        <div className="my-2 border-t border-line" aria-hidden />
        {SUB.map((t) => (
          <NavLink key={t.to} to={t.to}
                   className={({ isActive }) =>
                     `flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm transition-colors ${
                       isActive ? 'bg-canvas text-ink' : 'text-muted hover:bg-canvas hover:text-ink'}`}>
            <t.icon size={18} strokeWidth={1.8} />
            {t.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-line px-5 py-4">
        <p className="text-2xs uppercase tracking-wide text-muted">当前用户</p>
        <p className="mt-0.5 truncate text-sm font-medium">{uid || '—'}</p>
      </div>
    </aside>
  )
}
