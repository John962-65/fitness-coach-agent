# P0 交付文档：专家工作台与专家任务基础设施

> 交付日期：2026-10-25 ｜ 基线：`25f188c` ｜ 状态：**已交付，验收通过**
> 总纲见 [expert-platform-roadmap.md](expert-platform-roadmap.md)

## 0. 交付范围

P0 只做专家平台的地基与第一个真实工作台（训练科学），未启动 P1-P7
的功能开发。营养/恢复/康复/动作四顾问已在注册表登记为 planned 状态，
UI 如实标注"建设中"及数据依赖，不伪造分析能力。

## 1. 修改文件清单

### 后端（新增）

| 文件 | 职责 |
|---|---|
| `coach/experts/__init__.py` | 包说明（架构纪律） |
| `coach/experts/registry.py` | 专家注册表：5 顾问 + 主教练 + 共享知识；触发订阅表；任务类型 → 执行器映射 |
| `coach/experts/task_dispatcher.py` | 事件 → ExpertTask（幂等/频率限制/主动分析开关）→ 执行（重试/恢复/日志） |
| `coach/experts/insight_service.py` | ExpertInsight 创建/查询/已读/忽略/重新分析/懒失效/到期 |
| `coach/experts/evidence_validator.py` | 落库前证据复核：编造 fact_id/来源剔除并计数 |
| `coach/experts/recommendation_service.py` | 方案 → ChangeProposal（AI 路径）——唯一提案桥梁，无直接写权限 |
| `coach/experts/training_science.py` | 训练后回顾分析器（纯确定性，复用 fact_service 同源口径） |
| `test_experts.py` | 19 项专项回归测试 |

### 后端（修改）

| 文件 | 变更 |
|---|---|
| `coach/db.py` | 新增 4 表（expert_tasks / expert_task_events / expert_insights / expert_settings）及配套方法（约 +330 行） |
| `backend/routes.py` | 新增 12 个专家平台 API；`save_checkin` 训练保存后触发 WorkoutSaved（整体容错） |
| `backend/app.py` | 启动时 `recover_stale`：崩溃残留 running 任务重试或失败 |

### 前端（新增）

| 文件 | 职责 |
|---|---|
| `src/pages/Experts.tsx` | 专家中心：主教练/知识入口 + 5 顾问卡 + 主动分析开关 + 分析/任务列表 |
| `src/pages/experts/TrainingExpert.tsx` | 训练科学工作台（概览/数据/分析/建议/咨询 五区） |
| `src/components/experts/ExpertCard.tsx` | 顾问卡（ready/planned 如实标注） |
| `src/components/experts/InsightCard.tsx` | 分析摘要卡（今日页/中心页/工作台共用） |
| `src/components/experts/EvidencePanel.tsx` | 发现 → 引用事实/来源链展开面板 |
| `src/components/experts/RecommendationOptions.tsx` | 方案取舍呈现 + 忽略/重新分析/转提案与确认流 |
| `src/components/experts/ExpertTaskStatus.tsx` | 任务状态与执行日志 |
| `src/lib/experts.ts` + `experts.test.ts` | 展示工具（状态/置信度/追溯链/相对时间）+ 3 组单测 |

### 前端（修改）

| 文件 | 变更 |
|---|---|
| `src/App.tsx` | 新路由 `/experts/*`；`/coach`、`/explore` 重定向 |
| `src/components/BottomNav.tsx`、`SideNav.tsx` | 导航重构：今日｜训练｜专家｜我的 |
| `src/pages/Today.tsx` | 新增"专业分析"卡片区；AI 入口改指 `/experts/chat` |
| `src/pages/Training.tsx` | 旧 `/coach` 链接更新 |
| `src/api.ts`、`src/types.ts` | 专家平台类型与 API 客户端 |

## 2. 数据模型与兼容方案

四张新表（`CREATE TABLE IF NOT EXISTS`，老库无损升级，无既有表改动）：

