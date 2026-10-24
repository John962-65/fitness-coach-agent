import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import BottomNav from './components/BottomNav'
import SideNav from './components/SideNav'
import Coach from './pages/Coach'
import Explore from './pages/Explore'
import ExploreDetail from './pages/ExploreDetail'
import History from './pages/History'
import Mine from './pages/Mine'
import MineApproach from './pages/MineApproach'
import MineSettings from './pages/MineSettings'
import Onboarding from './pages/Onboarding'
import PlanEditor from './pages/PlanEditor'
import Today from './pages/Today'
import Training from './pages/Training'
import Workout from './pages/Workout'
import { useApp } from './store'

// 训练执行走沉浸式布局：无侧栏/底栏，由 Workout 自行掌控整屏
const isImmersive = (path: string) => path.startsWith('/workout')

function Shell() {
  const uid = useApp((s) => s.uid)
  const location = useLocation()
  const setOfflineCount = useApp((s) => s.setOfflineCount)
  const immersive = isImmersive(location.pathname)

  // 路由变化时尝试同步离线队列（恢复联网后自动补交）
  useEffect(() => {
    import('./offline').then(({ syncQueue, queuedCount }) =>
      syncQueue(async (u, type, data, sid) => { await api.saveCheckin(u, type, data, sid) })
        .then((r) => { if (r.synced || r.failed) queuedCount().then(setOfflineCount) })
        .catch(() => { /* 离线：留在队列 */ }))
  }, [location.pathname, setOfflineCount])

  if (!uid) return <Navigate to="/welcome" replace />

  const isChat = location.pathname.startsWith('/coach')

  return (
    <div className={immersive ? 'min-h-dvh' : 'min-h-dvh lg:pl-60'}>
      {!immersive && <SideNav />}
      {/* chat 页自管高度与滚动（输入框吸底）；其余页面常规纵向滚动 */}
      <main className={
        immersive ? ''
        : isChat ? 'mx-auto w-full lg:px-8'
        : 'mx-auto w-full max-w-5xl px-4 pb-[calc(4.5rem+env(safe-area-inset-bottom))] pt-3 lg:px-8 lg:pb-12 lg:pt-6'
      }>
        <Routes>
          <Route path="/today" element={<Today />} />
          <Route path="/training" element={<Training />} />
          <Route path="/training/edit" element={<PlanEditor />} />
          <Route path="/history" element={<History />} />
          <Route path="/workout/:day" element={<Workout />} />
          <Route path="/coach" element={<Coach />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/explore/:exerciseId" element={<ExploreDetail />} />
          <Route path="/mine" element={<Mine />} />
          <Route path="/mine/approach" element={<MineApproach />} />
          <Route path="/mine/settings" element={<MineSettings />} />
          <Route path="*" element={<Navigate to="/today" replace />} />
        </Routes>
      </main>
      {!immersive && <BottomNav />}
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/welcome" element={<Onboarding />} />
      <Route path="/*" element={<Shell />} />
    </Routes>
  )
}
