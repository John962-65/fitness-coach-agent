# P5-C 训练进阶与下一次训练建议

> 基线：`1e88513`（P5-C2）｜ 日期：2026-10-27
> 当前状态：**P5-C3 闭环收尾已交付——P5 全部完成**；闭环与个人尝试详见
> [p5c3-progression-trial-acceptance.md](p5c3-progression-trial-acceptance.md)

## 0.2 P5-C3（收尾）：进阶闭环与个人尝试

- **审计**：P5-C2 交付逐项复核达标；两项小修——替换动作后撤销该卡
  "仅本次"目标；分析后新增恢复记录也使旧洞察失效。
- **服务端构造提案**：新增 `POST …/training-progression/{exercise_id}/adopt`，
  只收 `option_id`，由服务端重算候选并取 `plan_proposal` 构造提案；
  前端不再提交目标数值。
- **PersonalTrial 闭环**：候选 → 尝试（origin/计划上下文/chosen_target/
  观察指标/基线快照落 `personal_trials` 新增可空列）→ 观察期真实记录
  确定性判定（与引擎同口径）→ 复盘草稿（已观察/可能解释/无法确认）→
  用户决策 keep/adjust/stop/observe；任何决策不自动修改计划。
- 测试：`test_p5c3.py` 8 项；全量后端 840 passed；浏览器 E2E A–D 全通过
  （截图 `docs/p5c3-shots/`）。

## 0.1 P5-C2（上轮）：候选引擎接入训练页面与训练科学顾问

不新增 Agent、不重建训练系统；P5-C1 确定性候选成为唯一可执行数值来源。

### 后端

1. **只读 API**：`GET /users/{uid}/training-progression/{exercise_id}`
   （query：`plan_id / plan_version / planned_day / index /
   planned_exercise_id`）。返回 `rules_version / context / options /
   recommendations_allowed / blocked_reasons / source_revisions` +
   `insight`（最近一次同动作 next-training-review 的状态，读取时懒失效）。
   只读：不建训练记录、不改计划；所有读取按 user_id 过滤，伪造他人
   计划上下文只会得到"过期/不存在"。`options[]` 上按差异附加
   `plan_proposal`（与当前处方有实际差异才有；是长期提案操作的
   唯一来源）。
2. **next-training-review 任务**：registry 新增任务类型（training_science），
   触发 `UserRequested`（训练页面打开只读确定性候选，不调 LLM；用户点
   "请求专业解释"才生成）。分析器 `analyze_next_training` 确定性打包：
   - 解释候选、适用条件、取舍比较、数据不足标注；全部数值来自
     P5-C 上下文（同源口径，构造保证不产生候选之外的可执行数值、
     不编造历史、e1RM 标注"估算"）；
   - findings 覆盖最近表现 / 目标达成分类 / 逐候选解释 / 数据缺口 /
     恢复自报（独立事实，不做过度训练推断）；evidence_validator 复核；
   - `source_revision` 记录 checkins 修订、计划版本、恢复记录修订、
     限制版本、器械/地点指纹（新 `equipment_version()`）与进阶规则版本；
   - 方案镜像确定性候选：有 `plan_proposal` 才带 `proposal_hint`。
3. **洞察生命周期**：`_revision_drift` 新增恢复记录修订、器械/地点指纹、
   规则版本三类失效检查（与既有 checkins/计划/限制失效并列）——
   用户更正历史训练、修改计划、切换地点/器械、规则升级都会使旧洞察
   失效；`list_expert_insights` 补齐 `input_refs` 列读取。
4. `POST /users/{uid}/experts/analysis` 支持
   `task_type=next-training-review`（必填 `params.exercise_id`）。

### 前端

1. **建议面板**（`NextTrainingAdvice.tsx` + `ProgressionOptionCard.tsx` +
   `ProgressionEvidence.tsx`）：每个动作卡新增"查看下一次训练建议"；
   打开时实时拉取确定性候选（不依赖前端缓存）；展示上次实际完成、
   数据状态（结构可比/达成分类/恢复自报/生效限制/阻断原因）、候选方案
   （含"查看依据与限制"展开：真实事实、可追溯来源、档位来源、限制、
   取舍）。