```
expert_tasks        任务队列：status(pending/running/ready/failed/cancelled)、
                    dedup_key(UNIQUE(user_id,dedup_key) 事件幂等)、retry/heartbeat、
                    error_code；trigger_source 列名避开 SQL 关键字 TRIGGER
expert_task_events  执行日志：enqueued/started/retry/ready/failed/cancelled/recovered
expert_insights     分析结果：findings/evidence_refs/facts_snapshot/knowledge_refs/
                    options/limitations + confidence(规则生成) + confidence_basis +
                    source_revision({checkins:{id:rev}, plan_version}) + input_refs +
                    expires_at + status(ready/viewed/dismissed/expired/invalidated)
expert_settings     proactive_enabled / min_interval_minutes（按用户）
```

**失效设计（关键决策）**：不依赖钩子全覆盖，采用**懒失效**——每次读取
洞察时对比 source_revision 与当前数据：引用的 checkin 修订数变化或生效
计划版本升高 → invalidated；expires_at 已过 → expired。任何写入路径
（API/agent/历史恢复）造成的数据漂移都会在用户看到之前被识别。

## 3. 后端 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/users/{uid}/experts/overview` | 注册表视图 + 各顾问活跃洞察数 + 设置 + 排队任务 |
| GET/POST | `/api/users/{uid}/experts/settings` | 主动分析开关与频率限制 |
| POST | `/api/users/{uid}/experts/analysis` | 用户主动请求分析（`{specialist, params:{checkin_id}}`） |
| GET | `/api/users/{uid}/experts/tasks[?status=&specialist=]` | 任务列表 |
| GET | `/api/users/{uid}/experts/tasks/{id}` | 任务详情 + 执行日志 |
| POST | `/api/users/{uid}/experts/tasks/{id}/cancel` | 取消未执行任务 |
| GET | `/api/users/{uid}/expert-insights[?specialist=&status=&limit=]` | 洞察列表（轻载荷，懒失效生效） |
| GET | `/api/users/{uid}/expert-insights/{id}` | 洞察详情（完整载荷） |
| POST | `…/{id}/view` `…/{id}/dismiss` `…/{id}/regenerate` | 已读 / 忽略 / 重新分析 |
| POST | `…/{id}/options/{option_id}/proposal` | 方案 → pending 修改提案（确认走既有 `/changes/{id}/confirm`） |

触发接线：`POST /checkins`(type=training) 成功后 `on_event(WorkoutSaved)`
（内联执行确定性分析；异常整体吞掉留任务日志，**绝不阻塞打卡**）。

## 4. 训练科学分析器（确定性内核）

- 输入：checkin_id；窗口 60 天（与趋势分析一致）；
- 数值全部来自 `fact_service` / `exercise_metrics` / `progress_analysis`
  同一套口径（与「我的表现」「周期统计」构造性一致）；
- 发现三类：本次基本盘 / 与窗口内此前对比 / 趋势（复用
  `analyze_progress`，含样本与缺口限制）；
- 每条发现带 `fact_ids`（对应事实快照）与 `source_ids`
  （`checkin:ID:revision:N` 追溯链），落库前经证据校验；
- 方案：永远含「延续当前安排」；递增趋势（weight_reps）给出"小幅加重"
  参考方向（动作在计划内册时附 `edit_set_prescription` 提案提示）；下行
  趋势给出"先检查恢复"；数据不足只保留观察项；
- 置信度规则（写入 basis 可复核）：每动作按窗口会话数/纠错/最大间隔评级
  （≥4 次且无纠错且间隔≤10 天=high；2-3 次=medium；1 次=low），整体取
  最低档；
- 局限：e1RM 估算口径、窗口间隔、未识别动作、方案为规则参考非处方。

**本分析不调用 LLM**（2.0 §2.3"事件不等于必须调用 LLM"）。

## 5. 前端交互

- **今日页**：训练保存后自动出现"专业分析"卡片（训练科学/状态/置信度/
  摘要），点击直达工作台分析详情（不经聊天）；
