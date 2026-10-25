# P2 交付文档：身体数据与恢复管理

> 交付日期：2026-10-25 ｜ 基线：P1（`4a2a67b`）｜ 状态：**已交付，验收通过**
> 总纲见 [expert-platform-roadmap.md](expert-platform-roadmap.md)

## 0. 交付范围

P2 交付：统一身体测量存储与趋势、每日恢复记录（1-5 主观量表）、确定性
恢复分析与训练前简报、恢复顾问工作台、身体×营养与训练×恢复联动。
**不做**医学诊断、症状记录与康复处方（P3）；不重做专家任务系统/知识库/
训练统计/营养计算（全部复用 P0/P1）。

## 1. P2-0 审计结论与兼容方案

现有 `checkins` 支持 type='body'（仅 weight_kg/waist_cm 清洗，History 页
可筛"身体"，agent 可打卡/纠错）。兼容方案（单一权威存储，无两套矛盾历史）：

1. 新 `body_measurements` 为**唯一权威存储**；
2. 启动时一次性迁移：旧 body 打卡 → 测量记录（`migrated_from=checkin:{id}`、
   method=import），原行保留并写入 `_migrated` 标记（幂等；无法解析的历史行
   原样保留不丢、不打标）；
3. `Database.record_checkin` 对 type='body' **统一拦截转发**到测量模块——
   旧接口（含 agent 打卡）无感，此后不再产生新的 body checkins 行；
4. 档案体重更新不回写历史测量（体重历史只属于测量表）。

## 2. 修改文件清单

### 后端（新增）

| 文件 | 职责 |
|---|---|
| `coach/body/__init__.py` | 包纪律（单一权威存储/NULL≠0/来源可比性） |
| `coach/body/measurement_service.py` | 录入/修订/删除/迁移/版本锚；指标独立校验；成分数据强制方法 |
| `coach/body/body_metrics.py` | 确定性指标：最近/均值/首末变化/频率/缺口/来源可比性说明 |
| `coach/body/trend_service.py` | 多窗口趋势（7/30/90/全部；只返回实际数据点） |
| `coach/recovery/__init__.py` | 包纪律（量表方向统一/未填≠正常/观察≠推断/无综合评分） |
| `coach/recovery/checkin_service.py` | 校验/当天一条（修订）/删除/版本锚；异常疼痛提示就医 |
| `coach/recovery/recovery_metrics.py` | 窗口均值/高分计数/区域汇总 + 训练负荷上下文（复用 fact_service） |
| `coach/recovery/recovery_analysis.py` | 恢复回顾分析器 + 训练前简报（均确定性，无 LLM） |
| `test_p2.py` | 10 项专项回归（三场景全覆盖） |

### 后端（修改）

| 文件 | 变更 |
|---|---|
| `coach/db.py` | 新增 5 表（body_measurements/revisions、recovery_checkins/revisions、record_submissions）+ 方法；`record_checkin` body 拦截 |
| `coach/experts/registry.py` | recovery 工作台 ready；注册 recovery-review；nutrition 订阅 BodyMeasurementRecorded |
| `coach/experts/insight_service.py` | 漂移检测扩展：恢复日版本 + 身体测量修订 |
| `coach/experts/evidence_validator.py` | source_ids 支持 body:/recovery: |
| `coach/nutrition/nutrition_analysis.py` | 体重上下文联动（相关观察非因果；不完整记录不声称摄入不足） |
| `backend/routes.py` | 新增 12 个 P2 API |
| `backend/app.py` | 启动执行旧 body 打卡迁移（幂等） |
| `test_experts.py` | 适配 P2 合法变化（WorkoutSaved 双顾问/recovery ready） |

### 前端（新增）

| 文件 | 职责 |
|---|---|
| `src/pages/BodyMetrics.tsx` | 身体数据页（/mine/body）：概览/快速记录/趋势（指标+窗口切换）/历史 |
| `src/pages/experts/Recovery.tsx` | 恢复工作台（/experts/recovery）五区 |
| `src/components/body/MeasurementForm.tsx` | 快速记录/编辑（指标全可选、成分必选方法、修订留痕） |
| `src/components/body/BodyHistory.tsx` | 历史列表（编辑/删除/修订记录查看） |
| `src/components/recovery/RecoveryQuickCheckin.tsx` | 30 秒打卡（量表方向文案统一、异常疼痛提示） |
| `src/lib/body.ts` + 测试、`src/lib/recovery.ts` | 展示工具（NULL≠0、变化带符号、量表文案） |

### 前端（修改）

App.tsx（/mine/body、/experts/recovery 路由）、Today.tsx（训练前简报卡）、
Mine.tsx（身体数据入口）、api.ts/types.ts。

## 3. 数据模型与兼容

```
body_measurements        指标全可选(NULL=未测)、measured_at/local_date/timezone、
                         measurement_method/device_source、migrated_from、updated_at
body_measurement_revisions  修订快照（old/new/reason/evidence，同训练打卡纪律）
recovery_checkins        UNIQUE(user_id, local_date) 当天一条；量表 1-5 全可选；
                         soreness_regions JSON；updated_at
recovery_revisions       修订快照
record_submissions       body/recovery 通用幂等提交（重放返回既有结果，不覆盖）
```

## 4. API（12 个）

`GET/POST /users/{uid}/body-measurements`（列表含 start/end 过滤；POST 幂等）、
`PATCH/DELETE .../{id}`、`GET .../{id}/revisions`、
`GET .../body-summary?days=`、`GET .../body-trend?metric=&days=`、
`GET/POST /users/{uid}/recovery-checkins`（当天一条，更新需 reason+evidence）、
`DELETE .../{id}`、`GET .../recovery-summary?days=`、
`GET .../pre-training-recovery-brief`。

