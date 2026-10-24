# 任务书 2.0 —— 后端做扎实（2026-10-24）

> 依据：发起人 2026-10-24 提供《Fitness Coach 2.0 最终产品设计与工程改造计划》V1.0，
> 原文已逐字节归档为 `DESIGN_2.0.md`（下称"2.0 标准"）。
> 发起人本轮指令：**"按照现在给你的 2.0 为标准，根据现在项目情况形成新的任务书 2.0 版，
> 按照新的任务书完成，暂时不做前端，把后端做扎实。"**
>
> 本文件是本轮开发的范围契约与验收依据；与 1.0 时代的差异以此为准。
> 沿用既有纪律：离线回归（临时库 / FAKE_LLM / 禁网）、冻结评测集不动、
> 真实 LLM 调用数为零、留痕写入 `PROGRESS.md`。

---

## 一、范围裁定

### 1.1 本轮做（后端）

对应 2.0 标准 §十六 任务 1–5、8 的后端部分，即 M0 全部 + M1 的服务层：

| 任务 | 2.0 出处 | 本轮交付 |
|---|---|---|
| B0 标准与契约落库 | §十六任务1 | `DESIGN_2.0.md` 归档 + 本任务书 + `DESIGN.md` 第 28 章指针 |
| B1 TrainingApproach 域模型 | §二、§十一、M0 任务2/3 | 新表 `training_approach` / `approach_revisions`，维度独立修改，版本历史可恢复，从现有数据受测迁移 |
| B2 统一修改协议 | §四、M0 任务4 | `ChangeProposal → Validation → Commit`：手动直通、AI 需确认，同套校验，单事务提交，版本冲突拒绝 |
| B3 计划手动编辑后端 | §4.1、M1 计划编辑器（无 UI） | 增/删/替换动作、组次/重量/备注编辑、排序、改日名，走 B2 协议出计划新版本 |
| B4 FastAPI 服务层 | §10.2、§十六任务5 | `backend/` 封装现有核心：档案 / 今日 / 训练方式 / 计划与编辑 / 打卡与纠错 / 动作库 / AI 对话；CLI 保留为调试入口 |
| B5 验证与留痕 | §十四 | 新增测试 + 全量回归全绿 + PROGRESS/README/requirements 同步 |

### 1.2 本轮不做（留待后续轮次）

- **前端全部**：React/TS/Vite/PWA、五页导航、训练执行界面（M1 的 UI 部分）——发起人明示暂缓。
- **多智能体**（M2）：专业 Agent 拆分与编排。本轮统一协议已为 AI 来源修改预留 `source=ai` 通道，agent 工具迁移到统一服务属 M2。
- **统一知识检索与导入**（M3）：向量检索、PDF/文章导入、从视频建动作。
- **视频分析深化**（M4）：时间轴标注、两次对比、人工标注集。现有 `vision*.py` 原样保留。
- 三维人体、实时纠偏、外部设备（§十五第三优先级全部）。
- PostgreSQL、Redis/任务队列（§10.3/10.4：SQLite + 进程内服务在本阶段足够）。

### 1.3 必须保护的现有资产（2.0 §十二"必须保护的资产"）

443 项离线回归及其覆盖的安全语义（红旗拦截、医疗准入、伤病隔离、两步确认、
evidence 绑定、打卡事务）**不因本轮改造退化**。本轮不重写 `coach/agent.py`、
不动冻结评测 YAML、不迁移现有表数据（只增表）。`coach/` 现有模块只做**增量**修改。

---

## 二、B1 TrainingApproach（我的训练方式）

### 2.1 数据模型（2.0 §2.1/§十一）

单一事实来源原则：**已在档案/计划/尝试表中存在的信息不在 approach 里复制品**，
approach 文档只拥有"训练方式选择"类维度；对外呈现时引用维度从现有数据动态拼装。

approach 文档（JSON，存 `training_approach.content`，按 user 一行）：

