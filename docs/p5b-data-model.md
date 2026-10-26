# P5-B0 数据模型审计与兼容方案（有氧 / HIIT / 器械）

> P5-B1 依据文档。审计对象：WorkoutSession / Workout.tsx / SetRecord /
> validate.py / exercise_metrics / training_calendar / fact_service / 模板 /
> 历史纠错 / 离线保存。

## 1. 三概念分层（沿用 P5-A，扩展活动类别）

| 层 | 字段 | 本阶段变化 |
|---|---|---|
| **活动类别（新增）** | 动作库 `activity` 字段（strength 缺省 / cardio） | 有氧动作以内置库 yaml 标注；稳定 exercise_id |
| 测量类型（不变） | `type` | 有氧复用 `duration` / `distance_time`；跳绳可携带可选 reps |
| 训练方法（不变） | `method`（P5-A） | 有氧/HIIT 不使用复杂组方法 |
| 组间组织（不变） | `superset_group` | HIIT 有独立编排结构（hiit 元数据），不塞进超级组 |

## 2. 有氧：混合进现有会话，不建第二套执行生命周期

- 有氧条目 = **同一 WorkoutSession 的一个 entry**（`activity: 'cardio'`），
  完成后产出既有类型的 set_log 记录：
  - 跑步/骑行/划船机/快走 → `{type:'distance_time', distance_m, duration_seconds, rpe?, at}`
  - 椭圆机/爬楼梯 → `{type:'duration', duration_seconds, rpe?, at}`
  - 跳绳 → duration 或携带可选 `reps`（次数口径）
- 执行器状态（开始/暂停/恢复）为**前端执行期状态**，落 localStorage
  （store 持久化）；**完成时的落库数据只有实际结果**——与力量组同一套
  保存/离线/幂等/纠错链路；
- 计时 = `Date.now() - startedAt - 累计暂停时长`（纯时间戳差，不依赖
  setInterval 累计；后台返回按时间戳重算，后台经过时间**如实计入**
  （现实中有氧在后台继续），用户可手动修正时长后保存）；
- 兼容：duration/distance_time 类型早于本阶段存在（平板支撑等），
  旧记录口径不变。

## 3. HIIT：独立编排结构，执行结果仍属现有会话

- 完成落库：HIIT entry 的 set_log = 1 条
  `{type:'duration', duration_seconds:<实际活动秒>, hiit:{...}, rpe?}`
  ——`hiit` 元数据（新契约）承载：

```json
{
  "name": "四轮间歇训练",
  "blocks": [{"name": "开合跳", "exercise_id": "jumping_jack",
               "work_seconds": 30, "rest_seconds": 30, "rounds": 4}],
  "planned_rounds": 4,
  "completed_rounds": 3,
  "work_seconds_done": 84, "rest_seconds_done": 66,
  "skipped": [{"block": 0, "round": 4}],
  "ended_early": true, "end_reason": "用户提前结束"
}
```

- validate.py 契约：hiit 为可选对象；rounds 0-999；秒数 0-86400；块 1-12；
  非法字段剔除不炸整条；
- **状态机（前端执行器）**：idle / running_work / running_rest / paused /
  completed / stopped_early。阶段推进=检查时间戳差；**后台跨阶段规则
  （保守）**：恢复时若后台经过时间越过当前阶段，状态转 paused 并提示
  "后台可能错过阶段切换，请确认实际完成"——用户确认前不自动补记多个
  阶段（满足"计时完成≠已完成运动"）；
- 模板：TrainingTemplate.doc 增加可选 `hiit` 字段（与 entries 互斥或共存的
  HIIT 模板），复用同一模板 CRUD 与会话体系。

## 4. 统计口径（P5-B1 落地部分）

- 力量容量：有氧/HIIT 记录天然无 kg 容量（duration/distance_time 不参与
  set_volume 公式）——**力量容量自动不含有氧**；
- 有氧不生成 e1RM（非 weight_reps）；
- fact_service 新增汇总事实（window/source_ids/口径同现有纪律）：
  `cardio-sessions / cardio-total-duration / cardio-total-distance`、
  `interval-sessions / interval-planned-rounds / interval-completed-rounds /
  interval-work-seconds`（判定依据=动作 `activity:'cardio'` 与 set_log
  `hiit` 元数据）；
- period-summary 增加 cardio_seconds / cardio_distance_m / interval_seconds；
- 历史纠错：hiit/有氧记录走同一 revise 链 → 洞察漂移自动生效。

## 5. 器械（P5-B3 预告，本轮不实施）

动作库 `equipment` 字段已有（数组）；器械 ID 稳定化与地点配置将在
P5-B2 设计，本轮仅保证新增有氧动作的 equipment 用规范 ID。
