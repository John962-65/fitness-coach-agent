# P5-B3 交付：统计整合与数据一致性

> 基线：`3ece264` ｜ 日期：2026-10-26 ｜ 状态：**P5-B3 通过，P5-B 全阶段完成；P5-C 未启动**

## 1. 统一活动分类

新增 [`coach/analytics/activity_class.py`](../coach/analytics/activity_class.py)：

| 类别 | 判据 |
|---|---|
| `interval` | `set_log.hiit` 为有效 HIIT 元数据（块、工作秒数、轮次齐全）；优先于有氧动作标记 |
| `steady_cardio` | 非 interval，且动作库/快照标记为有氧 |
| `strength` | 其余记录（含旧的时长型力量动作） |

版本：`activity-class-v1`。

### 快照与旧记录

- 新保存/纠错时，每组写入 `activity_class`、`activity_class_source`、`activity_class_version`。
- 动作库后续变化不会改变已保存快照的语义。
- 旧记录没有快照时，按“有效 HIIT → 动作库 `activity` → 默认 strength”推断，来源标记为 `hiit_metadata`、`exercise_activity_inferred` 或 `legacy_default_inferred`。
- 月历、周期统计和事实结果返回 `classification.inferred_records` 及来源计数；历史页明确提示旧记录为推断，不静默改变含义。
- 未改写任何原始历史行；纠错只产生新修订。

## 2. 指标定义与兼容

### 规范字段

| 字段 | 定义 |
|---|---|
| `training_sessions` | 训练会话数；一次训练记录 = 1，无论包含多少动作或类别 |
| `training_days` | 有训练的不同用户本地日期数 |
| `strength_working_sets` | 仅 `strength` 的非热身逻辑组；复杂组按一条逻辑组，超级组不重复 |
| `strength_volume_kg` | 仅力量组的外部负重×次数；自重/辅助/时长/距离按既有公式为 0 |
| `steady_cardio_seconds` | 仅 `steady_cardio` 的持续时长；不含任何 HIIT |
| `steady_cardio_distance_m` | 仅 `steady_cardio` 的距离 |
| `interval_work_seconds` | HIIT 实际工作秒数 |
| `interval_rest_seconds` | HIIT 实际休息秒数 |
| `interval_elapsed_seconds` | HIIT 记录的实际经过秒数（工作+休息） |
| `interval_planned_rounds` | 计划轮次，不等于完成轮次 |
| `interval_completed_rounds` | 实际完成轮次 |
| `interval_skipped_rounds` | 实际跳过轮次 |
| `interval_ended_early` | 提前结束的 HIIT 记录数 |
| `cardio_by_activity` | 按有氧动作分组的次数、时长、距离、速度、配速；无距离时速度/配速为 `null` |

### 兼容别名（语义已固定）

| 旧字段 | 新语义 |
|---|---|
| `sessions` | `training_sessions` |
| `working_sets` | `strength_working_sets` |
| `volume` | `strength_volume_kg` |
| `cardio_seconds` | `steady_cardio_seconds`；修正 P5-B 曾把 HIIT 也计入的问题 |
| `cardio_distance_m` | `steady_cardio_distance_m` |
| `interval_seconds` | `interval_elapsed_seconds` |

`GET /users/{uid}/training-facts` 新增只读入口；标准会话事实同时存在
`strength_working_sets` 等命名，旧事实名称保留。事实 `data_quality`
附带分类版本与推断来源。

## 3. 跨接口整合

- `training_calendar.py`：月历与周期均由同一分类结果累计。月历日包含力量、有氧、
  HIIT 各自的摘要；`working_sets/volume` 不再混入有氧或 HIIT。
- `exercise_metrics.py`：动作历史附加活动类别；`working_sets/volume/e1RM` 只来自
  力量组，有氧与间歇分别提供持续/工作/休息/经过时长。动作身份按实际执行动作。
- `fact_service.py`：动作级与周期级事实复用同一分类和 `period_summary`；
  HIIT 不进入持续有氧，也不进入力量工作组/容量。
- `progress_analysis.py`：按类别选择趋势指标。HIIT 使用实际工作秒，持续有氧使用
  距离或持续秒；力量类型才使用 e1RM、次数或力量时长口径，并明确不可直接比较。
- `training_science.py`：训练后回顾将力量与有氧/HIIT 分开表达；纯有氧/HIIT 训练
  不再被误作力量报告或直接报“无可分析动作”。

## 4. 替代动作收尾