```text
{
  "revision": 3,                      # 版本号，每次修改 +1
  "structure":        {"value": "ppl"|"full_body"|"upper_lower"|"circuit"|"custom",
                        "note": "...", "status": "active"|"trialing"|"stopped"|"to_review"},
  "intensity_style":  {"value": "linear"|"rpe_based"|"periodized"|"flexible",
                        "note": "...", "status": ...},
  "exercise_selection": [             # 当前采用/替代动作（自有维度）
      {"exercise_id": "...", "role": "main"|"secondary"|"accessory"|"cardio"|null,
       "alternatives": ["..."], "status": "active"|"trialing"|"stopped"|"to_review",
       "note": "选择依据"}],
  "execution_choices": [              # 动作执行的个人选择（幅度/节奏/站距/握距）
      {"exercise_id": "...", "choices": {"tempo": "...", "stance": "...", ...},
       "note": "..."}],
  "diet_approach":     {"strategy": "...", "note": "...", "status": ...},
  "recovery_approach": {"note": "...", "deload_policy": "..."},
  "preferences":       {"liked": [], "disliked": [], "structure_notes": "..."}
}
```

引用维度（GET 时拼装、不落库）：个人目标（`profile.goal`，含目标版本）、
现实条件（`profile.resources`）、身体状况（`profile.conditions`）、
进行中的个人尝试（`personal_trials`）、选择依据的可追溯记录
（`coach_notes` / 打卡派生数据）。频率（每周几天）仍以
`profile.resources.days_per_week` 为准，approach 不另存副本。

### 2.2 版本历史（2.0 §2.2）

`approach_revisions` 每次修改一行：完整快照 + 逐字段 diff + 发起者（user/ai/system_migration）
+ 原因 + 是否确认 + 变更时生效的计划版本 + 时间。恢复历史版本 = 以新版本落库快照
（不删历史、不回滚指针）。

### 2.3 受测迁移（2.0 §十二"不直接清空"）

`initialize_approach(db, user_id)`：从现有档案 + 当前生效计划推导 v1
（结构按计划模板推断、动作选择从 schedule 提取），幂等（已有 approach 不覆盖），
推导规则全部有测试。老用户零感知——不迁移任何既有表数据。

### 2.4 验收（2.0 M0 验收原文对照）

- 能创建、修改、查看和恢复训练方式版本 ✅（API + 域函数 + 测试）
- 能独立修改训练方式的部分字段（改一个动作不动整个方式）✅（维度独立 set/remove）
- 不影响已有计划、打卡和安全功能 ✅（全量回归 443 项保持全绿）
- 核心数据模型具有自动化测试 ✅（test_approach.py）

---

## 三、B2 统一修改协议（ChangeProposal → Validation → Commit）

### 3.1 协议要素（2.0 §4.2/4.3）

新表 `change_proposals`（id / user_id / target / operations / source / reason /
base_version / status / result / created_at / decided_at）。

- **target**：`approach` 或 `plan`（本轮支持的两类目标）。
- **operations**：类型化的操作列表（见 B1/B3），不是自由 JSON 补丁。
- **source**：`user_manual`（手动，2.0 §4.1 常规编辑不需 AI 批准）/
  `ai`（建议，必须经用户明确确认，2.0 §4.2）/ `rule`（预留）。
- **base_version**：approach_revision 或 plan_id+plan_version，提交时校验，
  不匹配即拒绝（2.0 §4.3"避免覆盖用户后续操作"）。

### 3.2 校验（确定性代码，同套用于两条路径）

1. 结构校验：operations 形状、枚举值、动作 id 必须在库内（未识别动作拒绝并提示）。
2. 安全校验（手动编辑也不可绕过，2.0 §1.4"用户自主≠绕过安全限制"）：
   - `plan_fence` 活跃（伤病/红旗隔离）→ 拒绝 plan 编辑，唯一出路是确认重排；
   - 医疗许可不允许处方 → 拒绝 plan 编辑；
   - 有伤病关节时，向计划加入该关节压力 ≥2 的动作 → 拒绝；
   - 用户 avoid 状态的动作 → 允许但警告（偏好可由用户本人改变）；
   - draft 动作 → 允许，计划备注保留"属性未审核"披露。
3. 版本校验：base_version 与当前不一致 → 拒绝。

### 3.3 提交（单事务，失败不部分生效）

- approach：应用操作 → 新 revision 快照 + diff → proposal 标记 applied。
- plan：应用操作 → `db.create_plan(expected_plan_id=...)` 出新版本
  （`adjust_action="manual_edit"` / `"approach_change"`，清空旧 pending 建议，
  记录 `approach_revision` 关联）→ proposal 标记 applied。
