// 账户删除后的客户端清理：localStorage / IndexedDB / Cache Storage。
// 只清本应用的 key，避免误删同源其他应用数据。
import { clearOfflineData } from '../offline'

const APP_PREFIXES = ['fc-', 'm5-trial-draft']

export async function clearClientData(): Promise<void> {
  try {
    const keys = Object.keys(localStorage)
    for (const key of keys) {
      if (APP_PREFIXES.some((p) => key === p || key.startsWith(p))) {
        localStorage.removeItem(key)
      }
    }
  } catch { /* 隐私模式 */ }
  try { await clearOfflineData() } catch { /* IndexedDB 不可用 */ }
  try {
    if ('caches' in window) {
      const names = await caches.keys()
      await Promise.all(names.map((n) => caches.delete(n)))
    }
  } catch { /* Cache Storage 不可用 */ }
}