2. **仅本次采用**：store 新增 `applySessionTarget(entryIdx, targets,
   optionId)` + `revertSessionTarget(entryIdx)`。只写 `entry.target`
   （+`session.appliedTargets` 快照）；不碰已记录组、组法草稿、超级组、
   休息计时器、有氧/HIIT 执行状态；`compatibleTargetPatch()` 把不兼容
   字段剔除（复杂组不接受普通负重覆盖、有氧/HIIT/时长/距离不接受
   次数/负重——这些候选只展示方向）；随会话持久化（刷新恢复）；
   仅本次，不改长期计划。
3. **长期修改**：面板内"申请修改长期计划"只对该候选的
   `plan_proposal` 开放 → `ChangeProposal`（stage_ai）→ 展示修改前后
   差异 → 用户明确确认 → 服务端确认时重新校验计划版本与安全状态。
   用户只查看建议时不创建任何提案。
4. AI 解释按需请求（UserRequested），面板显示状态徽标（有效/已读/
   已失效+原因）、置信度、发现与限制；失效可"重新分析"；忽略面板时
   同步忽略有效洞察。

### 浏览器 E2E（真实浏览器交互；截图在 `docs/p5c2-shots/`）

| 场景 | 结果 |
|---|---|
| A 普通卧推 | 面板显示真实历史与候选 → 仅本次采用 → 目标改 62.5kg、已完成组 0 组不变、计划仍 v1、无提案；刷新后恢复；撤销后目标复原 |
| B 数据不足 | 上斜卧推仅 1 次记录 → 只给维持/先完成目标次数/恢复观察，无增长伪造 |
| C 恢复数据 | 疲劳 5/酸痛 4/睡眠 5.5h 以"独立事实，不是诊断"呈现；候选含恢复观察方向，无过度训练判定 |
| D 安全限制 | 站姿推举受限 → 无候选方案、动作按钮全部禁用；直接调 API 修改 → 422 |
| E 长期修改 | 加重候选 → pending 提案（计划保持 v1，差异"负重 — → 62.5kg"可见）→ 确认 → v2 生效；旧上下文候选再提交 → 422 |

E2E 期间发现并修复：确认语义门会拒绝含"考虑"（候选标题原词）的确认语
——面板确认语改为明确肯定表述；确认时计划版本已变化的旧提案被服务端
拒绝（关键要求验证）。

## 0. P5-C1.1（上一轮）：结构可比与目标达成情况分离

修复三个 C1 边界，不改变候选引擎的确定性边界：

1. **记录可比性**：结构可比与目标达成情况分离。未达到目标次数的记录
   不再被自动排除出结构可比集合——结构相同才谈得上"差多少"。
   `NextTrainingContext` 新增 `comparability` 字段：
   - `structurally_comparable`：通过结构口径检查的会话 ID 列表；
   - `target_attainment`：按会话给出达成分类（达到目标次数上沿
     `at_top` / 达到下沿 `met_min` / 低于目标 `below_target` /
     超出目标范围 `above_range` / 数据不足 `insufficient_data`），
     混合情况在 `note` 中说明；
   - `comparison_limitations`：结构不可比的排除原因（纯结构口径，
     不再含"次数不在目标范围"）。
   "完成目标"与"训练量调整方向"现在能看见未达标记录并据此生成候选；
   **加重仍必须满足明确的完成标准**（最近两次可比训练均在目标次数上沿、
   无高 RPE），未达标记录永远不会触发加重。
2. **器械档位来源分级**（`equipment_context`）：
   - `exercise_progression_metadata`：内置动作库已验证的进阶元数据；
   - `user_exercise_progression_metadata`：用户自定义动作上明确配置的档位；
   - `observed_history`：历史记录中观察到的重量差——**只用于方向展示，
     不生成明确可执行的下一档重量**；
   - `unknown_no_exact_increment`：未知档位。
   新增 `increment_verified` 布尔：只有前两类来源才允许候选写入具体
   `weight_kg`/`assistance_kg` 数值。