- AI 来源：先落 pending（记 created_message_id，同轮不可确认），
  `confirm(proposal_id, user_message)` 用现有 `confirmation.classify_decision`
  语义门判定 accept/reject/unclear（unclear 保持 pending），accept 后走同一 commit。

### 3.4 验收

- 手动修改直接生效、AI 修改未经确认不生效（测试覆盖两种来源）；
- 版本冲突、隔离期编辑、医疗暂停期编辑、伤病高压动作注入均被拒绝（对抗测试）；
- 提交失败无部分生效（事务回滚测试）。

---

## 四、B3 计划手动编辑后端

操作集（作用于当前生效计划，全部走 B2 协议）：

| 操作 | 参数 |
|---|---|
| `add_exercise` | day, exercise(名/id), sets, reps, weight_kg?, role?, note?, index? |
| `remove_exercise` | day, index 或 exercise |
| `replace_exercise` | day, index 或 exercise, 新动作(+可选 sets/reps 继承) |
| `reorder_exercise` | day, from, to |
| `edit_set_prescription` | day, index, sets?/reps?/weight_kg?/note?（部分修改） |
| `rename_day` | day, new_name |

约束：日名必须存在；index 越界拒绝；一次 proposal 可含多个操作，按序应用，
任一失败整体拒绝（先校验后提交）。编辑产生的新计划版本保留未涉及部分原样
（含处方重量、卸载状态、notes 中的既有披露）。

---

## 五、B4 FastAPI 服务层

`backend/`（新增包，不移动 `coach/`）：

```text
backend/
├── __init__.py
├── app.py          # create_app(db_path=None) 应用工厂；python3 -m backend 启动 uvicorn
└── routes.py       # /api 路由（薄层，全部委托 coach/ 域函数）
```

端点（v1，全部离线可测，TestClient 不出进程）：

| 端点 | 说明 |
|---|---|
| `GET /api/users/{uid}/profile` | 档案（含目标版本/隔离状态摘要） |
| `GET /api/users/{uid}/today` | 今日简报（确定性：医疗状态/隔离/待跟进安全记录/到期笔记与尝试/距上次训练天数/本周执行率/当前计划摘要） |
| `GET/POST /api/users/{uid}/approach(/initialize)` | 查看（含引用维度拼装）/ 初始化迁移（幂等） |
| `GET /api/users/{uid}/approach/revisions` | 版本历史 |
| `POST /api/users/{uid}/approach/revisions/{rev}/restore` | 恢复历史版本 |
| `POST /api/users/{uid}/changes` | 提交手动修改提案（approach/plan） |
| `GET /api/users/{uid}/changes?status=` | 提案列表（含 pending 的 AI 建议） |
| `POST /api/users/{uid}/changes/{id}/confirm` | 确认/拒绝 AI 提案（语义门） |
| `GET /api/users/{uid}/plan` | 当前计划 + 版本元信息 |
| `POST /api/users/{uid}/plan/edits` | 计划手动编辑（走统一协议） |
| `GET/POST /api/users/{uid}/checkins`；`POST .../checkins/{id}/correct` | 打卡落库（确定性校验+归一）/ 纠错（复用 revise_checkin） |
| `GET /api/exercises` | 动作库检索（名称/别名/肌群/器械/状态过滤） |
| `POST /api/users/{uid}/chat` | AI 教练对话（复用 CoachAgent，测试用 FAKE_LLM） |

服务边界：每用户复用一个 `CoachAgent` 实例（进程内缓存）；应用工厂接受
`db_path` 注入（测试用临时库）。CLI `main.py` 保留不动（2.0 §十二）。

---

## 六、验证与完成定义

1. 新增测试文件：`test_approach.py` / `test_changes.py` / `test_plan_edit.py` / `test_api.py`，
   覆盖上述每条验收；全部离线（临时库、FAKE_LLM、禁网，conftest 现有约束不放宽）。