- 候选最低相关性：必须与源动作有相同动作模式、主要目标肌群重叠，或来自动作库
  明确的替代关联。器械/测量类型兼容不能单独让无关动作入列。
- 无合适候选时返回空列表，并报告 `excluded.unrelated`。
- 不宣称候选与源动作运动学/临床等价；P3 限制与医疗/隔离门优先。
- 训练记录同时保存 `session_replacement`：
  - 原计划动作 ID/名称/计划下标；
  - 实际动作 ID/记录口径；
  - `scope=session`（仅本次训练）；
  - 所属训练即当前 checkin ID。
- 力量、有氧统计按实际动作归类；只本次替换不修改计划版本。长期替换仍走
  ChangeProposal，并在用户确认后才改计划。
- 计划完成事实单独输出 `plan-replacement-sessions`；临时替换不等同于原计划动作
  等价完成。

## 5. 自动化测试

新增 [`test_p5b3.py`](../test_p5b3.py) 固定数据集，覆盖：

- A：卧推 3 组 + 划船 3 组 + 跑步 20 分钟 → 1 会话、6 力量组、3300kg 容量、
  1200 秒持续有氧、0 HIIT；
- B：4 轮 HIIT 实际完成 3、跳过 1、工作 84 秒、休息 66 秒、经过 150 秒、
  力量组 0；
- C：力量+有氧+HIIT 混合日，月历、周期、动作历史、AI 事实逐字段一致；
- D：纠错 HIIT 轮次/跑步距离 → 历史新修订、统计重算、旧洞察失效、新分析引用
  `revision:1`；
- E：杠铃卧推临时替换哑铃卧推 → 计划不变、哑铃历史增加、不记作杠铃执行、
  长期提案确认前不变；
- F：无相关动作通过器械筛选 → 候选为空；
- 快照冻结：动作库类别变化后新记录仍按快照统计；旧记录推断来源可见；
- 无距离有氧：速度/配速为 `null`；
- 趋势：HIIT/持续有氧使用各自指标，不套用 e1RM。

专项：

```bash
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider --confcutdir=/home/johb/fitness-coach-agent \
  test_p5b3.py test_p5b2.py test_p5b.py test_p5.py test_analytics.py test_m65_scenarios.py
```

前端：

```bash
cd frontend && npm test && npm run build
```

最终结果：后端全量 **793 passed**；前端 **11 files / 67 tests passed** 且
TypeScript + Vite 构建通过；动作库 **80** 个校验通过。

## 6. Chrome E2E（390×844）

```bash
PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" node tools/e2e_p5b3.mjs
```

实际结果：

- 混合+替代记录：2 会话、7 力量组、3500kg、持续有氧 1200 秒 / 6000 米、
  HIIT 工作 84 / 休息 66 / 经过 150 秒；月历与周期逐字段一致；
- 历史纠错：修订 v1，统计重算；
- 旧 ExpertInsight 失效，新分析引用 checkin revision 1；
- 替代记录保存原计划 `杠铃平板卧推`、实际 `哑铃卧推`、`scope=session`、
  口径 `weight_reps`；计划版本保持 v1；
- P3 限制下服务端替代校验返回 422。

截图：

1. [历史纠错](p5b3-shots/01-history-correction.png)
2. [月历与力量/有氧周期统计](p5b3-shots/02-calendar-period-stats.png)
3. [HIIT 与配速统计](p5b3-shots/03-hiit-period-stats.png)
4. [替代动作历史与修订](p5b3-shots/04-replacement-history.png)

同时用最终代码重跑了 P5-B2 Chrome E2E，候选现在只包含语义相关动作，截图已更新。

## 7. 数据与已知限制

- 旧记录没有类别快照；动作库改动可能改变推断结果，但接口会显示推断来源与数量，
  不会伪装成保存时快照。要彻底冻结旧语义只能另做受审计迁移，本轮禁止改写历史。
- `interval_elapsed_seconds` 来自实际记录的 duration；不把计划时长补齐为实际。
- 有氧配速只在同一条有距离记录内计算；不同器械/运动类型的速度不可直接比较。
- 混合会话的 `strength_sessions + steady_cardio_sessions + interval_sessions`
  可大于 `training_sessions`（一个会话可含多个类别），这是按类别统计的定义。
- 历史纠错 UI 编辑逐组数值；HIIT 计划/完成轮次的纠错由 API 契约测试覆盖。
- E2E 为系统 Chrome headless，不等同于实体手机测试。
- 未启动 P5-C，不新增训练专家或下一次训练建议。