3. **HIIT 可比性签名**：签名 = 每块（动作稳定 ID 或自定义活动身份）
   + 顺序 + 工作/休息/轮次。不同活动即使计时编排相同也不默认可比；
   自定义块（exercise_id 无法解析、保存时重置为 custom_hiit）用块名
   作为身份；只改计时不改身份、或只换块顺序，都会破坏可比性。

## 1. 本阶段范围（P5-C1）

本阶段只解决确定性分析核心：

- 修复 P5-B3 遗留边界；
- 建立 `NextTrainingContext`；
- 区分近期实际记录与可比记录；
- 按记录类型生成进阶候选；
- 接入恢复、P3 安全、器械档位和复杂组/超级组背景；
- 不新增 Agent，不改训练记录系统，不制作 AI 页面，不启动 P5-C2/C3。

## 2. C0.1 遗留边界修复

1. `exercise_metrics.exercise_sessions` 的 `steady_cardio_distance_m`
   只统计 `steady_cardio`。通用动作距离（如农夫行走）仍保留真实非间歇
   `distance_time` 记录；异常 HIIT 组携带的距离不会进入通用距离/持续有氧距离。
2. 历史纠错只有在“重新推断的活动类别 == 旧快照类别”时才继承旧快照。
   删除/新增 HIIT 元数据、动作类别或记录语义改变时，写入新的
   `activity_class=correction_snapshot`，不继续沿用已经失效的类别。
3. 同一 checkin 内重复出现同一动作时合并为一条动作会话并标记
   `duplicate_entries`；重复条目不能伪装成多次训练或触发进阶。
4. 计划处方重量与实际完成负重不一致时，只给“先完成当前处方”的方向，
   不把计划重量当成实际基数生成加重值。
5. P3 限制校验按操作顺序模拟计划变更，覆盖“先重排再按新下标编辑”；
   历史计划恢复也会对恢复内容重新执行当前生效限制。

## 3. 源码修改

| 文件 | 职责 |
|---|---|
| `coach/training_progression/context_service.py` | NextTrainingContext / 计划定位 / 恢复、安全、器械、事实来源；P5-C1.1 comparability 视图与档位来源分级 |
| `coach/training_progression/comparability.py` | 结构可比（方法/组织/编排/左右侧/HIIT 身份签名）与目标达成分类 |
| `coach/training_progression/candidate_rules.py` | A–E 类确定性候选与分类型规则；档位来源门控 |
| `coach/training_progression/progression_service.py` | `get_next_training_options()` 统一入口；plan_proposal 差异提案 |
| `coach/experts/training_science.py` | `analyze_next_training`（P5-C2 确定性解读） |
| `coach/experts/registry.py` / `task_dispatcher.py` / `insight_service.py` | next-training-review 任务登记与版本失效 |
| `coach/equipment.py` | `equipment_version()` 器械/地点指纹 |
| `backend/routes.py` | `GET /users/{uid}/training-progression/{exercise_id}`；experts/analysis 扩展 |
| `frontend/src/components/workout/NextTrainingAdvice.tsx` | 训练科学顾问建议面板 |
| `frontend/src/components/workout/ProgressionOptionCard.tsx` | 候选方案卡 |
| `frontend/src/components/workout/ProgressionEvidence.tsx` | 依据/限制/数据状态展示 |
| `frontend/src/store.ts` | `applySessionTarget` / `revertSessionTarget` / `compatibleTargetPatch` |
| `frontend/src/pages/Workout.tsx` | 动作卡建议入口与撤销 |
| `coach/analytics/exercise_metrics.py` | C0.1 距离口径；输出复杂组/超级组/替换上下文 |
| `coach/analytics/activity_class.py` | 纠错快照继承边界 |
| `coach/changes.py` | P3 限制校验覆盖"编辑既有动作处方"，不能借 API 绕过 |
| `test_p5c1.py` / `test_p5c11.py` / `test_p5c2.py` | 确定性候选 / C1.1 收尾 / C2 集成专项 |
| `test_p5b3.py` | C0.1 边界回归 |

## 4. 事实与候选契约

### NextTrainingContext

包含：

