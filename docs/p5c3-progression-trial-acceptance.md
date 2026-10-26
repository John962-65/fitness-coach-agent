# P5-C3 训练进阶闭环与个人尝试——交付与验收

> 基线：`1e88513`（P5-C2）｜ 日期：2026-10-27
> 状态：**P5-C3 已交付；P5（专业训练系统）全部完成，P6 未启动**

## 1. 本阶段范围

不新增进阶算法，只解决闭环：

**实际采用建议 → 执行训练 → 保存真实结果 → 观察变化 → 用户复盘决策。**

## 2. P5-C3-A：P5-C2 交付审计结果

按总任务书 1.2 逐项核对 `0b222bc`/`1e88513`，全部达标，两项小修：

| 审计点 | 结论 |
|---|---|
| 候选稳定 ID 与动作/计划位置关联 | 达标：`option_id` + 上下文 exercise/day/index；`plan_proposal` 携带 day+index |
| 排序/替换后不应用到其他动作 | 达标：排序变更产生新计划版本 → 旧提案 confirm 被版本锁拒绝。**小修**：替换动作后撤销该卡"仅本次"目标（`replaceExercise` 恢复应用前原值），避免把原动作候选带到替代动作 |
| 仅本次采用边界（组/组法/超组/计时器/HIIT 状态） | 达标（P5-C2 store 测试 + E2E 复验） |
| 长期修改由服务端构造 | **新增**：`POST /users/{uid}/training-progression/{exercise_id}/adopt` 只收 `option_id`，服务端重算候选后取对应 `plan_proposal` 构造提案；前端不再提交 `proposed_targets` |
| pending 期间版本不变 / 确认重校验 / 过期拒绝 / 重复确认幂等 | 达标：`confirm_proposal` 非 pending 一律拒绝（回归测试覆盖） |
| 洞察五类失效 | 达标；**小修**：分析后**新增**恢复记录也会使旧洞察失效（`recovery_records_count` 漂移检查，不只盯已引用记录） |

## 3. P5-C3-B：PersonalTrial 接入（复用，不建第二套）

复用 C4/M6.5-4 的 `personal_trials` + `trial_evidence`：

- **创建**：`POST /users/{uid}/training-progression/{exercise_id}/trial`
  `{option_id, window_days?, min_sessions?}`——服务端重新计算候选，
  写入关联字段（老库迁移补列，均可空）：
  `origin{kind, origin_insight_id, origin_option_id, rules_version}`、
  `exercise_id`、`plan_id/plan_version`、`chosen_target`、
  `observation_metric`、`observation_window_days`、`min_sessions`、
  基线快照（`p5c_trial_baseline_v1`：尝试前真实表现 + 达成分类）与
  `baseline_source_revisions`（checkins/plan/restrictions/equipment/rules）。
  约束：同一时间一个活跃尝试；无目标字段的候选（如恢复观察）与被安全
  阻断的候选不能创建。
- **观察**：`GET /users/{uid}/trials/{trial_id}` 返回观察期真实训练
  （仅尝试开始后的会话）× 观察指标的确定性判定：
  `target-completion`（达成分类，与进阶引擎同口径）/ `duration-attainment`
  / `steady-cardio-seconds` / `interval-completion`；到达窗口或
  `min_sessions` 即 `due_for_review`；计划版本变化标记同期混杂。
- **复盘**：`?review=1` 生成草稿，严格分节——已观察（尝试前基线 vs
  期间记录）/ 可能解释 / 无法确认（混杂、样本不足、计划版本变化），
  不把 AI 预测当结果，不因成绩变化宣称因果。
- **决策**：`POST /users/{uid}/trials/{trial_id}/decision`
  `keep / adjust / stop / observe`。observe=暂不判断继续观察（延长窗口、
  保持 active）；其余结束尝试并留痕复盘。**任何分支都不自动修改计划**；
  keep 返回提示：写入长期计划请走「申请修改长期计划」确认流程。
- **前端**：建议面板新增「开始个人尝试」；「我的 → 个人尝试」新增
  观察进展与复盘决策面板（`TrialProgress`）。

## 4. P5-C3-C：完整数据回归（test_p5c3.py + 全量）

`test_full_forms_regression_facts_trials_consistency` 一次覆盖：普通力量组、
递减组、单侧、超级组、有氧（时长处方）、HIIT、动作替代（长期 scope 关闭）、
自由训练、计划训练、历史纠错（观察读取纠错后修订）；离线/刷新恢复由前端
store 测试与 E2E 补充。

```bash
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider --confcutdir=$PWD test_p5c3.py
```

专项 **8 passed**；全量后端 **840 passed**；前端 **13 files / 74 tests**，
TypeScript + Vite 构建通过。

新增测试覆盖：服务端 adopt 构造提案（未知/过期 option_id 422）、pending
版本不变、重复确认 422、旧 base_version 重放 422；尝试关联字段与基线、
单活跃约束、观察计数（达标/未达标）、复盘分节与四决策、决策不改计划、
observe 延长窗口、无目标/被阻断候选 422、恢复数据新增使洞察失效。

## 5. P5-C3-D：真实浏览器 E2E（截图在 `docs/p5c3-shots/`）

| 场景 | 结果 |
|---|---|
| A 仅本次调整 | 面板选加重候选 → 仅本次采用 → 记录 62.5×8 一组 → 完成训练 → 保存记录 `barbell_bench_press 62.5×8`，计划仍 v1、无提案；刷新后"仅本次"标记与目标保持 |
| B 长期计划 | 面板申请修改（服务端 adopt）→ pending → 确认 → v2 生效；旧上下文候选再提交被 422；确认后面板显示"计划上下文已过期"并关闭可执行动作 |
| C 个人尝试 | 面板开始尝试 #1（候选重算为 65kg）→ 记录两次观察期训练 → 到达观察条件 → 我的页复盘草稿（已观察/无法确认）→ 暂不判断继续观察（窗口延长）→ 保留当前安排（结束留痕，计划不变，提示走确认流程） |
| D 数据纠错 | 请求 AI 解释（insight ready）→ 纠错历史 → 洞察「已失效」+原因+重新分析入口；纠错后候选重算（上沿判定随之变化） |

E2E 过程中引擎行为全部符合确定性预期（例如只完成 1 组/未到上沿时拒绝
给出加重候选——数据先补正，候选才出现）。

## 6. 交付

- Commit：见 `P5-C3 — 训练进阶闭环与个人尝试`
- 修改文件：`coach/db.py`（迁移+尝试字段）、`coach/training_progression/
  trial_service.py`（新）、`coach/experts/{training_science,insight_service}.py`、
  `backend/routes.py`（adopt/trial/detail/decision 路由）、
  `frontend/src/{api.ts,types.ts,store.ts,pages/Mine.tsx,pages/Workout.tsx,
  components/workout/NextTrainingAdvice.tsx}`、`test_p5c3.py`、
  `frontend/src/store.test.ts`
- 数据模型：`personal_trials` 增列（可空，向后兼容，老数据 NULL）
- API 契约：见 §3；错误统一 422（候选过期/安全阻断/约束冲突）
- 已知问题：无 P0/P1；截图采集在系统高负载时可能超时（工具侧，非产品）

## 7. P5 阶段标记完成

P5-A（组法）、P5-B（有氧/HIIT/器械/统计）、P5-C1/C1.1/C2/C3（确定性候选
→ 产品化 → 闭环）全部交付。**P5 完成。**

下一阶段：P6 跨专家协作（按总任务书分三次提交：P6-A 事实包与任务、
P6-B 三个联合场景、P6-C 工作台与评测）。
