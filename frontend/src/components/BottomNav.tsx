import { NavLink } from 'react-router-dom'
import { Dumbbell, Sun, UsersRound, UserRound } from 'lucide-react'

// P0 信息架构（2.0 §1.1）：今日｜训练｜专家｜我的。
// 饮食页在 P1 营养系统落地后加入，不用空壳标签冒充功能。
const TABS = [
  { to: '/today', label: '今日', icon: Sun },
  { to: '/training', label: '训练', icon: Dumbbell },
  { to: '/experts', label: '专家', icon: UsersRound },
  { to: '/mine', label: '我的', icon: UserRound },
]

/** 移动端底部导航（安全区兼容；lg 及以上由侧边栏接管） */
export default function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur
                    lg:hidden"
         style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} aria-label="主导航">
      <div className="mx-auto grid h-14 max-w-2xl grid-cols-4">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} aria-label={t.label}
                   className={({ isActive }) =>
                     `relative flex min-h-[44px] flex-col items-center justify-center gap-0.5
                      text-2xs font-medium transition-colors ${
                        isActive ? 'text-ink' : 'text-muted'}`}>
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute top-0 h-0.5 w-8 rounded-full bg-accent" aria-hidden />
                )}
                <t.icon size={21} strokeWidth={isActive ? 2.2 : 1.8}
                        className={isActive ? 'text-ink' : 'text-muted'} />
                {t.label}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
