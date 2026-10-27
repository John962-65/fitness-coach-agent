// RC-FIX-C 浏览器 E2E：洞察失效 + PersonalTrial 10 次观察/冻结复盘。
import { spawn, execFileSync } from 'node:child_process'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const REPO = process.cwd()
const API_PORT = Number(process.env.FC_E2E_API_PORT || 18086)
const WEB_PORT = Number(process.env.FC_E2E_WEB_PORT || 5182)
const CDP_PORT = Number(process.env.FC_E2E_CDP_PORT || 9230)
const OUT = process.env.FC_E2E_SHOTS || 'docs/rc-fix-shots'
const API = `http://127.0.0.1:${API_PORT}`
const WEB = `http://127.0.0.1:${WEB_PORT}`
const uid = `rcfix-c-${Date.now()}`
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
const get = (path) => request(path)

async function seed() {
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
  const plan = await get(`/api/users/${uid}/plan`)
  const ctx = { plan_id: plan.plan_id, plan_version: plan.version }
  const day = plan.content.schedule.find((d) =>
    d.exercises.some((x) => x.exercise_id === 'barbell_bench_press'))
  const index = day.exercises.findIndex((x) => x.exercise_id === 'barbell_bench_press')
  const planCtx = { ...ctx, planned_day: day.day, index,
                    planned_exercise_id: 'barbell_bench_press' }
  const save = async (offset) => post(`/api/users/${uid}/checkins`, {
    type: 'training', data: {
      exercises: [{ name: '杠铃平板卧推', exercise_id: 'barbell_bench_press',
                    set_logs: Array(4).fill({ type: 'weight_reps',
                                              weight_kg: 60, reps: 12 }) }],
      session_meta: { mode: 'free',
        local_date: new Date(Date.now() - offset * 86400000).toISOString().slice(0, 10) },
    },
  })
  await save(6); await save(2)
  const analysis = await post(`/api/users/${uid}/experts/analysis`, {
    specialist: 'training_science', task_type: 'next-training-review',
    params: { exercise_id: 'barbell_bench_press', ...planCtx },
  })
  const insight = analysis.insight
  await save(0) // 新增相关训练 → 旧洞察应失效
  const stale = await get(`/api/users/${uid}/expert-insights/${insight.id}`)
  if (stale.status !== 'invalidated') {
    throw new Error(`洞察未失效：${stale.status}`)
  }
  const trial = await post(`/api/users/${uid}/trials`, {
    change_desc: '卧推尝试', reason: 'E2E', observe: '完成次数',
    stop_rule: '10 次', review_days: 1,
  })
  return { insight, trial_id: trial.trial_id }
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

async function launchChrome() {
  const profile = await mkdtemp(join(tmpdir(), 'coach-rcfixc-chrome-'))
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
  const tmp = await mkdtemp(join(tmpdir(), 'coach-rcfixc-'))
  const dbPath = join(tmp, 'e2e.db')
  await mkdir(OUT, { recursive: true })
  const serverCode = `
from pathlib import Path
from backend.app import create_app
import uvicorn
app = create_app(db_path=Path(r"${dbPath}"))
uvicorn.run(app, host="127.0.0.1", port=${API_PORT}, log_level="warning")
`
  const server = spawn('python3', ['-c', serverCode], {
    cwd: REPO, stdio: 'ignore', env: { ...process.env, FAKE_LLM: '1' },
  })
  const web = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1',
    '--port', String(WEB_PORT), '--strictPort'], {
    cwd: join(REPO, 'frontend'), stdio: 'ignore',
    env: { ...process.env, FC_API_TARGET: API },
  })
  let launched
  try {
    await waitFetch(`${API}/api/health`)
    const seeded = await seed()
    // 给 /trials 的通用 API 补上动作/观察指标（E2E 夹具，不改变产品 API）
    execFileSync('python3', ['-c', `
from pathlib import Path
import json
from coach.db import Database
db = Database(Path(r"${dbPath}"))
db.conn.execute("UPDATE personal_trials SET exercise_id=?, observation_metric=?,"
                " chosen_target=?, min_sessions=?, observation_window_days=?"
                " WHERE user_id=? AND status='active'",
                ("barbell_bench_press", "target-completion",
                 json.dumps({"sets": 4, "reps": "12", "weight_kg": 60}),
                 "10", "30", "${uid}"))
db.conn.commit()
`], { cwd: REPO, stdio: 'ignore' })
    for (let i = 0; i < 10; i++) {
      await post(`/api/users/${uid}/checkins`, {
        type: 'training', data: {
          exercises: [{ name: '杠铃平板卧推', exercise_id: 'barbell_bench_press',
                        set_logs: Array(4).fill({ type: 'weight_reps',
                                                  weight_kg: 60, reps: 12 }) }],
          session_meta: { mode: 'free',
            local_date: new Date().toISOString().slice(0, 10) },
        },
      })
    }
    await waitFetch(WEB)
    launched = await launchChrome()
    const { cdp } = launched
    await cdp.open()
    await cdp.send('Page.enable')
    await cdp.send('Runtime.enable')
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 390, height: 844, deviceScaleFactor: 1, mobile: true,
    })
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
      try { console.error('BODY_SNAPSHOT:', (await bodyText()).slice(-1600)) } catch { /* ignore */ }
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
    const clickStarts = async (text) => {
      const ok = await evalJs((prefix) => {
        const b = [...document.querySelectorAll('button')]
          .find((x) => (x.textContent || '').trim().startsWith(prefix))
        if (!b) return false
        b.click(); return true
      }, text)
      if (!ok) throw new Error(`找不到以「${text}」开头的按钮`)
    }
    const setUid = async (u) => evalJs((value) => {
      localStorage.setItem('fc-app-v1', JSON.stringify({
        uid: value, session: null, settings: { restSeconds: 90 }, offlineCount: 0,
      }))
    }, u)
    const goto = async (path) => {
      await cdp.send('Page.navigate', { url: `${WEB}${path}` })
      await sleep(700)
    }

    await goto('/')
    await setUid(uid)
    await goto(`/experts/training?insight=${seeded.insight.id}`)
    await waitText('已失效')
    await goto('/mine')
    await waitText('个人尝试')
    await clickStarts('查看观察进展')
    await waitText('观察期内 10 次训练')
    if (!(await bodyText()).includes('尝试期间：10 次训练')) {
      await click('生成复盘草稿')
    }
    await waitText('尝试期间：10 次训练')
    await click('保留当前安排')
    for (let i = 0; i < 20; i++) {
      const t = await get(`/api/users/${uid}/trials/${seeded.trial_id}`)
      if (t.trial.status === 'ended') break
      await sleep(200)
    }
    const endedTrial = await get(`/api/users/${uid}/trials/${seeded.trial_id}`)
    if (endedTrial.trial.status !== 'ended') {
      throw new Error('决策后尝试未结束')
    }
    // 结束后新增训练，冻结复盘仍只包含 10 次
    await post(`/api/users/${uid}/checkins`, {
      type: 'training', data: {
        exercises: [{ name: '杠铃平板卧推', exercise_id: 'barbell_bench_press',
                      set_logs: Array(4).fill({ type: 'weight_reps',
                                                weight_kg: 60, reps: 12 }) }],
        session_meta: { mode: 'free', local_date: new Date().toISOString().slice(0, 10) },
      },
    })
    const detail = await get(`/api/users/${uid}/trials/${seeded.trial_id}?review=1`)
    if (detail.review?.frozen !== true || detail.review?.observation?.sessions_total !== 10) {
      throw new Error('结束后的复盘未冻结或次数不是 10')
    }
    const shot = await cdp.send('Page.captureScreenshot', { format: 'png' })
    await writeFile(join(OUT, 'rc-fix-e2e-trial-frozen.png'),
                    Buffer.from(shot.data, 'base64'))
    console.log(JSON.stringify({
      ok: true, uid, insight_invalidated: true,
      trial_id: seeded.trial_id, trial_sessions: 10,
      review_frozen: true,
      screenshot: join(OUT, 'rc-fix-e2e-trial-frozen.png'),
    }, null, 1))
  } finally {
    try { launched?.cdp?.close() } catch { /* ignore */ }
    try { launched?.chrome?.kill('SIGTERM') } catch { /* ignore */ }
    try { web.kill('SIGTERM') } catch { /* ignore */ }
    try { server.kill('SIGTERM') } catch { /* ignore */ }
    try { if (launched?.profile) await rm(launched.profile, { recursive: true, force: true }) } catch { /* ignore */ }
    try { await rm(tmp, { recursive: true, force: true }) } catch { /* ignore */ }
  }
}

main().catch((e) => { console.error(e); process.exit(1) })