2. **全量离线回归 443 项保持全绿**（现有测试不改语义；如确需触碰，逐处留痕说明）。
3. 零真实 LLM 调用、零付费额度；冻结评测 YAML 不动；`data/` 真实库不被测试触碰。
4. `requirements.txt` 增加服务层依赖（fastapi/uvicorn，注释标明用途）。
5. 留痕：PROGRESS.md 新节、README 组成更新、DESIGN.md 第 28 章指针。
6. 本轮改动**不自动提交 git**——提交与推送等发起人指令。

## 七、已知边界（不冒充完成）

- 统一协议本轮只接管"手动编辑 + AI 提案确认"两条新路径；`coach/agent.py` 现有
  工具（apply_adjustment / confirm_profile_change / 重排）**继续按原机制运行**，
  迁移到统一服务属 M2，本轮不做（避免重写冻结架构）。
- approach 与计划的关联：经协议提交的计划版本带 `approach_revision` 戳；
  agent 旧路径生成的计划不带该戳（GET 时如实标注），不做回填。
- 多设备并发：本轮以 base_version 乐观锁防覆盖（单机单进程足够）；
  完整冲突合并留待多端同步需求出现。

---

## 八、B6 前端（2026-10-24 追加：发起人指示"按照任务书把前端完成"）

原 §1.2 的前端暂缓由发起人同日指示解除。本轮范围 = 2.0 §10.1 技术选型 + M1 的 UI 部分，
验收线为 M1 原文：**手机上完成建档 → 制定计划 → 修改计划 → 开始训练 → 逐组记录 →
完成训练 → 查看历史，全程不依赖 CLI，不要求每个操作经过 LLM**。

### 8.1 交付

| 项 | 内容 |
|---|---|
| 技术栈 | React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + Zustand + React Router 6 + idb-keyval（IndexedDB）；PWA（manifest + 最小 service worker：外壳缓存，`/api` 一律走网络） |
| 五页导航 | 今日 / 训练 / AI 教练 / 探索 / 我的（手机优先 max-w-lg 布局，底部 Tab） |
| 今日 | 医疗状态与隔离警告、待复核笔记/尝试、当日训练（按星期匹配）与继续训练、本周计划、执行统计、离线同步提示 |
| 训练计划编辑器 | 六种操作全部走统一修改协议（`POST /plan/edits` + base_version 乐观锁）；422 版本冲突自动刷新并提示重做；draft 动作披露随保存自动出现 |
| 训练执行 | 逐组记录（重量/次数/RPE/热身组）、上次重量自动带出（`/exercise-states`）、休息计时器（默认 90s 可跳过）、训练中替换动作（仅影响本次记录）、完成后统一 `save_checkin`（确定性清洗归一，不经 LLM） |
| 离线记录与同步 | 断网时打卡进 IndexedDB 队列，恢复联网自动补交；422 类永久拒绝留痕丢弃、网络类按序保留（vitest 锁定，曾抓到并修复断网丢后续条目的 bug） |
| 训练历史 | 按时间列出；纠错弹窗（expected_revision 乐观锁 + 必填原因），修订 vN 标签展示 |
| AI 教练 | 对话（复用 CoachAgent）；AI 待确认修改提案卡片（同意/先不改 → 语义门 confirm），手动/已应用提案列表 |
| 探索 | 动作库搜索（名称/别名/id）+ 肌群筛选 + 审核状态标签 + 详情（教学要点/关节压力/未审核披露） |
| 我的 | 档案摘要、我的训练方式（查看/一键初始化/版本历史/恢复）、个人尝试、数据导出 JSON、用户切换、边界声明 |
| 建档 | 四步表单（基本信息/目标经验/条件/PAR-Q 四项必答），**不经过 LLM**；后端确定性校验对齐 onboarding 门槛；阳性自动落医疗暂停模板并如实呈现 |
| 部署 | `create_app` 自动托管 `frontend/dist`（SPA 回退），`python3 -m backend` 单进程即完整产品；开发模式 `npm run dev` 代理 `/api` |

### 8.2 后端配套新增（均已测）

`POST /users/{uid}/onboarding`（表单建档）、`GET /users/{uid}/exercise-states`（上次重量）、
`GET /users/{uid}/trials`、`GET /exercises/{id}`、SPA 静态托管；test_api.py 增 6 项（16→22 全绿）。

### 8.3 验证与边界