- 用户/动作/实际测量类型/活动类别与分类来源；
- 当前计划 ID/版本、计划日与计划动作；
- `recent_sessions`：最近 60 天实际记录（最多 8 条）；
- `comparable_sessions`：通过口径检查、可用于同类比较的记录；
- `last_actual_performance`：最近一次真实完成情况；
- `current_prescription`：仅当计划上下文属于当前版本且动作身份一致时提供；
- `recovery_context`、`safety_context`、`equipment_context`；
- `data_quality`、`source_revisions`、`fact_refs`。

`recent_sessions` 与 `comparable_sessions` 不互换。比如 60kg×12 和
70kg×3 都可能是真实记录，但如果计划目标是 8–12 次，后者不会进入该目标
范围的可比集合。

### 可比性

两个会话只有在以下**结构**条件成立时才可比（P5-C1.1 起不再包含目标范围）：

- 活动类别一致（力量/持续有氧/间歇）；
- 测量类型一致；
- 复杂组/普通组的方法签名一致；
- 超级组组织一致；
- HIIT 的动作身份、块顺序、工作/休息、轮次编排一致；
- 单侧训练左右侧记录完整。

目标达成情况由 `comparability.target_attainment` 单独给出（结构可比的
会话才分类）；未达标记录保持可比并可参与"完成目标/训练量调整方向"。
RPE 缺失、计划缺失、最近记录不可比等进入 `data_quality` / `limitations`，
不伪造。

### 候选

每条候选包含：

```json
{
  "option_id": "...",
  "category": "maintain|complete-target-reps|increase-load|adjust-volume|observe-recovery",
  "title": "...",
  "proposed_targets": {},
  "basis_fact_ids": [],
  "source_ids": [],
  "data_quality": {},
  "limitations": [],
  "tradeoffs": {"benefits": "", "costs": "", "conditions": ""},
  "action_scope": ["session", "plan"],
  "requires_confirmation": true
}
```

`proposed_targets` 只填当前计划中已存在且校验过的目标字段，或明确的下一档
负重/辅助重量。未知档位时不写具体数值，只提供方向。

## 5. 分类型规则

| 类型 | 规则 |
|---|---|
| 重量×次数 | 至少两次可比训练均在目标次数上沿完成、无高 RPE，才考虑加重；档位只有已验证/用户明确配置来源才写具体数值（P5-C1.1：历史重量差只给方向）；两者都无时只给方向；未达标记录参与"完成目标/调量方向"判断但不触发加重 |
| 自重次数 | 使用次数/额外负重；不套 e1RM；稳定达到目标后只给提高次数/额外负重方向 |
| 辅助次数 | 同时检查完成次数与辅助重量；不会仅因辅助变小宣称进步；稳定完成后才考虑降低辅助（档位来源同上分级） |
| 静态/计时力量 | 按实际保持秒数；不估算 e1RM/负重容量 |
| 持续有氧 | 使用持续时长/距离/配速；无距离不生成配速；单次变快不自动加量 |
| HIIT | 使用实际完成/跳过/工作/休息/经过；不把计划轮次当完成；未稳定完成不增加轮次或缩休息；不同动作编排不可直接比较 |

复杂组不会取第一段重量作为普通组目标；超级组候选保留组织背景，不把
轮间休息误当作每个动作的独立休息。

## 6. 恢复与安全

- 恢复只读取 P2 自报事实：睡眠、疲劳、酸痛、训练意愿、记录日期。
- 无记录只标记未知，不推断“恢复良好”。
- 恢复信号只生成“结合恢复继续观察/调整当次压力”方向，不诊断过度训练、
  不声明表现变化的因果关系，也不自动减少计划组数。
- 在生成候选前调用 P3 `safety_view()`；医疗/隔离/动作限制阻断时返回
  空候选和限制原因，训练记录仍可查看。
- P3 限制现在也覆盖 `edit_set_prescription`：直接调用修改 API 修改受限动作
  的处方同样被拒绝。

## 7. 自动化测试

```bash
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider --confcutdir=/home/johb/fitness-coach-agent \
  test_p5c2.py test_p5c11.py test_p5c1.py test_p5b3.py test_p5b2.py test_p3.py
```

当前结果：**59 passed**。全量后端 **832 passed**；前端 **12 files / 73
tests passed**，TypeScript + Vite 构建通过；浏览器 E2E 场景 A–E 全部通过。