- **训练科学工作台**五区：
  - 概览：30 天统计 + 当前状态 + 分析口径说明；
  - 数据：近期训练记录（含纠错标记）+ 任务执行日志；
  - 分析：洞察列表 → 详情（发现/证据展开/知识参考/局限/置信度依据/
    失效原因/数据来源链）；
  - 建议：方案取舍（收益/代价/适用条件）+ 转提案 → 明确表述确认/拒绝
    （语义门）；忽略；失效洞察提供"用最新数据重新分析"；
  - 咨询：训练科学相关咨询历史 + 主教练入口（聊天为辅助）；
- **专家中心**：5 顾问卡（ready/planned + 各自数据依赖）、主动分析开关、
  分析/任务两个列表；
- 失效洞察如实显示原因（"训练计划已更新（v1→v2），该分析基于旧计划…"），
  不再以旧充新。

## 6. 测试与验收

### 自动化

- 后端：`test_experts.py` 19 项（端到端/幂等/置信度/纠错失效/计划变更
  失效/到期/已读忽略重分析/取消/恢复/开关/频率限制/确认协议/失败不阻塞
  /输入无效不重试/用户隔离/证据校验/概览接口）；**全量 708 项通过**；
- 前端：tsc 零错误；Vitest 45 项通过（含新增 3 项）；生产构建通过。

### 真实浏览器端到端（手机视口 390×844，FAKE_LLM 后端）

完整验收链路 **全程未打开聊天页面**：

1. 自由训练添加杠铃平板卧推，记录 70kg×5×3 组，保存 → WorkoutSaved；
2. 今日页自动出现新卡片：**数据充分 · 趋势上行 · 2 个可选方向**；
3. 点击卡片进入工作台（自动标记已读）：发现/证据/知识参考/局限/
   置信度依据（"窗口内 5 次 → high"）/数据来源（打卡 #1-#5）；
4. 建议页：「延续当前安排」+「小幅加重 72.5kg 档位」；
5. 转为修改提案 → pending（周一 处方 weight_kg=72.5）→ 输入"确认，
   按这个方案加重" → **计划 v1→v2 生效**；
6. 计划变更后全部旧洞察自动标记**已失效**（含原因）；
7. 失效洞察"用最新数据重新分析"→ 新洞察（依据计划 v2）；
8. **忽略建议** → "已忽略（历史保留，随时可重新分析）"；
9. 旧路由 `/coach` → `/experts/chat` 重定向验证通过。

截图：`docs/p0-shots/`（01 今日卡片 / 02 工作台分析 / 03 建议与提案 /
04 计划变更失效 / 05 专家中心）。

### 实际发现并修复的问题

1. `on_event` 返回入队时快照而非执行后状态 → 执行后重读任务（测试抓出）；
2. `expert_insights` 漏存 `input_refs` 导致重新分析拿不到输入 → 补列；
3. E2E 发现：失效洞察最需要"重新分析"但按钮仅在 actionable 状态显示
   → 移出条件（忽略仍限 actionable，重新分析对所有已落库洞察可用）。

## 7. 未完成事项与技术限制

1. **LLM 增强叙述**：post-workout-review 为纯确定性输出；未来可为需要
   解释/知识比较的任务类型增加 `analysis_mode=llm`（框架已预留 llm 参数）；
2. **触发面**：仅 WorkoutSaved/UserRequested 接线；其余事件
  （MealRecorded 等）在注册表登记，待对应领域数据系统（P1-P4）落地；
3. **执行模型**：内联同步执行（确定性分析毫秒级）。若未来出现耗时任务
   （视频分析等），需引入后台工作线程复用既有 `_run_media_worker` 模式；
4. 历史回填（通过保存接口导入旧训练）每次保存同样触发各自的回顾——
   可忽略，批量导入场景的触发豁免待 P7 数据导入一并设计；
5. 营养/恢复/康复/动作工作台为 planned 占位（如实标注），P1-P4 交付；
6. 「饮食」导航页待 P1 营养系统落地后加入（不用空壳标签冒充功能）。