- `tsc --noEmit` + `vite build` 通过；vitest 5/5（协议构造器 + 离线队列语义）。
- **浏览器 E2E 全流程通过**（真实 Chromium，390×844 移动视口，FAKE_LLM + 临时库）：
  建档（4 步表单 → 定级进阶 → 三分化计划）→ 修改计划（v1→v2，加平板支撑，draft 披露出现）→
  开始训练（周六·蹲，上次重量自动带出 102.5kg）→ 逐组 3 组（休息计时/容量统计）→ 完成训练 →
  历史 → 纠错（105→110，修订 v1 留痕）→ 我的（训练方式初始化 13 项）→ 探索（详情/审核标签）。
  E2E 抓到并修复 1 个前端 bug（保存成功页被空会话守卫挡住）。
- 后端全量回归 **500 项全绿**（无退化）；冻结评测 YAML 未动。
- 边界：结构化卡片/图表（ECharts）、三维展示、推送提醒属后续增强（§十五第三优先级）；
  AI 回复的结构化组件（2.0 §三 页面三）留待 M2 多智能体一起做。

---

## 九、M1.1 修复轮（2026-10-24，发起人外部审查处置）

发起人审查 `009be28` 后提出 5 个 P0 + 3 个 P1（P0-1 版本保护未贯通 / P0-2 离线重复提交与静默丢弃 /
P0-3 无身份验证 / P0-4 逐组数据被压缩 / P0-5 健康筛查预填阴性；P1-1 隔离态仍可开始训练 /
P1-2 处方缺数值校验 / P1-3 训练方式不可编辑）。本轮只修复、不加新架构。

| 项 | 修复 | 测试证据 |
|---|---|---|
| P0-1 | 前端编辑器提交携带打开时的 `base_version`；`/plan/edits` 缺 base_version 一律 422（不再自动补最新版） | API 并发测试（B 先改 v2，A 基于 v1 提交被拒）；浏览器 E2E 实测 422 + 自动刷新 |
| P0-2 | `submission_id` 客户端稳定生成 + 服务端 `checkin_submissions` 唯一约束幂等（重试返回已存结果；并发窗口删重复行）；4xx 不再丢弃——进**失败队列**（IndexedDB 持久化，可重试/丢弃/导出，「我的」页管理卡片）；网络类按序保留 | pytest 幂等/重复/异 ID；vitest 5 项（含同 ID 重试）；E2E 真实断网：停服→训练→入队→恢复→自动同步→服务端恰好 1 条 |
| P0-3 | 访问模式分级：默认仅 127.0.0.1；`API_HOST` 非回环且未设 `API_ACCESS_TOKEN` 时启动拒绝；设令牌后 `/api/*`（health 除外）需 `X-Access-Token`；前端「我的」配置令牌自动携带。**完整多用户认证仍是手机公网开放前的门槛**（如实声明） | 401/放行/health 开放测试 + 启动守卫测试 |
| P0-4 | 训练保存改 `set_logs` 逐组结构（每组重量/次数/RPE/热身/完成时间）；聚合字段（sets/weight/reps/rpe）由服务端从正式组派生（代表组=容量最大），旧复盘/调整引擎无感兼容；`coerce_checkin` 逐组清洗（坏组剔除并警告） | pytest 每组保存+派生+坏组；E2E 三组递增卧推逐组可见 |
| P0-5 | PAR-Q 初始未作答（不再预填阴性）；「有」只聚焦引导填写（不落占位文字）；未作答提交被拦并列出缺项；伤病必须勾选"无"或如实填写，依据文本忠实 | E2E：未答提交被拦→逐项作答通过 |
| P1-1 | 隔离态：今日页隐藏"开始训练/练这天"；训练页 3 个执行入口替换为隔离说明；执行页加载即拦截 | E2E 实测（DB 直设 fence） |
| P1-2 | `_check_sets/_check_reps/_check_weight` 统一处方校验：组数 1-20 整数；次数 1-100 / 区间 a≤b / 时长 N秒·分；重量 0-1000；备注 ≤200 字 | 7 组参数化拒绝测试 + 时长/区间合法测试 |
| P1-3 | 「我的」页训练方式编辑器：结构/强度/饮食/恢复/偏好五维度直改，走统一修改协议出 v2+；**不自动重排计划**（计划落后提示由用户决定找 AI 商量） | E2E：改结构保存 v2 |

