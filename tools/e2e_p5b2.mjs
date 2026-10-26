import { spawn } from 'node:child_process'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const WEB = process.env.FC_E2E_WEB || 'http://127.0.0.1:5173'
const API = process.env.FC_E2E_API || 'http://127.0.0.1:18002'
const OUT = process.env.FC_E2E_SHOTS || 'docs/p5b2-shots'
const CDP_PORT = Number(process.env.FC_E2E_CDP_PORT || 9224)
const uid = `p5b2-e2e-${Date.now()}`
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function request(path, init = {}) {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
  let body = null
  try { body = await response.json() } catch { body = null }
  if (!response.ok) throw new Error(`${path}: ${response.status} ${JSON.stringify(body)}`)
  return body
}

const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) })
const patch = (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) })

async function seed() {
  await post(`/api/users/${uid}/onboarding`, {
    basic: { age: 30, gender: '男', height_cm: 175, weight_kg: 70 },
    goal: { primary: 'muscle_gain' },
    experience: { training_years: 2, recent_layoff_weeks: 0 },
    resources: { location: 'gym', days_per_week: 3, session_minutes: 60 },
    conditions: {
      injuries: [], injuries_evidence: '用户自述无伤病',
      health_screen: { heart: '无', pregnancy: '不适用', medication: '无', clearance: '无' },
      health_screen_evidence: '用户逐项作答',
    },
  })
  const places = await request(`/api/users/${uid}/locations`)
  const gym = places.locations.find((x) => x.name === '健身房')
  const home = places.locations.find((x) => x.name === '居家')
  await patch(`/api/users/${uid}/locations/${gym.id}`, {
    required_equipment: ['barbell', 'dumbbell', 'bench'], optional_equipment: [],
  })
  await patch(`/api/users/${uid}/locations/${home.id}`, {
    required_equipment: ['dumbbell', 'band', 'bench'], optional_equipment: [],
  })
  await post(`/api/users/${uid}/locations/${gym.id}/select`, {})
  const plan = await request(`/api/users/${uid}/plan`)
  const day = plan.content.schedule.find((d) =>
    d.exercises.some((x) => x.exercise_id === 'barbell_bench_press'))
  if (!day) throw new Error('初始计划中没有杠铃卧推')
  return { gym, home, day: day.day, plan }
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
  const profile = await mkdtemp(join(tmpdir(), 'coach-p5b2-chrome-'))
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
  const seeded = await seed()
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
    const bodyText = () => evaluate(() => document.body.innerText)
    const waitText = async (text, timeout = 15000) => {
      const started = Date.now()
      while (Date.now() - started < timeout) {
        if ((await bodyText()).includes(text)) return
        await sleep(150)
      }
      throw new Error(`等待文本超时：${text}`)
    }
    const click = async (label) => {
      const ok = await evaluate((text) => {
        const buttons = [...document.querySelectorAll('button')]
        const target = buttons.find((b) => b.textContent?.trim() === text)
          || buttons.find((b) => b.textContent?.includes(text))
        if (!target) return false
        target.click()
        return true
      }, label)
      if (!ok) throw new Error(`找不到按钮：${label}`)
      await sleep(150)
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
    const selectByLabel = async (label, value) => {
      const ok = await evaluate((aria, val) => {
        const el = [...document.querySelectorAll('select')]
          .find((node) => node.getAttribute('aria-label') === aria)
        if (!el) return false
        Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(el, val)
        el.dispatchEvent(new Event('change', { bubbles: true }))
        return true
      }, label, String(value))
      if (!ok) throw new Error(`找不到选择器：${label}`)
      await sleep(150)
    }
    const screenshot = async (name) => {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true })
      await writeFile(join(OUT, name), Buffer.from(shot.data, 'base64'))
    }
    const navigate = async (path, marker) => {
      await cdp.send('Page.navigate', { url: `${WEB}${path}` })
      await waitText(marker)
    }

    await cdp.send('Page.navigate', { url: `${WEB}/welcome` })
    await waitText('先认识一下你')
    await evaluate((id) => {
      localStorage.setItem('fc-app-v1', JSON.stringify({
        uid: id, session: null, settings: { restSeconds: 90 }, offlineCount: 0,
      }))
    }, uid)

    await navigate('/mine/locations', '训练地点与器械')
    await waitText('杠铃')
    await screenshot('01-locations-gym-home-config.png')

    const dayPath = `/workout/${encodeURIComponent(seeded.day)}`
    await navigate(dayPath, '杠铃平板卧推')
    await waitText('健身房')
    await sleep(500)
    await screenshot('02-gym-bench-available.png')

    await selectByLabel('当前训练地点', seeded.home.id)
    await waitText('缺少杠铃')
    await screenshot('03-home-bench-unavailable.png')

    await click('替换')
    await waitText('动作替代候选')
    await waitText('哑铃卧推')
    await screenshot('04-substitute-candidates.png')

    await click('仅本次训练替换')
    await waitText('哑铃卧推')
    await fill('重量', '20')
    await fill('次数', '10')
    await click('完成本组')
    await waitText('20 kg × 10 次')
    await screenshot('05-session-only-replaced.png')

    const planBefore = await request(`/api/users/${uid}/plan`)
    await click('完成训练（1 组）')
    await waitText('训练已保存')
    const checkin = (await request(`/api/users/${uid}/checkins?limit=1`)).checkins[0]
    const replaced = checkin.data.exercises[0]
    if (replaced.exercise_id !== 'dumbbell_bench_press'
        || replaced.session_replacement_of !== 'barbell_bench_press') {
      throw new Error(`本次替换落库错误：${JSON.stringify(replaced)}`)
    }
    const planAfterSession = await request(`/api/users/${uid}/plan`)
    if (planAfterSession.version !== planBefore.version
        || !planAfterSession.content.schedule.some((d) =>
          d.exercises.some((x) => x.exercise_id === 'barbell_bench_press'))) {
      throw new Error('仅本次替换意外修改了长期计划')
    }

    const restriction = await post(`/api/users/${uid}/training-restrictions`, {
      source_type: 'user_reported', source_evidence: '肩部发力不适，先避开哑铃卧推',
      restriction_description: '暂不做哑铃卧推',
      affected_activities: { regions: [], movements: ['dumbbell_bench_press'] },
    })
    await navigate(dayPath, '杠铃平板卧推')
    await waitText('缺少杠铃')
    await click('替换')
    await waitText('动作替代候选')
    await sleep(500)
    const restrictedCandidates = await bodyText()
    if (restrictedCandidates.includes('哑铃卧推')) {
      throw new Error('P3 限制下仍展示了受限替代候选')
    }
    await screenshot('06-p3-restricted-candidate-removed.png')
    const blocked = await fetch(
      `${API}/api/users/${uid}/exercise-substitutions/validate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_exercise_id: 'barbell_bench_press',
          target_exercise_id: 'dumbbell_bench_press',
          location_id: seeded.home.id,
        }),
      })
    if (blocked.status !== 422) throw new Error('P3 限制未阻止替代候选')

    await post(`/api/users/${uid}/training-restrictions/${restriction['id']}/lift`, {
      expected_revision: restriction.revision,
      lift_evidence: '肩部不适已缓解，逐步恢复并观察',
      reason: '验收解除限制',
    })
    await navigate(dayPath, '杠铃平板卧推')
    await waitText('缺少杠铃')
    await click('替换')
    await waitText('哑铃卧推')
    await click('提交长期计划修改')
    await waitText('已创建待确认修改')
    await screenshot('07-long-term-proposal-pending.png')
    const planPending = await request(`/api/users/${uid}/plan`)
    if (planPending.version !== planAfterSession.version) {
      throw new Error('待确认提案自动修改了计划')
    }
    await click('确认长期计划修改')
    await waitText('长期计划已确认更新')
    await screenshot('08-long-term-confirmed.png')
    const planFinal = await request(`/api/users/${uid}/plan`)
    if (planFinal.version !== planAfterSession.version + 1) {
      throw new Error('确认后长期计划版本未更新')
    }
    const monday = planFinal.content.schedule.find((d) => d.day === seeded.day)
    if (!monday.exercises.some((x) => x.exercise_id === 'dumbbell_bench_press')) {
      throw new Error('确认后长期计划未替换为哑铃卧推')
    }

    console.log(JSON.stringify({
      uid, screenshots: OUT,
      session_replacement: {
        exercise_id: replaced.exercise_id,
        session_replacement_of: replaced.session_replacement_of,
        plan_version_unchanged: planAfterSession.version,
      },
      p3_direct_validation_status: blocked.status,
      long_term_plan_version: planFinal.version,
    }, null, 2))
  } finally {
    cdp.close()
    chrome.kill('SIGTERM')
    await Promise.race([
      new Promise((resolve) => chrome.once('exit', resolve)),
      sleep(1500),
    ])
    await rm(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 })
      .catch(() => { /* 临时目录清理不影响验收 */ })
  }
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exitCode = 1
})
