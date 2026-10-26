# P5 交付文档（P5-A 里程碑）：专业组法与超级组

> 交付日期：2026-10-25 ｜ 基线：P4（`dab0117`）｜ 状态：**P5-A 已交付，验收通过**
> 总纲见 [expert-platform-roadmap.md](expert-platform-roadmap.md)
> 本文件覆盖 P5-A（P5-0/1/2/3）；P5-B（有氧/HIIT/器械/统计整合）已完成，
> 见 [P5-B1.1](p5b11-verification.md)、[P5-B2](p5b2-equipment-substitution.md)、
> [P5-B3](p5b3-statistics-integration.md)；P5-C 尚未开始。

## 0. 核心设计决策：测量类型 × 训练方法 × 超级组三层分离

| 层 | 承载字段 | 取值 |
|---|---|---|
| 测量类型（不变） | `type` | weight_reps / bodyweight_reps / assisted_reps / duration / distance_time |
| **训练方法（新增）** | `method`（正交可选） | straight_set（缺省）/ drop_set / rest_pause / unilateral |
| 组间组织（不变+增强） | `superset_group` + 执行配置 | A/B/C 标签 + rounds/rest 配置 |

复杂组记录 = `method` + `segments`（执行段数组，每段按 type 的同套字段校验）。
**统计概念严格区分**：逻辑组（1 条记录=1 组）、实际执行段（segments）、
计划组数（target）、左右侧（side）。

## 1. 数据契约与兼容

- 旧记录无 method → 按 straight_set 解释（**不回写、不改原始含义**）；
- 显式 `straight_set` 落库时剥离冗余字段（与旧记录同构）；
- 未知 method → 警告并按普通组记录；空/无效段 → 警告降级普通组（保留
  主级字段）；单侧段缺 side、段缺次数、weight_reps 段缺重量 → 该段剔除；
- 跨链路兼容验证：保存（coerce）→ 聚合派生（routes 代表段）→ 统计
  （exercise_metrics）→ fact_service 说明 → 纠错（同一 coerce 契约）→
  离线队列（submission_id 幂等不受影响）→ 模板（目标不含 method，roundtrip
  回归）。

## 2. 修改文件清单

| 文件 | 变更 |
|---|---|
| `frontend/src/types.ts` | SetMethod/SetSegment 类型；SetRecord 各变体加 method/segments；SetLog 同步 |
| `coach/validate.py` | method/segments 清洗契约（四方法结构校验+降级纪律） |
| `coach/analytics/exercise_metrics.py` | set_volume（分段求和）/set_e1rm（段中最大）/_working_sets（代表段+段和 reps_total+method 透出） |
| `coach/analytics/fact_service.py` | 复杂组说明进 data_quality.notes（"逻辑组计数、容量分段求和、单侧分别执行"） |
| `backend/routes.py` | 聚合派生：method 组代表段=段中容量最大段，reps=段和 |
| `frontend/src/store.ts` | SupersetConfig 类型；supersetConfig 随会话持久化（刷新恢复）；SetDraftValues 加 method/segments 镜像 |
| `frontend/src/pages/Workout.tsx` | SetForm 组法 chips+分段编辑器（增删改段/休息秒）+复制上一组；SupersetBanner（轮次/下一动作/轮间休息/配置/解除）；头部计量按段求和；保存链透传；组表 method 标签 |
| `frontend/src/lib/setDisplay.ts` | formatSetRecord 分段展示（"递减：80kg8次 + 65kg6次"；单侧带左右） |
| `test_p5.py` | 9 项专项回归 |

## 3. 统计规则（P5-7 前置落实）

- **递减组**：80×8 + 65×6 → 容量 1030，逻辑组 1，reps_total 14；
- **休息暂停**：60×8+3+2（段间休息秒数保留）→ 容量 780，逻辑组 1；
- **单侧**：左 12×10 + 右 12×8 → 容量 216（左右各一次，**不简化为
  12×10、不重复计算**），逻辑组 1，左右次数独立保留；
