// RC-FIX-B 浏览器 E2E：完整导出 → 导入预览/确认 → 删除账户 → 清本地缓存。
// 需要本机 google-chrome；不依赖 Playwright。
import { spawn } from 'node:child_process'
import { appendFileSync } from 'node:fs'
import { mkdtemp, mkdir, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const REPO = process.cwd()
const API_PORT = Number(process.env.FC_E2E_API_PORT || 18084)
const WEB_PORT = Number(process.env.FC_E2E_WEB_PORT || 5180)
const CDP_PORT = Number(process.env.FC_E2E_CDP_PORT || 9228)
const OUT = process.env.FC_E2E_SHOTS || 'docs/rc-fix-shots'
const API = `http://127.0.0.1:${API_PORT}`
const WEB = `http://127.0.0.1:${WEB_PORT}`
const uidA = `rcfix-a-${Date.now()}`
const uidB = `rcfix-b-${Date.now()}`
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitFetch(url, timeout = 30000) {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    try { const r = await fetch(url); if (r.ok) return } catch { /* retry */ }
    await sleep(200)
  }
  throw new Error(`服务未就绪：${url}`)
}

async function request(path, init = {}) {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
  const text = await res.text()
  let body = null
  try { body = text ? JSON.parse(text) : null } catch { body = text }
  if (!res.ok) throw new Error(`${path}: ${res.status} ${JSON.stringify(body)}`)
  return body
}
const post = (path, body = {}) => request(path, {
  method: 'POST', body: JSON.stringify(body),
})

async function seed(uid) {
  await post(`/api/users/${uid}/onboarding`, {
    basic: { age: 30, gender: '男', height_cm: 175, weight_kg: 75 },
    goal: { primary: 'muscle_gain' },
    experience: { training_years: 2, recent_layoff_weeks: 0 },
    resources: { location: 'gym', days_per_week: 3, session_minutes: 60 },
    conditions: {
      injuries: [], injuries_evidence: '用户自述无伤病',
      health_screen: { heart: '无', pregnancy: '不适用', medication: '无', clearance: '无' },
      health_screen_evidence: '用户逐项作答',
    },
  })
  await post(`/api/users/${uid}/checkins`, {
    type: 'training', data: {
      exercises: [{
        name: '杠铃平板卧推', exercise_id: 'barbell_bench_press',
        set_logs: [{ type: 'weight_reps', weight_kg: 60, reps: 8 }],
      }],
      session_meta: { mode: 'free', local_date: new Date().toISOString().slice(0, 10) },
    },
  })
}

class Cdp {
  constructor(url) { this.url = url; this.id = 0; this.pending = new Map() }
  async open() {
    this.ws = new WebSocket(this.url)
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true })
      this.ws.addEventListener('error', reject, { once: true })
    })
    this.ws.addEventListener('message', (event) => {
      const msg = JSON.parse(event.data)
      if (!msg.id) return
      const p = this.pending.get(msg.id)
      if (!p) return
      this.pending.delete(msg.id)
      if (msg.error) p.reject(new Error(msg.error.message))
      else p.resolve(msg.result)
    })
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this.id
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }
  close() { this.ws.close() }
}

