import { spawn } from 'node:child_process'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const WEB = process.env.FC_E2E_WEB || 'http://127.0.0.1:5173'
const API = process.env.FC_E2E_API || 'http://127.0.0.1:18001'
const OUT = process.env.FC_E2E_SHOTS || 'docs/p5b11-shots'
const CDP_PORT = Number(process.env.FC_E2E_CDP_PORT || 9223)
const uid = `p5b11-e2e-${Date.now()}`
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function request(path, init = {}) {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
  const body = await response.json()
  if (!response.ok) throw new Error(`${path}: ${response.status} ${JSON.stringify(body)}`)
  return body
}

async function seed() {
  await request(`/api/users/${uid}/onboarding`, { method: 'POST', body: JSON.stringify({
    basic: { age: 30, gender: '男', height_cm: 175, weight_kg: 70 },
    goal: { primary: 'health' },
    experience: { training_years: 1, recent_layoff_weeks: 0 },
    resources: { location: 'gym', days_per_week: 3, session_minutes: 60 },
    conditions: {
      injuries: [], injuries_evidence: '用户自述无伤病',
      health_screen: { heart: '无', pregnancy: '不适用', medication: '无', clearance: '无' },
      health_screen_evidence: '用户逐项作答',
    },
  }) })
  await request(`/api/users/${uid}/training-templates`, { method: 'POST', body: JSON.stringify({
    name: 'A 卧推跑步', entries: [
      { exercise_id: 'barbell_bench_press', name: '杠铃平板卧推', measurement: 'weight_reps' },
      { exercise_id: 'running', name: '跑步', measurement: 'distance_time', activity: 'cardio' },
    ],
  }) })
  await request(`/api/users/${uid}/training-templates`, { method: 'POST', body: JSON.stringify({
    name: 'C HIIT 模板', entries: [],
    hiit: {
      name: 'C HIIT 模板', exercise_id: 'jumping_jack',
      blocks: [{ name: '开合跳', exercise_id: 'jumping_jack',
        work_seconds: 30, rest_seconds: 10, rounds: 2 }],
    },
    hiit_index: 0,
  }) })
  return (await request(`/api/users/${uid}/training-templates`)).templates
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
      const pending = this.pending.get(msg.id)
      if (!pending) return
      this.pending.delete(msg.id)
      if (msg.error) pending.reject(new Error(msg.error.message))
      else pending.resolve(msg.result)
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
  const profile = await mkdtemp(join(tmpdir(), 'coach-p5b11-chrome-'))
  const chrome = spawn('google-chrome', [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
    '--remote-allow-origins=*', `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profile}`, '--window-size=390,844', 'about:blank',
  ], { stdio: 'ignore' })
  for (let i = 0; i < 100; i++) {
    try {
      const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json`).then((r) => r.json())
      const page = targets.find((target) => target.type === 'page')
      if (page) return { chrome, profile, cdp: new Cdp(page.webSocketDebuggerUrl) }
    } catch { /* Chrome 尚未就绪 */ }
    await sleep(100)
  }
  throw new Error('Chrome DevTools 未就绪')
}

async function main() {
  const templates = await seed()
  await mkdir(OUT, { recursive: true })
  const { chrome, profile, cdp } = await launchChrome()
  try {
    await cdp.open()
    await cdp.send('Page.enable')
    await cdp.send('Runtime.enable')
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 390, height: 844, deviceScaleFactor: 1, mobile: true,
    })

    const evaluate = async (fn, ...args) => {
      const expression = `(${fn.toString()})(${args.map((x) => JSON.stringify(x)).join(',')})`
      const result = await cdp.send('Runtime.evaluate', {
        expression, returnByValue: true, awaitPromise: true, userGesture: true,
      })
      if (result.exceptionDetails) {
        throw new Error(result.exceptionDetails.exception?.description || '页面脚本失败')
      }
      return result.result.value
    }
    const waitText = async (text, timeout = 15000) => {
      const started = Date.now()
      while (Date.now() - started < timeout) {
        if (await evaluate(() => document.body.innerText, ).then((body) => body.includes(text))) return
        await sleep(150)
      }
      throw new Error(`等待文本超时：${text}`)
    }
    const click = async (text) => {
      const ok = await evaluate((label) => {
        const buttons = [...document.querySelectorAll('button')]
        const exact = buttons.find((b) => b.textContent?.trim() === label)
        const target = exact || buttons.find((b) => b.textContent?.includes(label))
        if (!target) return false
        target.click()
        return true
      }, text)
      if (!ok) throw new Error(`找不到按钮：${text}`)
      await sleep(120)
    }
    const fill = async (placeholder, value) => {
      const ok = await evaluate((ph, val) => {
        const el = [...document.querySelectorAll('input,textarea')]
          .find((node) => node.getAttribute('placeholder')?.includes(ph))
        if (!el) return false
        const proto = el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val)
        el.dispatchEvent(new Event('input', { bubbles: true }))
        el.dispatchEvent(new Event('change', { bubbles: true }))
        return true
      }, placeholder, value)
      if (!ok) throw new Error(`找不到输入框：${placeholder}`)
      await sleep(120)
    }
    const fillLabel = async (label, value) => {
      const ok = await evaluate((text, val) => {
        const wrapper = [...document.querySelectorAll('label')]
          .find((node) => node.innerText.includes(text))
        const el = wrapper?.querySelector('input,textarea')
        if (!el) return false
        const proto = el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val)
        el.dispatchEvent(new Event('input', { bubbles: true }))
        el.dispatchEvent(new Event('change', { bubbles: true }))
        return true
      }, label, value)
      if (!ok) throw new Error(`找不到带标签输入框：${label}`)
      await sleep(120)
    }
    const choose = async (value) => {
      const ok = await evaluate((val) => {
        const el = document.querySelector('select')
        if (!el) return false
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, val)
        el.dispatchEvent(new Event('change', { bubbles: true }))
        return true
      }, value)
      if (!ok) throw new Error(`找不到选择器：${value}`)
      await sleep(120)
    }
    const screenshot = async (name) => {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
      await writeFile(join(OUT, name), Buffer.from(shot.data, 'base64'))
    }
    const navigate = async (path, marker) => {
      await cdp.send('Page.navigate', { url: `${WEB}${path}` })
      await waitText(marker)
    }
    const reload = async (marker) => {
      await cdp.send('Page.reload', { ignoreCache: true })
      await waitText(marker)
    }

    await cdp.send('Page.navigate', { url: `${WEB}/welcome` })
    await waitText('先认识一下你')
    await evaluate((id) => {
      localStorage.setItem('fc-app-v1', JSON.stringify({
        uid: id, session: null, settings: { restSeconds: 90 }, offlineCount: 0,
      }))
    }, uid)

    const a = templates.find((t) => t.name === 'A 卧推跑步')
    const c = templates.find((t) => t.name === 'C HIIT 模板')
    await navigate(`/workout/template/${a.id}`, '杠铃平板卧推')
    await waitText('开始有氧')
    await screenshot('01-A-template-bench-running-idle.png')
    await fill('重量', '60')
    await fill('次数', '10')
    await click('完成本组')
    await waitText('60 kg × 10 次')
    await sleep(1200)
    await click('开始有氧')
    await sleep(2500)
    await click('结束')
    await waitText('记录本次有氧')
    await fillLabel('距离（米', '5000')
    const actualSeconds = await evaluate(() => {
      const input = [...document.querySelectorAll('input')]
        .find((node) => node.closest('label')?.innerText.includes('实际用时'))
      return Number(input?.value || 0)
    })
    if (actualSeconds < 2 || actualSeconds > 6) {
      throw new Error(`有氧计时包含了未开始阶段：${actualSeconds}s`)
    }
    await click('记录本次有氧')
    await waitText('已记录到本会话')
    await screenshot('02-A-cardio-finished.png')
    await click('完成训练（2 组）')
    await waitText('训练已保存')
    const checkinsA = (await request(`/api/users/${uid}/checkins?limit=5`)).checkins
    const cardio = checkinsA[0].data.exercises.find((ex) => ex.exercise_id === 'running')
    if (cardio.set_logs[0].duration_seconds !== actualSeconds) {
      throw new Error('有氧落库时长与页面计时不一致')
    }

    await navigate(`/workout/template/${c.id}`, 'C HIIT 模板')
    await waitText('未开始')
    await sleep(1600)
    if ((await evaluate(() => document.body.innerText)).includes('工作阶段')) {
      throw new Error('HIIT 模板载入后自动开始')
    }
    await screenshot('03-C-hiit-template-idle.png')

    await click('开始间歇训练')
    await waitText('工作阶段')
    await sleep(1000)
    await click('暂停')
    await waitText('已暂停')
    await reload('已暂停')
    await screenshot('04-B-hiit-paused-after-refresh.png')
    await click('恢复')
    await waitText('工作阶段')
    await click('跳过阶段')
    await click('提前结束')
    await waitText('已提前结束')
    await screenshot('05-B-hiit-stopped-early.png')
    await click('完成训练（1 组）')
    await waitText('训练已保存')
    const checkinsB = (await request(`/api/users/${uid}/checkins?limit=5`)).checkins
    const hiitB = checkinsB[0].data.exercises[0].set_logs[0].hiit
    if (hiitB.completed_rounds !== 0 || hiitB.skipped.length !== 1) {
      throw new Error('HIIT 跳过/完成轮次落库不一致')
    }

    await navigate('/workout/free', '自由训练')
    await click('HIIT')
    await waitText('请选择已收录动作')
    await click('自定义活动')
    await fillLabel('计划名称', 'D 波比循环')
    await fill('如 波比跳', '波比跳')
    await fillLabel('工作（秒）', '30')
    await fillLabel('休息（秒）', '10')
    await fillLabel('轮次', '2')
    await screenshot('06-D-custom-hiit-planner.png')
    await click('开始间歇训练')
    await waitText('工作阶段')
    await click('提前结束')
    await waitText('已提前结束')
    await screenshot('07-D-custom-hiit-result.png')
    await click('完成训练（1 组）')
    await waitText('训练已保存')
    const checkinsD = (await request(`/api/users/${uid}/checkins?limit=5`)).checkins
    const custom = checkinsD[0].data.exercises[0]
    if (custom.exercise_id !== 'custom_hiit' || custom.name !== 'D 波比循环') {
      throw new Error(`自定义间歇身份错误：${custom.exercise_id}/${custom.name}`)
    }
    const block = custom.set_logs[0].hiit.blocks[0]
    if (block.exercise_id !== 'custom_hiit' || block.name !== '波比跳') {
      throw new Error(`自定义间歇块身份错误：${block.exercise_id}/${block.name}`)
    }

    console.log(JSON.stringify({
      uid, screenshots: OUT,
      cardio_seconds: actualSeconds,
      hiit_skipped: hiitB.skipped.length,
      custom_identity: { exercise_id: custom.exercise_id, name: custom.name,
        block_name: block.name },
    }, null, 2))
  } finally {
    cdp.close()
    chrome.kill('SIGTERM')
    await Promise.race([
      new Promise((resolve) => chrome.once('exit', resolve)),
      sleep(1500),
    ])
    await rm(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 })
      .catch(() => { /* Chrome 退出后临时目录清理失败不影响验收结果 */ })
  }
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exitCode = 1
})