**E2E 补充发现并修复**：断网时计划接口失败导致训练页完全不可用 → 计划成功加载时缓存 localStorage、断网降级（训练/执行页 + SW 外壳缓存；SW 缓存版本随发布升级 v1→v3）；`exercise_states`（上次重量，辅助信息）断网降级为空不阻塞执行。

**验证汇总**：全量离线回归 **515 passed**（500 + 15 新增，零退化）；tsc+vite build 通过；vitest 7/7；
浏览器 E2E（真实 Chromium 390×844 + 真实网络中断）覆盖：表单必答拦截、并发编辑 422、多组逐组持久化、
断网 PWA 启动/训练/入队/恢复自动同步且无重复、隔离态入口禁用、训练方式编辑，附视觉验收截图。

**边界**：多用户完整认证体系（注册/登录/会话）未做——单令牌是过渡方案，手机跨设备/公网开放前必须补；
失败记录"修正后重试"暂为原样重试+导出（修正入口属 M2 范畴）；E2E 用 FAKE_LLM，真实 LLM 对话行为不在本轮证据内。

---

## 十、M2 多智能体教练（2026-10-24，发起人指示"开始 m2"）

对照 2.0 §五/§十三 M2 十项任务与验收；同时补通上轮审查点名的断链
（"原有 CoachAgent 尚未整体接入新的统一修改协议"）。

| 项 | 实现 |
|---|---|
| 主教练编排（任务1） | `coach/agents/orchestrator.py`：**确定性关键词路由**（不调 LLM 决定路由）——"简单问题只调用必要智能体"由代码保证；复合问题命中多专家并行咨询 |
| 五个专业 Agent（任务2–6） | `coach/agents/specialists.py`：训练科学/营养/恢复/动作/知识研究，统一 **AgentAdvice** 结构化输出（问题/事实/知识依据/候选方案/适用条件/风险/需确认，任务7）；非法输出确定性降级（缺字段补空），绝不把自由文本当结构化建议 |
| 跨 Agent 冲突（任务8） | 多专家均给出候选方案时**并列保留**各自适用条件并显式提示"不自动裁决"（2.0 §6.6），由用户选择 |
| 统一协议接入（审查断链） | CoachAgent 新增三工具：`consult_specialists`（咨询+留痕 agent_consultations）、`propose_change`（结构化修改只落 **pending**，绝不直接写数据）、`confirm_proposal`（对话确认：语义门+跨轮检查，同轮自批拒绝）——与网页提案卡同一条 `change_proposals` 通道 |
| 预览/确认/撤销（任务9） | 提案卡展示**操作预览**（类型化操作转人话）；确认=同意/拒绝语义门；撤销=拒绝待确认提案 + **计划版本历史与恢复**（新端点，安全门内隔离/医疗暂停拒恢复，恢复出新版本不清历史） |
| 训练方式关联（任务10） | 经协议的计划/提案带 approach_revision 戳（B2 已有，M2 链路复用） |

**验收对照（M2 原文）**：简单问题零咨询（路由测试+FAKE 链路）✓；复杂问题综合多专家
（营养+恢复复合提问测试）✓；AI 不绕过确认（propose 只 pending；同轮自批被拒测试）✓；
建议可追溯（AgentAdvice 带知识依据 + agent_consultations 留痕 + API 可查）✓；
不同 Agent 不写坏计划（专家零写权限，写路径唯一=统一协议）✓。

**验证**：test_agents.py 20 项 + test_api 4 项；全量回归 **539 passed**（515 基线零退化）；
tsc+build 通过；浏览器 E2E（FAKE）：专业问题→已咨询专家回复+最近咨询卡；教练提案→
卡片操作预览→用户同意生效（训练方式 v2=upper_lower）；计划改名 v2→版本历史→恢复 v1 为 v3。

**边界**：FAKE 专家为确定性固定建议，真实 LLM 下专家质量需下一轮真实对话验收；
行为支持 Agent（2.0 §5.2 明示可后续）与专家并行调用的进程池化未做（单用户本地串行足够）；
规则引擎 apply_adjustment 旧路径与 propose_change 并存（前者管规则建议、后者管 AI 结构化修改），完全归一属后续。