async function launchChrome(downloadDir) {
  const profile = await mkdtemp(join(tmpdir(), 'coach-rcfix-chrome-'))
  const chrome = spawn('google-chrome', [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
    '--remote-allow-origins=*', `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profile}`, '--window-size=390,844', 'about:blank',
  ], { stdio: 'ignore' })
  for (let i = 0; i < 150; i++) {
    try {
      const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json`).then((r) => r.json())
      const page = targets.find((t) => t.type === 'page')
      if (page) return { chrome, profile, cdp: new Cdp(page.webSocketDebuggerUrl) }
    } catch { /* retry */ }
    await sleep(100)
  }
  throw new Error('Chrome DevTools 未就绪')
}

async function main() {
  const tmp = await mkdtemp(join(tmpdir(), 'coach-rcfix-'))
  const dbPath = join(tmp, 'e2e.db')
  const downloadDir = join(tmp, 'downloads')
  await mkdir(downloadDir, { recursive: true })
  await mkdir(OUT, { recursive: true })
  const serverCode = `
from pathlib import Path
from backend.app import create_app
import uvicorn
app = create_app(db_path=Path(r"${dbPath}"))
uvicorn.run(app, host="127.0.0.1", port=${API_PORT}, log_level="warning")
`
  const serverLog = join(OUT, 'e2e-server.log')
  const webLog = join(OUT, 'e2e-web.log')
  const server = spawn('python3', ['-c', serverCode], {
    cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, FAKE_LLM: '1' },
  })
  server.stdout.on('data', (d) => appendFileSync(serverLog, d))
  server.stderr.on('data', (d) => appendFileSync(serverLog, d))
  server.on('exit', (code, signal) => appendFileSync(serverLog, `\n[exit ${code} ${signal}]\n`))
  const web = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1',
    '--port', String(WEB_PORT), '--strictPort'], {
    cwd: join(REPO, 'frontend'), stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, FC_API_TARGET: API },
  })
  web.stdout.on('data', (d) => appendFileSync(webLog, d))
  web.stderr.on('data', (d) => appendFileSync(webLog, d))
  web.on('exit', (code, signal) => appendFileSync(webLog, `\n[exit ${code} ${signal}]\n`))
  let launched
  try {
    await waitFetch(`${API}/api/health`)
    await seed(uidA)
    await seed(uidB)
    await waitFetch(WEB)
    launched = await launchChrome(downloadDir)
    const { cdp } = launched
    await cdp.open()
    await cdp.send('Page.enable')
    await cdp.send('Runtime.enable')
    await cdp.send('DOM.enable')
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 390, height: 844, deviceScaleFactor: 1, mobile: true,
    })
    try {
      await cdp.send('Page.setDownloadBehavior', {
        behavior: 'allow', downloadPath: downloadDir,
      })
    } catch {
      try {
        await cdp.send('Browser.setDownloadBehavior', {
          behavior: 'allow', downloadPath: downloadDir,
        })
      } catch { /* 下载目录可能由环境策略控制 */ }
    }

    const evalJs = async (fn, ...args) => {
      const expression = `(${fn.toString()})(${args.map((x) => JSON.stringify(x)).join(',')})`
      const r = await cdp.send('Runtime.evaluate', {
        expression, returnByValue: true, awaitPromise: true, userGesture: true,
      })
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || '页面脚本失败')
      return r.result.value
    }
    const bodyText = () => evalJs(() => document.body.innerText)
    const waitText = async (text, timeout = 20000) => {
      const start = Date.now()
      while (Date.now() - start < timeout) {
        if ((await bodyText()).includes(text)) return
        await sleep(150)
      }
      try { console.error('BODY_SNAPSHOT:', (await bodyText()).slice(-1200)) } catch { /* ignore */ }
      throw new Error(`等待文本超时：${text}`)
    }
    const click = async (label) => {
      const ok = await evalJs((text) => {
        const b = [...document.querySelectorAll('button')].find((x) => x.textContent?.trim() === text)
        if (!b) return false
        b.click(); return true
      }, label)
      if (!ok) throw new Error(`找不到按钮：${label}`)
    }
    const setUid = async (uid) => {
      await evalJs((u) => {
        const settings = { restSeconds: 90 }
        localStorage.setItem('fc-app-v1', JSON.stringify({
          uid: u, session: null, settings, offlineCount: 0,
        }))
      }, uid)
    }
    const goto = async (path) => {
      await cdp.send('Page.navigate', { url: `${WEB}${path}` })
      await sleep(700)
    }

    await goto('/')
    await setUid(uidA)
    await goto('/mine/settings')
    await waitText('完整备份与恢复')
    await click('完整导出我的数据（JSON）')
    // 等下载完成
    let file
    let lastSize = -1
    let stable = 0
    for (let i = 0; i < 200; i++) {
      const all = await readdir(downloadDir)
      const names = all.filter((n) => n.endsWith('.json'))
      if (names.length && !all.some((n) => n.endsWith('.crdownload'))) {
        const candidate = join(downloadDir, names[0])
        const size = (await import('node:fs/promises').then((m) => m.stat(candidate))).size
        if (size === lastSize && size > 0) stable += 1; else stable = 0
        lastSize = size
        if (stable >= 3) { file = candidate; break }
      }
      await sleep(150)
    }
    if (!file) throw new Error('导出下载未生成完整 JSON 文件')
    const exported = await import('node:fs/promises').then((m) => m.readFile(file, 'utf8'))
    if (!exported.includes('"schema_version"')) throw new Error('导出文件内容异常')
    // 切换到 B，恢复预览 → 确认导入
    await goto('/')
    await setUid(uidB)
    await goto('/mine/settings')
    await waitText('选择备份 JSON 并预览恢复')
    const doc = await cdp.send('DOM.getDocument')
    const input = await cdp.send('DOM.querySelector', {
      nodeId: doc.root.nodeId, selector: 'input[type=file]',
    })
    if (!input.nodeId) throw new Error('找不到备份文件输入框')
    await cdp.send('DOM.setFileInputFiles', { nodeId: input.nodeId, files: [file] })
    await evalJs(() => {
      const el = document.querySelector('input[type=file]')
      el?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await waitText('恢复预览')
    await waitText('确认导入')
    await click('确认导入')
    await waitText('导入完成', 30000)
    const importedApi = await request(`/api/users/${uidB}/checkins?limit=50`)
    if (!importedApi.checkins || importedApi.checkins.length < 1) {
      throw new Error('导入后 B 没有训练记录')
    }

    // 删除 B：输入 DELETE → 勾选 → 删除
    await evalJs(() => {
      const el = document.querySelector('input[placeholder="输入 DELETE 确认"]')
      if (!el) throw new Error('找不到删除确认输入框')
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
      setter.call(el, 'DELETE')
      el.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await evalJs(() => {
      const labels = [...document.querySelectorAll('label')]
      const label = labels.find((l) => l.textContent?.includes('我理解删除不可逆'))
      const box = label?.querySelector('input[type=checkbox]')
      if (!box) throw new Error('找不到删除确认勾选框')
      box.click()
    })
    await click('永久删除账户及个人数据')
    try {
      await waitText('怎么称呼你', 20000)
    } catch (e) {
      console.error('DELETE_BODY_SNAPSHOT:', await bodyText())
      throw e
    }
    const statusB = await fetch(`${API}/api/users/${uidB}/profile`)
    if (statusB.status !== 404) throw new Error(`B 删除后 profile 仍返回 ${statusB.status}`)
    const statusA = await fetch(`${API}/api/users/${uidA}/profile`)
    if (statusA.status !== 200) throw new Error(`A 被误删：${statusA.status}`)
    const local = await evalJs(() => Object.keys(localStorage))
    if (local.some((k) => k === 'fc-app-v1' || k.startsWith('fc-plan-'))) {
      throw new Error('删除后本地缓存未清理：' + local.join(','))
    }
    // 截图存证
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' })
    await writeFile(join(OUT, 'rc-fix-e2e-delete-welcome.png'),
                    Buffer.from(shot.data, 'base64'))
    console.log(JSON.stringify({
      ok: true, exported_file: file, uidA, uidB,
      b_deleted: true, a_intact: true, local_keys_after: local,
      screenshot: join(OUT, 'rc-fix-e2e-delete-welcome.png'),
    }, null, 1))
  } finally {
    try { launched?.cdp?.close() } catch { /* ignore */ }
    try { launched?.chrome?.kill('SIGTERM') } catch { /* ignore */ }
    try { web.kill('SIGTERM') } catch { /* ignore */ }
    try { server.kill('SIGTERM') } catch { /* ignore */ }
    try { if (launched?.profile) await rm(launched.profile, { recursive: true, force: true }) } catch { /* Chrome 尚未退出 */ }
    try { if (tmp) await rm(tmp, { recursive: true, force: true }) } catch { /* 保留供排查 */ }
  }
}

main().catch((e) => { console.error(e); process.exit(1) })
