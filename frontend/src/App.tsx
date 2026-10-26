import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { api } from './api'
import BottomNav from './components/BottomNav'
import SideNav from './components/SideNav'
import Coach from './pages/Coach'
import Explore from './pages/Explore'
import ExploreDetail from './pages/ExploreDetail'
import Experts from './pages/Experts'
import History from './pages/History'
import Mine from './pages/Mine'
import MineApproach from './pages/MineApproach'
import MineSettings from './pages/MineSettings'
import Onboarding from './pages/Onboarding'
import PlanEditor from './pages/PlanEditor'
import Today from './pages/Today'
import MovementExpert from './pages/experts/MovementExpert'
import Rehab from './pages/experts/Rehabilitation'
import Recovery from './pages/experts/Recovery'
import BodyMetrics from './pages/BodyMetrics'
import TrainingExpert from './pages/experts/TrainingExpert'
import Collaboration from './pages/experts/Collaboration'
import LongTermOverview from './pages/LongTermOverview'
import Nutrition from './pages/Nutrition'
import NutritionHistory from './pages/nutrition/NutritionHistory'
import NutritionTargets from './pages/nutrition/NutritionTargets'
import NutritionExpert from './pages/experts/NutritionExpert'
import Training from './pages/Training'
import TrainingLocations from './pages/TrainingLocations'
import Workout from './pages/Workout'
import { useApp } from './store'

// 训练执行走沉浸式布局：无侧栏/底栏，由 Workout 自行掌控整屏
const isImmersive = (path: string) => path.startsWith('/workout')

/** 旧 /explore/:id → /experts/knowledge/:id（保留动作参数） */
function OldExploreRedirect() {
  const { exerciseId } = useParams()
  return <Navigate to={`/experts/knowledge/${exerciseId ?? ''}`} replace />
}

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

  const isChat = location.pathname.startsWith('/experts/chat')

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
          <Route path="/workout/template/:templateId" element={<Workout />} />
          <Route path="/workout/:day" element={<Workout />} />
          {/* P0 专家平台：中心页 / 训练科学工作台 / 主教练聊天 / 知识检索 */}
          <Route path="/nutrition" element={<Nutrition />} />
          <Route path="/nutrition/history" element={<NutritionHistory />} />
          <Route path="/nutrition/targets" element={<NutritionTargets />} />
          <Route path="/experts" element={<Experts />} />
          <Route path="/experts/training" element={<TrainingExpert />} />
          <Route path="/experts/nutrition" element={<NutritionExpert />} />
          <Route path="/experts/recovery" element={<Recovery />} />
          <Route path="/experts/rehabilitation" element={<Rehab />} />
          <Route path="/experts/movement" element={<MovementExpert />} />
          <Route path="/experts/collaboration" element={<Collaboration />} />
          <Route path="/mine/body" element={<BodyMetrics />} />
          <Route path="/mine/locations" element={<TrainingLocations />} />
          <Route path="/mine/overview" element={<LongTermOverview />} />
          <Route path="/experts/chat" element={<Coach />} />
          <Route path="/experts/knowledge" element={<Explore />} />
          <Route path="/experts/knowledge/:exerciseId" element={<ExploreDetail />} />
          <Route path="/mine" element={<Mine />} />
          <Route path="/mine/approach" element={<MineApproach />} />
          <Route path="/mine/settings" element={<MineSettings />} />
          {/* 旧路径兼容重定向（2.0 §1.1：不破坏既有链接/书签） */}
          <Route path="/coach" element={<Navigate to="/experts/chat" replace />} />
          <Route path="/explore" element={<Navigate to="/experts/knowledge" replace />} />
          <Route path="/explore/:exerciseId" element={<OldExploreRedirect />} />
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
