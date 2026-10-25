# P3 交付文档：运动康复与伤痛风险辅助系统

> 交付日期：2026-10-25 ｜ 基线：P2（`808fbbc`）｜ 状态：**已交付，验收通过**
> 总纲见 [expert-platform-roadmap.md](expert-platform-roadmap.md)

## 0. 交付范围与定位

康复与伤痛风险顾问工作台：症状记录（SVG 人体图）、确定性安全分流、
多来源训练限制、专业安排跟踪。定位是**运动健康辅助工具**——不提供
疾病诊断、个体化医学治疗或临床康复处方（工作台顶部醒目声明）。

第一里程碑（不适记录+人体图+分流+限制集成）与专业安排跟踪、跨专家
协作均在本轮交付。

## 1. P3-0 安全体系审计报告

| 既有安全层 | 位置 | 行为 |
|---|---|---|
| 医疗许可 | `coach/medical.py training_permission()` | 健康筛查原话 → prohibited/pending/limited/allowed；禁止/不明确优先于许可；个人医嘱自述只能收紧 |
| 计划隔离 | `profile.plan_fence` | 隔离期计划编辑/恢复一律拒绝 |
| 伤病关节高压 | `changes._validate_plan` | 伤病关节 + 动作 joint_stress≥阈值 → 拒绝加入 |
| pain_flags | 档案 conditions | 待跟进安全记录（今日页展示） |
| 统一修改协议 | `coach/changes.py` | AI 提案确认门；手动编辑同一套安全校验 |

**P3 不新建许可判断**：`safety_integration.safety_view()` 合并上述各层 +
新 TrainingRestriction，作为唯一组合视图供计划校验与各顾问读取。
**优先级规则**：医疗 prohibited/pending > plan_fence > 限制集；多条限制
**并集生效**（互不覆盖——某专家未发现风险不能覆盖另一来源的明确限制）。

## 2. 修改文件清单

### 后端（新增）

| 文件 | 职责 |
|---|---|
| `coach/rehab/triage_rules.py` | **确定性分流规则库**（见 §3 规则清单；版本可审计） |
| `coach/rehab/symptom_service.py` | 症状事件+观察（历史不覆盖）；保存时同步分流；triage_recommended 限制维护（只收紧不放松） |
| `coach/rehab/restriction_service.py` | 限制创建/解除纪律（professional 需专业人员说明≥10 字）/计划校验匹配（关节压力+显式动作） |
| `coach/rehab/safety_integration.py` | 统一安全视图（多来源并集）+ `validate_plan_change` |
| `coach/rehab/analysis.py` | symptom-review 确定性洞察（症状事实+分流结果+限制+专业安排；无诊断） |
| `test_p3.py` | 10 项专项回归 |

### 后端（修改）

| 文件 | 变更 |
|---|---|
| `coach/db.py` | 新增 7 表（episodes/observations/restrictions/revisions/care_plans/activities/logs）+ 方法 |
| `coach/changes.py` | `_validate_plan` 集成 `validate_plan_change`（手动与 AI 路径同门） |
| `coach/experts/registry.py` | rehabilitation ready；symptom-review 任务注册；SymptomReported/Updated/RestrictionChanged 订阅 |
| `coach/experts/insight_service.py` | 漂移检测扩展：症状版本 + 限制版本 |
| `backend/routes.py` | 新增 12 个 P3 API（含 `/rehab/triage-preview` 无状态分流预览） |
| `test_experts.py` | 适配 rehabilitation ready |

### 前端（新增/修改）

| 文件 | 职责 |
|---|---|
| `src/pages/experts/Rehabilitation.tsx` | 工作台四区（不适记录/训练限制/专业安排/咨询）+ 定位声明 |
| `src/components/rehab/BodyMap.tsx` | SVG 人体图（正/背面、左右热点、多选） |
| `src/lib/rehab.ts` | 分流四态配色/区域标签 |
| App.tsx、api.ts、types.ts | 路由与客户端 |

## 3. 风险规则清单（`rehab-rules-1`，来源=公开常识性安全提示，非临床指南）

**关键词规则**（否定感知：忽略"消/退/不/无/没"紧邻前缀与"正常/没问题"后缀）：

| 规则 ID | 触发词（节选） | 分流 | 限制提示 |
|---|---|---|---|
| rf-cardiovascular | 胸闷/胸痛/心悸/呼吸困难/头晕/眩晕/晕厥 | urgent | 暂停全部训练 |
| rf-trauma-unable-weightbearing | 无法负重/站不起来/剧痛/撕裂感/听到响声 | urgent | 暂停相关部位 |
| rf-swelling-deformity | 肿胀/肿起来/越来越肿/肿了/发烫/红肿/变形 | urgent | 暂停相关部位 |
| rf-night-rest-pain | 夜间痛/静息痛/睡觉痛醒/休息也痛 | professional | 暂停相关部位 |
| rf-numbness-radiating | 麻木/放射/无力/拿不住/手脚麻 | professional | 暂停相关部位 |
| rf-locking-giving-way | 交锁/卡住/打软腿/不稳 | professional | 暂停相关部位 |
| rf-fever-systemic | 发烧/发热/寒战 | professional | 发热期暂停 |

