import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import BottomNav from './components/BottomNav'
import Coach from './pages/Coach'
import Explore from './pages/Explore'
import History from './pages/History'
import Mine from './pages/Mine'
import Onboarding from './pages/Onboarding'
import PlanEditor from './pages/PlanEditor'
import Today from './pages/Today'
import Training from './pages/Training'
import Workout from './pages/Workout'
import { useApp } from './store'

function Shell() {
  const uid = useApp((s) => s.uid)
  const location = useLocation()
  const setOfflineCount = useApp((s) => s.setOfflineCount)

  // 路由变化时尝试同步离线队列（恢复联网后自动补交）
  useEffect(() => {
    import('./offline').then(({ syncQueue, queuedCount }) =>
      syncQueue(async (u, type, data, sid) => { await api.saveCheckin(u, type, data, sid) })
        .then((r) => { if (r.synced || r.failed) queuedCount().then(setOfflineCount) })
        .catch(() => { /* 离线：留在队列 */ }))
  }, [location.pathname, setOfflineCount])

  if (!uid) return <Navigate to="/welcome" replace />
  return (
    <div className="mx-auto min-h-dvh max-w-lg px-4 pb-20">
      <Routes>
        <Route path="/today" element={<Today />} />
        <Route path="/training" element={<Training />} />
        <Route path="/training/edit" element={<PlanEditor />} />
        <Route path="/history" element={<History />} />
        <Route path="/workout/:day" element={<Workout />} />
        <Route path="/coach" element={<Coach />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/mine" element={<Mine />} />
        <Route path="*" element={<Navigate to="/today" replace />} />
      </Routes>
      <BottomNav />
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
