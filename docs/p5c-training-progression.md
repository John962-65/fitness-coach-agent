# P5-C 训练进阶与下一次训练建议

> 基线：`903d6ca` ｜ 日期：2026-10-26
> 当前状态：**P5-C1 确定性候选引擎已交付；P5-C2/C3 未启动**

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
| `coach/training_progression/context_service.py` | NextTrainingContext / 计划定位 / 恢复、安全、器械、事实来源 |
| `coach/training_progression/comparability.py` | 记录类型、方法、左右侧、超级组、HIIT 编排和目标范围的可比性 |
| `coach/training_progression/candidate_rules.py` | A–E 类确定性候选与分类型规则 |
| `coach/training_progression/progression_service.py` | `get_next_training_options()` 统一入口 |
| `coach/analytics/exercise_metrics.py` | C0.1 距离口径；输出复杂组/超级组/替换上下文 |
| `coach/analytics/activity_class.py` | 纠错快照继承边界 |
| `coach/changes.py` | P3 限制校验覆盖“编辑既有动作处方”，不能借 API 绕过 |
| `test_p5c1.py` | 确定性候选专项 |
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

两个会话只有在以下条件成立时才可比：

- 活动类别一致（力量/持续有氧/间歇）；
- 测量类型一致；
- 复杂组/普通组的方法签名一致；
- 超级组组织一致；
- HIIT 的块、工作/休息、轮次编排一致；
- 力量次数落在当前目标范围；
- 单侧训练左右侧记录完整。

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
| 重量×次数 | 至少两次可比训练均在目标次数上沿完成、无高 RPE，才考虑加重；档位优先用动作进阶元数据，其次从同动作实际负荷差推断；两者都无时只给方向 |
| 自重次数 | 使用次数/额外负重；不套 e1RM；稳定达到目标后只给提高次数/额外负重方向 |
| 辅助次数 | 同时检查完成次数与辅助重量；不会仅因辅助变小宣称进步；稳定完成后才考虑降低辅助 |
| 静态/计时力量 | 按实际保持秒数；不估算 e1RM/负重容量 |
| 持续有氧 | 使用持续时长/距离/配速；无距离不生成配速；单次变快不自动加量 |
| HIIT | 使用实际完成/跳过/工作/休息/经过；不把计划轮次当完成；未稳定完成不增加轮次或缩休息 |

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
  test_p5c1.py test_p5b3.py test_p5b2.py test_p3.py
```

当前结果：**42 passed**。最终全量后端 **809 passed**；前端 **11 files / 67
tests passed**，TypeScript + Vite 构建通过；动作库 **80** 个校验通过。

`test_p5c1.py` 覆盖：

- A：连续两次可比的卧推完成 → 维持 + 适用的精确加重候选（档位来源可见）；
- B：仅一次记录 / 70×3 与目标 5–8 次不可比 → 不生成增长/加重结论；
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

- 本轮没有接入 `next-training-review` ExpertInsight，也没有训练页面候选面板；
  这些属于后续 P5-C2。
- PersonalTrial 轻量接入、仅本次采用/长期确认 UI、Chrome E2E 属于后续 P5-C3。
- 器械没有用户级“实际重量档位表”；目前使用动作进阶元数据或历史负荷差，
  未知时只给方向。
- 复杂组/超级组当前只禁用普通数值加重；尚未生成段级进阶数值。
- 数据不足、计划上下文过期、恢复缺失均如实返回限制，不自动补齐。
- 无实体手机测试；本阶段尚未做浏览器 E2E。