**结构化规则**：持续 ≥14 天或加重（persistent-worsening）、影响日常活动
（daily-limitation，否定感知）→ professional；轻度（severity≤4、<7 天、
无功能受限）→ general_information；其余 → **uncertain**
（"未报告危险症状不代表没有风险"写入文案）。

**纪律**：severity 不单独定级（severity=9 无红旗 → uncertain，有测试）；
分流保存路径同步执行（monkeypatch 掉任务系统后仍即时返回，有测试）；
规则版本在洞察与 UI 中展示；**专业审核缺口**：规则内容由系统按公开常识
整理，标注 `system_default（待专业审核）`——上线前需合格专业人员复核
（§8）。

## 4. 训练限制集成说明

- **TrainingRestriction** 三来源：user_reported / professional /
  triage_recommended（分流自动创建，标注"待确认"）；
- **解除纪律**：user_reported 用户附依据即可；professional 必须附专业人员
  解除说明（≥10 字，如复诊结论原文）——AI 短依据被拒（有测试）；
  triage 缓解后**不自动解除**，设 review_at 提醒复核；
- **计划修改强制**：`changes._validate_plan` 调用 `validate_plan_change`——
  新增动作的 joint_stress（≥2）或显式 movements 命中限制区域 → 422；
  手动编辑与 AI stage 同门（有测试）；不受限动作正常加入（用户保留
  训练决策权）；
- **洞察失效**：症状/限制版本进 source_revision，任何记录变化 →
  引用旧版本的洞察 invalidated（有测试）。

## 5. 测试与验收

### 自动化（`test_p3.py` 10 项；全量 742 项通过）

规则资产与版本/分流矩阵（8 例 + mild 与 severity 边界）/场景 A 历史
不覆盖/场景 B urgent 自动限制+缓解不解除/场景 C 手动编辑拦截+AI 路径
拦截+解除纪律/场景 D 无诊断词断言+隔离/场景 E 三次观察→洞察失效+
专业安排打卡幂等/分流与任务解耦/事件去重。前端 tsc+52 项+构建通过。

### 真实浏览器 E2E（390×844）

- **A**：人体图（正面）点右膝 → 填轻度描述 → **实时分流预览"一般情况
  说明"** → 保存 → 列表与展开历史（截图 01）；
- **B**：膝左报"越来越肿、发烫、走路困难" → 预览"**建议尽快就医评估**"
  → 保存 → 事件卡红色提示（截图 02/03）→ 限制 tab 显示自动创建的
  安全分流限制（覆盖膝，含规则 ID 依据）（截图 04）；
- **C**（API 层）：手动编辑加深蹲 422（限制冲突）；哑铃卧推可加；
  AI 提案路径同门；专业限制短依据解除被拒、专业人员说明解除成功；
- **E**：专业安排录入（来源必填）→ 活动打卡 → 同日重复拒绝（截图 05）；
- 专家中心四工作台全部 ready，康复顾问显示"5 条新分析"（截图 06）。

### 真实 LLM 安全评测（与 FAKE 分开报告）

**本轮未执行真实 LLM 评测**（执行环境无 API key；CI 亦无）。已预留
`tests/coach_eval` 框架；高风险反例评测（症状描述→是否被引导为训练建议
而非就医提示）列入 P3 后续补测清单。**FAKE LLM 测试通过不宣称临床安全
性已验证。**

## 6. 实际发现并修复的问题

1. `create_restriction` 返回 dict 而调用方按 id 使用 → 统一取 id；
2. 观察分流合并历史文本导致缓解永不可识别 → 改为按**新报告内容**分流，
   历史 urgent 由限制复核机制承载；
3. "走路正常"误命中功能受限规则 → 否定后缀感知；"崴脚后肿了"漏命中 →
   词表补"肿了"+ 否定前缀感知；
4. types.ts 追加脚本吞掉 RecoveryBrief 闭合括号 → 修复。

## 7. 专业审核缺口（如实登记）

1. **分流规则**：红旗词表与阈值（持续 14 天等）为系统默认，未经医学审核；
2. **教育内容**：一般性说明（如"运动后轻度酸痛通常属于正常反应"）为常识
   表述，未逐条审核；结构化教学库（teaching_content 审核机制）接入待后续；
3. **AI 不能自动生成替代动作处方**：训练科学顾问不按疼痛部位推荐替代
   （用户可自行选择不受限动作，服务端只做拦截不做推荐）；
4. 无真实 LLM 高风险反例评测（见 §5）。

## 8. 已知限制与后续计划

1. 症状观察的图片上传（如肿胀照片）未做；2. CarePlan 提醒（review_at 到期
提醒）暂为被动展示；3. 人体图区域粒度为 9 区域×左右（更细分区域待后续）；
4. 恢复页酸痛与康复模块的联动引导（P2 已有"异常疼痛就医"提示，双跳转
入口待 P4 一并优化）；5. 动作视频×康复协作（场景 D）当前以数据隔离断言
保障，P4 视频工作台上线后补充联动 UI。