`test_p5c2.py`（P5-C2 专项）覆盖：

1. 只读 API 契约（含顶层 source_revisions/insight 字段）；只查看建议
   不创建提案/洞察、计划版本不变；
2. 用户隔离：其他用户读自己的空数据而非他人记录；未知用户/未知动作
   404；
3. 过期计划上下文：不给处方、给阻断原因；
4. 康复限制：API 返回 allowed=false + 原因；直接编辑 API 422；
5. next-training-review 镜像确定性候选（无未批准的可执行目标、提案
   操作逐字一致、事实引用全部可核）；
6. 生命周期：查看/忽略/重新分析；纠错历史训练 → 洞察失效（修订漂移）
   且候选数据源版本更新；计划更新 → 失效 + 旧提案 422；训练限制变化 →
   失效；地点切换（器械指纹）→ 失效且候选阻断；
7. 恢复事实独立呈现（不做过度训练推断，fact_ids 可核）；
8. HIIT 用自身指标（无 e1RM、complete-interval-plan）；
9. 长期修改统一协议：pending 不改版本 → 确认后 v+1 生效 → 旧版本
   重放 422；确认前计划被其他操作更新 → 提案拒绝生效。

`test_p5c11.py`（P5-C1.1 专项）覆盖：

- 验收 A：目标 8–12 次、最近完成 7 次 → 保持结构可比，仍生成
  "先完成既有目标次数"候选（附达成分类），不给加重；
- 验收 B：会话内 60→70kg 历史重量差 10kg、无已确认档位 → 加重候选
  只给方向；对照：内置动作已验证档位 2.5kg → 仍生成 62.5kg 明确数值；
- 验收 C：开合跳与高抬腿相同间歇计时 → 不可比（动作身份不同）；
  同名自定义活动可比、不同名不可比；只改计时或只换块顺序都破坏可比；
- 目标达成分类边界：at_top / met_min / below_target / above_range /
  混合 / 数据不足；时长目标分类；
- 用户自定义动作 progression 元数据 → `user_exercise_progression_metadata`
  已验证来源，生成明确数值；
- 有氧未达时长目标保持结构可比。

`test_p5c1.py` 覆盖（含 P5-C1.1 语义更新）：

- A：连续两次可比的卧推完成 → 维持 + 适用的精确加重候选（档位来源可见）；
- B：仅一次记录 → 不生成增长/加重结论；70×3 与目标 5–8 次结构可比、
  达成分类为"低于目标次数"，但不因重量更高触发加重（P5-C1.1 更新）；
- C：递减组、执行段、超级组背景；单侧左右不完整不可比；
- D：自重、辅助、持续有氧、HIIT 各用自身指标，不生成 e1RM；
- E：近期高疲劳/短睡眠作为事实，生成恢复观察方向且不诊断；
- F：P3 限制阻断候选，直接编辑受限动作处方 API 返回 422；
- 临时替换：按实际动作建历史，同时保留原计划身份，长期 scope 不开放；
- 未知器械档位：只给方向，不虚构重量；
- 计划版本过期：不引用旧计划目标；
- 计划重量 100kg、实际只完成 60kg：不生成基于 100kg 的加重值；
- 同一打卡重复动作条目：只算一个会话且不可比；
- 先重排再按新下标编辑受限动作：服务端仍返回 422；
- 恢复含受限动作的旧计划：服务端返回 422；
- 超级组：允许方向候选，但不生成数值加重。

## 8. 已知限制 / 未完成

- 洞察解释与候选解释均为确定性打包（与平台其他分析器一致，不调 LLM）；
  LLM 叙事层（复述/自由问答）仍属后续阶段。
- 长期修改目前覆盖 `edit_set_prescription`（组数/次数/负重）；段级/结构类
  候选提案仍属后续。
- 器械没有用户级"实际重量档位表"；已验证来源=内置动作元数据与用户自定义
  动作的 progression 配置，历史重量差只给方向。
- 复杂组/超级组当前只禁用普通数值加重；尚未生成段级进阶数值。
- 数据不足、计划上下文过期、恢复缺失均如实返回限制，不自动补齐。
- 无实体手机测试；E2E 为桌面浏览器（移动视口）验证。
