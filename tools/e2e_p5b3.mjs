import { spawn } from 'node:child_process'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const WEB = process.env.FC_E2E_WEB || 'http://127.0.0.1:5173'
const API = process.env.FC_E2E_API || 'http://127.0.0.1:18003'
const OUT = process.env.FC_E2E_SHOTS || 'docs/p5b3-shots'
const CDP_PORT = Number(process.env.FC_E2E_CDP_PORT || 9225)
const uid = `p5b3-e2e-${Date.now()}`
const today = new Date()
const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
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
const post = (path, body = {}) => request(path, {
  method: 'POST', body: JSON.stringify(body),
})
const patch = (path, body) => request(path, {
  method: 'PATCH', body: JSON.stringify(body),
})

function mixedPayload(plan) {
  const hiit = {
    name: "四轮间歇", exercise_id: "custom_hiit",
    blocks: [{ name: "开合跳", exercise_id: "jumping_jack",
      work_seconds: 30, rest_seconds: 30, rounds: 4 }],
    planned_rounds: 4, completed_rounds: 3,
    work_seconds_done: 84, rest_seconds_done: 66,
    skipped: [{ block: 0, round: 4 }], ended_early: true,
    end_reason: "时间不够",
  }
  return {
    exercises: [
      { name: "杠铃平板卧推", exercise_id: "barbell_bench_press",
        set_logs: Array(3).fill({ type: "weight_reps", weight_kg: 60, reps: 10 }) },
      { name: "杠铃划船", exercise_id: "barbell_row",
        set_logs: Array(3).fill({ type: "weight_reps", weight_kg: 50, reps: 10 }) },
      { name: "跑步", exercise_id: "running", set_logs: [{
        type: "distance_time", distance_m: 5000, duration_seconds: 1200, rpe: 6 }] },
      { name: "四轮间歇", exercise_id: "custom_hiit",
        set_logs: [{ type: "duration", duration_seconds: 150, hiit }] },
    ],
    session_meta: { mode: "free", local_date: localDate },
  }
}

async function seed() {
  await post(`/api/users/${uid}/onboarding`, {
    basic: { age: 30, gender: "男", height_cm: 175, weight_kg: 70 },
    goal: { primary: "muscle_gain" },
    experience: { training_years: 2, recent_layoff_weeks: 0 },
    resources: { location: "gym", days_per_week: 3, session_minutes: 60 },
    conditions: {
      injuries: [], injuries_evidence: "用户自述无伤病",
      health_screen: { heart: "无", pregnancy: "不适用", medication: "无", clearance: "无" },
      health_screen_evidence: "用户逐项作答",
    },
  })
  const plan = await request(`/api/users/${uid}/plan`)
  const day = plan.content.schedule.find((d) =>
    d.exercises.some((x) => x.exercise_id === "barbell_bench_press"))
  const benchIndex = day.exercises.findIndex(
    (x) => x.exercise_id === "barbell_bench_press")
  const mixed = await post(`/api/users/${uid}/checkins`, {
    type: "training", data: mixedPayload(plan),
  })
  const replacement = await post(`/api/users/${uid}/checkins`, {
    type: "training", data: {
      exercises: [{
        name: "哑铃卧推", exercise_id: "dumbbell_bench_press",
        session_replacement_of: "barbell_bench_press",
        session_replacement: {
          planned_exercise_id: "barbell_bench_press",
          planned_name: "杠铃平板卧推", planned_index: benchIndex,
          actual_exercise_id: "dumbbell_bench_press",
          actual_measurement: "weight_reps", scope: "session",
        },
        set_logs: [{ type: "weight_reps", weight_kg: 20, reps: 10 }],
      }],
      session_meta: {
        mode: "planned", day: day.day, local_date: localDate,
        plan_id: plan.plan_id, plan_version: plan.version,
      },
    },
  })
  return { plan, day, benchIndex, mixedId: mixed.id, replacementId: replacement.id }
}