**权限与边界说明**：所有接口按 user_id 严格隔离（测试覆盖跨用户 404/空集）；
但当前部署模式为本地单用户 + 访问令牌，尚无多用户身份认证——uid 不构成
完整访问控制（与 2.0 §10.1 一致，云端多用户前必须建立真实认证）。

触发链：
- 恢复增删改 → `RecoveryRecorded`（锚=日期+恢复版本+窗口版本）→ recovery-review；
- 训练保存 → `WorkoutSaved` → recovery-review（负荷上下文更新）+ training_science；
- 身体记录/修订 → `BodyMeasurementRecorded`（锚=body_version）→ 当天有饮食时
  营养日回顾重跑；
- 训练纠错/恢复修订/身体修订 → 对应洞察**懒失效**（读取时比对版本）。

## 5. 确定性分析纪律

**身体**：均值/首末变化/频率/缺口均为可计算观察；体重短期波动不解读为
脂肪变化（写入限制）；多来源并列时输出可比性说明；记录少只显示实际数据点。

**恢复**：输出 observations/data_quality/limitations/evidence_refs；
"最近 3 次记录中 3 次疲劳≥4（自报）"是可计算观察；**"过度训练"等推断
绝不输出**（有测试断言文本）；无综合评分；量表方向全局统一
（疲劳 5=非常疲劳），未填维度进入 data_quality，不从训练量反推主观疲劳。

**训练前简报**（确定性，不落库）：restricted（医疗隔离/计划隔离优先）→
caution（最新自报信号偏高：调低一档/休息观察/状态可以照练，三方向并列）→
clear。选项是参考方向而非指令；修改长期计划仍走 ChangeProposal 确认。

**联动**：营养洞察附加体重上下文（weight-context 发现，引用
body:ID:revision:N，"相关观察——不能断言当前摄入导致体重变化"）；
恢复洞察引用训练负荷（checkin 追溯链）；各专家只读本领域+明确授权的
上下文数据，互相不编造（测试断言：营养发现不含 recovery 来源，
恢复发现不谈摄入）。

## 6. 测试与验收

### 自动化
- `test_p2.py` 10 项：场景 A（记录→趋势→编辑→修订保留→统计更新→版本错拒绝）、
  迁移幂等与解析失败保留、体重修订→营养洞察失效、场景 B（校验/只记一项/
  训练触发/无评分/无过度训练文本/幂等重放）、更新需原因+失效、训练纠错→
  恢复洞察失效、无数据不伪造、场景 C（各专家数据隔离断言）、简报三态、
  幂等提交与导出隔离；**全量 732 项通过**（test_experts 5 项适配 P2 合法变化）。
- 前端：tsc 零错误；Vitest 52 项（+3）；生产构建通过。

### 真实浏览器端到端（390×844）

**场景 A**：身体页记录三次体重+腰围（趋势 -1.2kg/-1cm）→ 编辑第二次
（74.2→75.0）→ 概览与趋势实时更新、历史显示"已修订 r1"（截图 01）。

**场景 B**：恢复工作台快速打卡（30 秒，量表方向文案展示）→ API 补两天
高疲劳 → 完成卧推训练 → 今日修订疲劳 2→4（走修订，留痕 r1）→ 简报转
caution："最新自报信号偏高"，三方向并列（调低一档/休息观察/照练）
（截图 02/03）→ 分析页洞察链（每次变化重分析、旧的失效留痕）→
详情证据（窗口均值+负荷上下文+区域）→ 建议页方案取舍（截图 04/05）。
**全程未打开聊天**。

**场景 C**：体重×饮食×恢复×训练并存 → 营养洞察含 weight-context
（"近 30 天 74.8→75kg…相关观察，不能断言当前摄入导致体重变化"，引用
body:1/2/3 含修订）→ 今日页同时展示训练前简报卡+三个领域的专业分析卡
（截图 06）→ 专家中心三个工作台 ready（截图 07）。

### 实际发现并修复的问题
1. 恢复洞察版本锚与漂移检测格式不一致（id:rev vs id:rev:updated_at）→
   统一用 checkin_service.version()（修后验证双向：未修改 ready、修订失效）；
2. SCALES 未导入导致恢复快照崩溃；
3. BodyMeasurementRecorded 未订阅营养顾问 → 补注册（仅当天有饮食时触发，
   避免无分析对象的失败任务噪音）；
4. 恢复洞察负荷发现文本用英文 metric 名 → 中文标签。

## 7. 已知限制与未完成事项

1. **体重×目标方向一致性**：偏好中未提供 weight_direction 字段 UI（后端已
   预留 preferences.weight_direction 读取），P2 仅呈现变化本身；
2. 恢复趋势图基于近 14 天 summary 的记录序列（90 天窗口需翻页，暂满足
   快速回看；长期序列待 P7 数据导出/报告）；
3. 旧 body 打卡迁移后，History 页仍显示原行（带"已迁移"数据标记但不渲染
   徽标）——后续可在 History 页加显式标记；
4. agent 的 body 纠错工具对已拦截的 body 打卡返回"记录不存在"（新数据在
   测量表），用户经身体页纠错；agent 链路适配留待下轮；
5. 症状记录/安全分流/康复辅助属 P3；恢复页已预置"异常疼痛→就医评估"提示；
6. 多用户认证缺失（本地单用户模式边界，同 P0/P1）。
