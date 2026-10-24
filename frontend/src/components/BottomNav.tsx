import { NavLink } from 'react-router-dom'
import { Compass, Dumbbell, MessageCircleHeart, Sun, UserRound } from 'lucide-react'

const TABS = [
  { to: '/today', label: '今日', icon: Sun },
  { to: '/training', label: '训练', icon: Dumbbell },
  { to: '/coach', label: 'AI 教练', icon: MessageCircleHeart },
  { to: '/explore', label: '探索', icon: Compass },
  { to: '/mine', label: '我的', icon: UserRound },
]

/** 移动端底部五栏导航（安全区兼容；lg 及以上由侧边栏接管） */
export default function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur
                    lg:hidden"
         style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} aria-label="主导航">
      <div className="mx-auto grid h-14 max-w-2xl grid-cols-5">
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