class Cdp {
  constructor(url) { this.url = url; this.id = 0; this.pending = new Map() }
  async open() {
    this.ws = new WebSocket(this.url)
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true })
      this.ws.addEventListener("error", reject, { once: true })
    })
    this.ws.addEventListener("message", (event) => {
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
  const profile = await mkdtemp(join(tmpdir(), "coach-p5b3-chrome-"))
  const chrome = spawn("google-chrome", [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
    "--remote-allow-origins=*", `--remote-debugging-port=${CDP_PORT}`,
    `--user-data-dir=${profile}`, "--window-size=390,844", "about:blank",
  ], { stdio: "ignore" })
  for (let i = 0; i < 100; i++) {
    try {
      const targets = await fetch(`http://127.0.0.1:${CDP_PORT}/json`).then((r) => r.json())
      const page = targets.find((target) => target.type === "page")
      if (page) return { chrome, profile, cdp: new Cdp(page.webSocketDebuggerUrl) }
    } catch { /* Chrome 尚未就绪 */ }
    await sleep(100)
  }
  throw new Error("Chrome DevTools 未就绪")
}

async function main() {
  const seeded = await seed()
  const planBefore = await request(`/api/users/${uid}/plan`)
  await mkdir(OUT, { recursive: true })
  const { chrome, profile, cdp } = await launchChrome()
  try {
    await cdp.open()
    await cdp.send("Page.enable")
    await cdp.send("Runtime.enable")
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: 390, height: 844, deviceScaleFactor: 1, mobile: true,
    })

    const evaluate = async (fn, ...args) => {
      const expression = `(${fn.toString()})(${args.map((x) => JSON.stringify(x)).join(",")})`
      const result = await cdp.send("Runtime.evaluate", {
        expression, returnByValue: true, awaitPromise: true, userGesture: true,
      })
      if (result.exceptionDetails) {
        throw new Error(result.exceptionDetails.exception?.description || "页面脚本失败")
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
        const buttons = [...document.querySelectorAll("button")]
        const target = buttons.find((b) => b.textContent?.trim() === text)
          || buttons.find((b) => b.textContent?.includes(text))
        if (!target) return false
        target.click()
        return true
      }, label)
      if (!ok) throw new Error(`找不到按钮：${label}`)
      await sleep(180)
    }
    const clickWithin = async (containerText, label) => {
      const ok = await evaluate((needle, text) => {
        const cards = [...document.querySelectorAll(".card")]
          .filter((c) => c.innerText.includes(needle))
        for (const card of cards) {
          const button = [...card.querySelectorAll("button")]
            .find((b) => b.textContent?.includes(text))
          if (button) { button.click(); return true }
        }
        return false
      }, containerText, label)
      if (!ok) throw new Error(`在「${containerText}」中找不到按钮：${label}`)
      await sleep(180)
    }
    const setAria = async (label, value) => {
      const ok = await evaluate((aria, val) => {
        const el = [...document.querySelectorAll("input")]
          .find((node) => node.getAttribute("aria-label") === aria)
        if (!el) return false
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, val)
        el.dispatchEvent(new Event("input", { bubbles: true }))
        el.dispatchEvent(new Event("change", { bubbles: true }))
        return true
      }, label, value)
      if (!ok) throw new Error(`找不到输入：${label}`)
      await sleep(120)
    }
    const fillPlaceholder = async (needle, value) => {
      const ok = await evaluate((ph, val) => {
        const el = [...document.querySelectorAll("input,textarea")]
          .find((node) => node.getAttribute("placeholder")?.includes(ph))
        if (!el) return false
        const proto = el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(proto, "value").set.call(el, val)
        el.dispatchEvent(new Event("input", { bubbles: true }))
        el.dispatchEvent(new Event("change", { bubbles: true }))
        return true
      }, needle, value)
      if (!ok) throw new Error(`找不到输入框：${needle}`)
      await sleep(120)
    }
    const scrollToText = async (text) => {
      await evaluate((needle) => {
        const el = [...document.querySelectorAll("body *")]
          .find((node) => node.children.length === 0
            && node.textContent?.includes(needle))
        el?.scrollIntoView({ block: "center" })
      }, text)
      await sleep(180)
    }
    const screenshot = async (name) => {
      const shot = await cdp.send("Page.captureScreenshot", { format: "png", fromSurface: true })
      await writeFile(join(OUT, name), Buffer.from(shot.data, "base64"))
    }
    const navigate = async (path, marker) => {
      await cdp.send("Page.navigate", { url: `${WEB}${path}` })
      await waitText(marker)
    }

    await cdp.send("Page.navigate", { url: `${WEB}/welcome` })
    await waitText("先认识一下你")
    await evaluate((id) => {
      localStorage.setItem("fc-app-v1", JSON.stringify({
        uid: id, session: null, settings: { restSeconds: 90 }, offlineCount: 0,
      }))
    }, uid)

    await navigate("/history", "训练历史")
    await clickWithin("跑步", "纠错这条记录")
    await waitText("逐组纠错")
    await setAria("第 1 组米", "6000")
    await fillPlaceholder("纠错原因", "实际距离是 6 公里")
    await screenshot("01-history-correction.png")
    await click("保存纠错")
    await waitText("修订 v1")

    // API：纠错后的历史、月历、周期、动作统计与事实一致
    const checkins = (await request(`/api/users/${uid}/checkins?limit=10`)).checkins
    const mixed = checkins.find((x) => x.id === seeded.mixedId)
    if (mixed.revision !== 1) throw new Error("历史纠错版本未更新")
    const runLog = mixed.data.exercises.find((x) => x.exercise_id === "running")
      .set_logs[0]
    if (runLog.distance_m !== 6000) throw new Error("历史距离未更新")

    const [period, calendar, facts] = await Promise.all([
      request(`/api/users/${uid}/period-summary?days=30`),
      request(`/api/users/${uid}/training-calendar?year=${today.getFullYear()}&month=${today.getMonth() + 1}`),
      request(`/api/users/${uid}/training-facts?window_days=30`),
    ])
    const expected = {
      training_sessions: 2, strength_working_sets: 7,
      steady_cardio_seconds: 1200, steady_cardio_distance_m: 6000,
      interval_work_seconds: 84, interval_rest_seconds: 66,
      interval_elapsed_seconds: 150,
    }
    for (const [key, value] of Object.entries(expected)) {
      if (period[key] !== value) throw new Error(`周期 ${key}=${period[key]} != ${value}`)
    }
    const day = calendar.days.find((d) => d.date === localDate)
    for (const key of Object.keys(expected)) {
      if (key === "training_sessions" && day[key] !== 2) {
        throw new Error(`月历 ${key}=${day[key]} != 2`)
      }
      if (day[key] !== period[key]) throw new Error(`月历/周期不一致：${key}`)
    }
    const sessionFacts = Object.fromEntries(facts.facts
      .filter((f) => f.measurement_type === "session"
        && Object.keys(expected).includes(f.metric))
      .map((f) => [f.metric, f.value]))
    for (const [key, value] of Object.entries(expected)) {
      if (sessionFacts[key] !== value) {
        throw new Error(`事实 ${key}=${sessionFacts[key]} != ${value}`)
      }
    }
    if (facts.facts.some((f) => f.metric === "interval-work-seconds"
      && f.measurement_type === "session" && f.value === 150)) {
      throw new Error("HIIT 总经过时长被误当成工作时长")
    }

    const dumbbell = await request(
      `/api/users/${uid}/exercise-stats/dumbbell_bench_press`)
    const bench = await request(`/api/users/${uid}/exercise-stats/barbell_bench_press`)
    if (dumbbell.sessions.length !== 1 || bench.sessions.length !== 1) {
      throw new Error("替代动作历史归类错误")
    }
    if (dumbbell.sessions[0].replacement?.planned_exercise_id
        !== "barbell_bench_press") {
      throw new Error("替换历史缺少原计划动作")
    }
    const planAfter = await request(`/api/users/${uid}/plan`)
    if (planAfter.version !== planBefore.version) {
      throw new Error("临时替换修改了长期计划")
    }

    // 旧洞察失效并重新分析最新修订
    let oldInsight = null
    for (let i = 0; i < 40 && !oldInsight; i++) {
      const list = await request(`/api/users/${uid}/expert-insights?limit=20`)
      for (const item of list.insights) {
        const detail = await request(`/api/users/${uid}/expert-insights/${item.id}`)
        if (detail.source_revision?.checkins?.[String(seeded.mixedId)] !== undefined) {
          oldInsight = detail
          break
        }
      }
      if (!oldInsight) await sleep(250)
    }
    if (!oldInsight) throw new Error("未找到混合训练洞察")
    if (oldInsight.status !== "invalidated") {
      throw new Error(`旧洞察未失效：${oldInsight.status}`)
    }
    const regenerated = await post(
      `/api/users/${uid}/expert-insights/${oldInsight.id}/regenerate`)
    if (regenerated.insight?.source_revision?.checkins?.[String(seeded.mixedId)] !== 1) {
      throw new Error("新分析未引用纠错后的修订版本")
    }

    // 月历与周期统计页面
    await click("日历与统计")
    await waitText("持续性有氧")
    await scrollToText("持续性有氧")
    await screenshot("02-calendar-period-stats.png")
    await scrollToText("HIIT 工作")
    await screenshot("03-hiit-period-stats.png")

    // 替换记录页面
    await click("记录列表")
    await waitText("原计划：")
    await scrollToText("原计划：")
    await screenshot("04-replacement-history.png")

    // P3 安全门（先配置一个可执行哑铃卧推的当前地点，确保阻断来自限制而非器械）
    const places = await request(`/api/users/${uid}/locations`)
    const gym = places.locations.find((x) => x.kind === "gym")
    await patch(`/api/users/${uid}/locations/${gym.id}`, {
      required_equipment: ["barbell", "dumbbell", "bench"],
      optional_equipment: [],
    })
    await post(`/api/users/${uid}/locations/${gym.id}/select`, {})
    const restriction = await post(`/api/users/${uid}/training-restrictions`, {
      source_type: "user_reported",
      source_evidence: "肩部不适，先避开哑铃卧推",
      restriction_description: "暂不做哑铃卧推",
      affected_activities: { regions: [], movements: ["dumbbell_bench_press"] },
    })
    const blocked = await fetch(
      `${API}/api/users/${uid}/exercise-substitutions/validate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_exercise_id: "barbell_bench_press",
          target_exercise_id: "dumbbell_bench_press",
        }),
      })
    if (blocked.status !== 422) throw new Error("P3 限制未阻止替代")
    await post(`/api/users/${uid}/training-restrictions/${restriction.id}/lift`, {
      expected_revision: restriction.revision,
      lift_evidence: "肩部不适已缓解，逐步恢复",
      reason: "验收解除",
    })

    console.log(JSON.stringify({
      uid, screenshots: OUT, mixed_checkin: seeded.mixedId,
      corrected_revision: mixed.revision, metrics: expected,
      old_insight: oldInsight.id, old_status: oldInsight.status,
      new_insight_revision:
        regenerated.insight.source_revision.checkins[String(seeded.mixedId)],
      replacement: dumbbell.sessions[0].replacement,
      p3_validation_status: blocked.status,
      plan_version_unchanged: planAfter.version,
    }, null, 2))
  } finally {
    cdp.close()
    chrome.kill("SIGTERM")
    await Promise.race([
      new Promise((resolve) => chrome.once("exit", resolve)),
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