- 热身组不变（不计入正式容量/组数）；
- 有氧/HIIT 不参与（P5-B）；
- fact_service 说明样例："含递减组等复杂组：工作组按逻辑组计数（每条
  记录=1 组），容量按各执行段实际完成求和"。

## 4. 超级组执行（P5-2）

- 分组标签升级为执行能力：每个 A/B/C 组可配 **目标轮次/动作间休息/
  轮间休息**（存 session，刷新恢复）；
- 横幅（每动作卡内）：`超级组 A · 第 2/3 轮` + "← 本动作现在轮到"/
  "下一动作：X"（派生自已记录组数，**不自动编造完成记录**）+ 轮间休息
  按钮 + 配置（跳过/补做/改顺序=直接操作对应动作卡）+ 解除；
- 兼容旧 `superset_group: "A"` 记录（无配置时轮次按最少完成数派生）；
- 休息计时基于绝对时间戳（restEndsAt），手机切后台重开恢复准确剩余时间
  （沿用 M6.4 机制，E2E 刷新断言覆盖）。

## 5. 测试与验收

### 自动化（`test_p5.py` 9 项；全量 759 项通过）
契约（8 例：旧兼容/四方法/空段降级/未知方法/缺 side/显式 straight）、
五测量类型兼容、分段容量数学、逻辑组计数与代表段、单侧保留（API 落库
断言）、fact 说明、纠错重算（1030→890+修订痕+漂移机制）、API 幂等+
聚合派生（代表段 80kg/段和 reps=14）+隔离、模板 roundtrip。
前端 tsc + 52 项 + 构建通过。

### 真实浏览器 E2E（390×844）
- **场景 A**：自由训练完成 普通 60×8 → 递减（80×8+65×6）→ 单侧
  （左 12×10/右 12×8）→ 休息暂停（60×8/3/2 歇 20s），组表分段文案
  正确；**修头部计量 bug 后** 计量=2506 与后端一致；刷新后 4 组完整恢复；
  保存无警告（修下单侧提交 bug 后）；历史页分段展示
  （截图 01/02）；
- **场景 B**：卧推+划船标超级组 A 配 3 轮 → 横幅"第 1/3 轮 · 下一动作"
  → 交替记录 → **中途刷新**：已记录组不丢、配置恢复、轮次与下一动作
  正确（[3,1] → 第 2/3 轮+下一动作：杠铃划船）；保存 5 逻辑组分动作
  统计正确（卧推 3/1700、划船 2/1000）。

### 实际发现并修复的问题
1. **头部计量未按段求和**（显示 480 应为 2506）→ segVolume 与后端同公式；
2. **单侧组提交静默失败**：method 分支在 validateSetDraft 之后且 errRow
   被主输入分支隐藏 → 分支前移（E2E 抓出——UI 显示 4 组而后端只存 3 条）；
3. **轮次计算把自由训练的空目标（0）纳入 min** → 恒为第 1 轮 → 修复；
4. E2E 定位污染：动作卡 filter(hasText"划船") 匹配到横幅里的"下一动作：
   杠铃划船"导致组记错卡——改 heading 定位（测试脚本问题，非应用缺陷；
   反向验证了"下一动作"提示的真实性）。

## 6. 已知限制与后续计划（P5-B/P5-C）

1. 分段编辑草稿镜像为 JSON 字符串（SetDraftValues.segments）——功能正确
   但类型偏弱，P5-B 顺手类型化；
2. 超级组"跳过某动作/单独补做"当前=直接操作动作卡（无专门跳过按钮）；
   轮间休息按钮仅在全员完成一轮后出现——手动休息可用既有休息计时；
3. 训练总时长显示（started_at 已存，头部未展示）与 HIIT 结构化计时属
   P5-B/P5-C；
4. 下一次训练建议、progress_analysis 对复杂组的趋势口径（代表段 vs 段和）
   属 P5-C 统计整合；
5. 器械管理与替代动作属 P5-B。
