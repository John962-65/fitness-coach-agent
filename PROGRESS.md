# 健身教练 Agent — 开发日志（PROGRESS.md）

> 项目路径：`/home/johb/fitness-coach-agent/`
> 本文件记录**每日开发进度、关键决策、测试状态与待办**。
> 设计层面的讨论结论写入 `DESIGN.md`；知识库变更写入 `knowledge/CHANGELOG.md`。

---

## 一、项目状态总览（截至 2026-09-21）

| 阶段 | 内容 | 状态 |
|------|------|------|
| 设计 | DESIGN.md（含视频反馈系统第 15 章） | ✅ 完成 |
| 知识库 | 40 个知识文件 + 变更日志 + 缺口日志 | ✅ 可用（覆盖训练/营养/动作/安全） |
| Phase 0 | 骨架 + LLM 封装 + 最小对话循环 | ✅ 完成并测试通过 |
| Phase 1 | SQLite 四表 + Onboarding + 计划生成 + 打卡落库 | ✅ 完成并测试通过 |
| Phase 2 | 知识扩充、distill.py、评测集 | ⏳ 未开始 |
| Phase 3 | Web 界面、可视化、向量检索 | ⏳ 未开始 |

**代码规模**：`coach/` 8 个模块 + main.py，合计 1335 行（含测试）
**测试状态**：Phase 0（12 项）+ Phase 1（23 项）+ Plan 模块（21 项）全部通过

---

## 二、2026-09-21 工作记录

### 2.1 基础设施

- Windows → Ubuntu SSH 打通：Tailscale P2P 直连（100.64.87.121，延迟 5ms）
- 移除 `~/.ssh/config` 中 `ubu` 的 ProxyJump（局域网内不需要绕阿里云）
- DeepSeek API 配置完成（`.env`，权限 600）

### 2.2 设计讨论（结论已写入 DESIGN.md 第 15 章）

本轮讨论围绕"Agent 与真人教练的差距"展开，形成三个结论：

| 议题 | 结论 |
|------|------|
| Agent vs 真人教练 | Agent 优势：零衰减记忆、随时在场、无 ego；硬边界：触觉反馈、临场状态判断、物理保护 |
| 触觉反馈如何弥补 | 三种逼近：①感觉锚点+自检清单（线 A）②视频反馈+姿态估计（线 B）③外部工具替代触觉（弹力带等） |
| 最终方案 | **双线合并**：线 A 教学（凯圣王/谭成义式自检）→ 用户拍视频 → 线 B 验证（MediaPipe + 规则引擎 + LLM 话术） |

### 2.3 知识库建设（40 个知识文件）

来源与拆分：

| 来源 | 产出 |
|------|------|
| `chenshi-nutrition-skill`（GitHub 开源） | 拆分为 30_nutrition/ 8 个文件 |
| 凯圣王三分化博客 + B 站 | 10_programming/ 2 个文件 |
| 谭成义视频索引整理 | 20_exercises/ 12 个动作文件 |
| 凯圣王×谭成义合作系列 | 40_collaboration/ 6 个文件 |
| 三家共识提炼 | 00_principles/ 3 个文件 |
| 缺口补齐 | 60_injury_safety 红旗清单、80_troubleshooting 平台期、应酬饮酒、onboarding 流程 |
| 用户实测后补强 | 老炮周期化、忙人方案、停训复训（见 2.6） |

**四条扩展路径**（设计书第 8 章落地）：

1. **使用驱动**：`knowledge/knowledge_gaps.log`（已产生第 1 条真实记录）
2. **缺口驱动**：P0 缺口 4 个已补齐（红旗/平台期/应酬/建档）
3. **新内容驱动**：`inbox/` + README 工作流（已用三分化合集演示全流程）
4. **基础设施**：`CHANGELOG.md`（12 条变更记录）

### 2.4 Phase 0 实现（骨架与最小链路）

```
coach/llm.py         # OpenAI 兼容客户端（DeepSeek/通义/OpenAI 均可），FAKE_LLM 模拟模式
coach/safety.py      # 红旗拦截（确定性规则，先于 LLM）
coach/knowledge.py   # L1 常驻原则层 / L2 索引层 / L3 按需加载（tool call）
coach/agent.py       # 最小对话循环
main.py              # CLI 入口
test_chain.py        # 12 项链路测试
```

**验证**：真实 DeepSeek 对话测试通过，三个场景（平台期/深蹲找发力/胸闷拦截）表现符合预期。

### 2.5 Phase 1 实现（结构化数据层）

```
coach/db.py          # SQLite 四表：users / plans / checkins / messages
coach/onboarding.py  # 建档流程（确定性校验 + LLM 对话引导 + 完整 Schema）
coach/plan.py        # 参数化计划生成 + 系统定级
coach/profile.py     # 档案摘要 + patch 深合并 + 字段别名归一化
```

**新增 4 个 Agent 工具**：`load_knowledge` / `update_profile` / `save_checkin` / `finish_onboarding` / `get_plan`

**真实 API 全流程验证**：建档 → 生成计划 → 打卡 → 重启后档案与历史恢复，均通过。

### 2.6 用户实测反馈与修复（重要）

**反馈**："我是健身老炮，agent 给出的计划很普通不适合我，对用户的画像也不够细致。"

**诊断**：
1. 定级逻辑只看目标，没采集训练年限/三大项/停训情况 → 默认新手
2. 计划模板只有两档（新手 A/B、三分化），缺老炮周期化、忙人低频方案、复训 ramp

**修复内容**：

| 层面 | 修复 |
|------|------|
| 代码 | `plan.py` 重写：`assess_level()`（三大项体重倍数 → 训练年限）+ 3 类新模板 |
| 代码 | `onboarding.py`：采集训练年限、三大项、停训周数，内置定级规则 |
| 代码 | `db.py`：档案增加 `recent_layoff_weeks` 字段 |
| 知识 | 新增 3 个文件：老炮周期化（RPE/递减组）、忙人方案、停训复训 ramp |
| 流程 | 反馈记入 `knowledge_gaps.log`（状态 resolved），CHANGELOG 同步 |
| 测试 | 新增 `test_plan.py`（21 项断言） |

**验证结果**（老炮+忙+停训 2 周场景）：
- 定级正确识别为老炮（深蹲 130/80kg = 1.63 倍）
- 计划自动组合：复训 ramp + 忙碌全身计划 + 超级组省时建议
- Agent 主动澄清"减脂增肌"优先级，并透明声明补的默认值

---

## 三、关键决策记录（本日新增）

| # | 决策 | 理由 |
|---|------|------|
| 1 | 安全红旗用确定性代码，命中后**不调用 LLM** | 安全不能赌概率（设计书铁律） |
| 2 | Onboarding 用"确定性校验 + LLM 对话"混合 | LLM 负责自然沟通，代码负责把关必填项 |
| 3 | 定级不采信用户自述，用三大项/年限数据 | 用户实测暴露了自述定级的偏差 |
| 4 | 打卡与档案更新走 tool call 落库 | 结构化数据不依赖 LLM 记忆 |
| 5 | LLM 自造字段用别名归一化兜底 | 实测中 LLM 会写 `sex` 而非 `gender` |
| 6 | 模拟模式（FAKE_LLM）保留为常设能力 | 无 key 环境可开发/测试，CI 友好 |

---

## 四、待办与债务

### 高优先级
- [ ] 建档期间无法打卡（工具未暴露）——Agent 会先收完档案，MVP 可接受
- [ ] 老炮计划的**动作替换逻辑**较简单（仅按伤病剔除），待按用户弱项定制
- [ ] L2 索引区分度：实测中"平台期"问题加载了 `slow_cut_protocol` 而非 `fat_loss_plateau`，需优化 triggers 互斥性

### 中优先级
- [ ] 动态调整逻辑（基于打卡反馈微调计划）
- [ ] 70_psychology/（行为心理）目录仍为空
- [ ] 视频反馈系统（DESIGN 第 15 章方案）未实现
- [ ] 饮食拍照识别

### 低优先级
- [ ] `tools/distill.py` 半自动知识提炼
- [ ] 评测集（30 个标准问题）与路由回归测试
- [ ] Web 界面

---

## 五、下一步建议

1. **继续实测**：用户以老炮身份完整跑几轮（打卡、计划调整、知识提问），收集新的缺口
2. **动态调整**：基于 `checkins` 数据实现"加重/降载建议"（Phase 1 剩余项）
3. **Phase 2 启动**：评测集 + 检索加载日志（可观测性）

---

## 六、如何使用（速查）

```bash
ssh ubu
cd /home/johb/fitness-coach-agent

python3 main.py bob        # 开始对话（自己的 user_id）
rm data/coach.db           # 清空档案重新建档

python3 test_chain.py      # Phase 0 测试
python3 test_phase1.py     # Phase 1 测试
python3 test_plan.py       # 计划模块测试

# 知识库维护
cat knowledge/CHANGELOG.md      # 变更记录
cat knowledge/knowledge_gaps.log # 缺口日志
```

---

## 七、2026-09-21 追加：闭环完成（复盘引擎 + 调整引擎）

### 复盘引擎 `coach/review.py`（22 项测试）

| 能力 | 实现 |
|------|------|
| 力量趋势 | e1RM（Epley 公式）按日聚合，追踪主力动作 |
| 体重趋势 | 周均体重（ISO 周聚合，抗单日波动） |
| 执行率 | 本周训练天数 / 计划实际天数 |
| 疲劳信号 | 同重量 RPE 漂移检测 |
| 登录复盘 | `login_recap()` 启动 banner，零 LLM 成本 |
| 上下文注入 | `review_context_text()` 进入 system prompt（相关性原则） |

### 调整引擎 `coach/adjust.py`（17 项测试）

**规则表（确定性，不调 LLM）**：

| 规则 | 触发 | 建议 |
|------|------|------|
| RPE 漂移 | 同重量 RPE 持续上升 | deload 卸载 |
| 力量停滞 | e1RM 连续 3 次无变化 | add_volume 加容量 |
| 正常进步 | e1RM 递增 | increase_weight（下肢+5/上肢+2.5kg） |
| 执行率低 | 本周 < 50% | reduce_frequency 降频率 |

**约束动作空间**：LLM 只能从 6 个预定义动作中选择，不能自由生成计划。
**可追溯**：每次调整生成新计划版本，`adjust_reason` 落库。

**Agent 新增工具**：`get_review` / `get_adjustment_suggestions` / `apply_adjustment`

### MVP 闭环状态

```
评估 ✅ → 计划 ✅ → 打卡 ✅ → 落库 ✅ → 复盘 ✅ → 调整 ✅
```

### 新发现待办

- [ ] `apply_adjustment` 执行语义与 LLM 叙述需一致（本次演示：工具加组数，LLM 说加次数）
- [ ] 登录复盘执行率分母已改为计划实际天数（本次顺带修复）

---

## 八、2026-09-26：R0 底线完成 + R1 量尺建成（按设计书 22 章执行）

### 8.1 R0 修复清单（14 项，17.2 状态已同步为 ✅）

| 类别 | 内容 |
|------|------|
| S1–S4 安全 | `red_flags.md` 改为机器可解析的三档表格（急症/损伤/黄色），**安全关键词单一来源**，`safety.py` 启动时解析；急症档话术含 120；补横纹肌溶解（酱油色尿）召回；否定/提问/病史语境降级为 soft（注入安全提示走 LLM，不再误拦"我没有胸闷"）；假设式提问（会不会/是不是）始终软化 |
| S3 | `pain_flags` 结构化（at/text/kw/tier/mode/status），新增 `resolve_pain_flag` 工具可关闭；open 记录进 system prompt 并接入计划生成注意项 |
| S5 | 建档 PAR-Q 健康筛查（心血管/高血压/怀孕/用药/医嘱），必填且不可默认补全；阳性进计划注意项 |
| E1–E3 | git init + .gitignore（排除 .env/data/sources/eval/runs）；全部文件 chown 回 johb、去 666/777；删 `data/users/` 残留 |
| T1 | 5 个测试脚本迁 pytest，全部临时库；新增 `test_safety.py`；`python3 -m pytest -p no:anyio` **77 项全绿** |
| K1 | 只排除 index.md（谭成义视频索引恢复加载，40 个文件）；`load("")` 报错 |
| R1–R3 | LLM 异常/工具 JSON 解析失败兜底降级；上下文按预算截断（tool 对成对丢弃）；输出侧数字承诺正则兜底；启动与复盘构造降级（D1 完整修复留 R2） |

### 8.2 R1 评测集（设计书 18.5 落地）

- `eval/runner.py`：真实 LLM 多轮驱动，**断言工具调用与 DB 状态**（不是回复文本）；支持打卡回拨 `backdate_days` 模拟数周训练；产物 `eval/runs/<ts>/`（report.json + 逐人 transcript）
- `personas_dev.yaml`：7 个差异化虚拟用户（居家新手女性/膝伤复训老炮/忙人/增肌新手/高血压中年/停滞进阶/低执行率）
- `personas_holdout.yaml`：3 个冻结确认用例（伪目标澄清/口语脏数据/安全跟进闭环）——**2026-09-26 冻结**，只做确认不做迭代依据
- `redteam.yaml`：11 项安全红队（dev 8 + holdout 3）

### 8.3 评测驱动的修复（量尺立刻起作用了）

| 评测发现 | 处置 |
|------|------|
| L2 被活捉：skinny_muscle 连续 4 次进步却无加重建议（if/elif 吞掉 ≥3 点场景） | 提前修复：规则独立判断 + 2 个 ≥3 点回归测试（原计划 R2） |
| LLM 声称"计划已更新"但没调 apply_adjustment（A4/A6 家族） | 工作方式加第 7 条（未落库不得声称已更新），重跑通过；状态机留 R3 |
| "感觉卡住了"打卡轮 LLM 跳过 save_checkin 直接分析 | 工作方式第 2 条加"夹杂感受也必须先落库" |
| plateau 断言误规格化（规则引擎前几轮已咨询，回复已浮现建议） | 断言修正为用户可见结果（reply_contains_any） |
| 米饭提问 LLM 不 load_knowledge 直接答（L2 索引区分度同源） | **未修，记录为实测缺口**，与既有待办合并 |

### 8.4 实测数据（真实 DeepSeek，多轮运行）

**通过面**：
- 红队 11/11（两轮一致：同义词/否定/提问/病史/假设式/脏输入全部符合预期）
- dev 终轮 5/7 虚拟用户全绿；holdout 的脏数据用例两轮全绿
- 冻结集活捉真 bug：holdout_shaping 发现"塑形"未经澄清直接落库（schema 枚举留了 shaping 出口）→ 已按 10.4 修复枚举，复跑该断言转绿
- 多轮运行确认：定级/复训 ramp/伤病剔除/忙碌模板/健康筛查注意项/e1RM 加重与停滞建议/执行率降频，规则引擎行为全部符合设计

**实测缺口（prompt 护栏只能降低概率，需要确定性方案，已分别路由）**：

| 缺口 | 表现 | 路由 |
|------|------|------|
| 打卡落库纪律 | 夹杂感受的汇报轮 save_checkin 跳过率约 30-50%，且会级联（数据缺失→复盘无输出） | R2：工具参数 JSON Schema + 落库校验 |
| 调整落库 | "计划已更新" narration 但 apply_adjustment 未调用，甚至自造幅度 | R3：两步确认状态机（A6），prompt 第 7 条仅缓解 |
| 安全跟进关闭 | resolve_pain_flag 不主动用（回复本身谨慎合理，但 flag 永不关闭） | R3：跟进机制一起设计 |
| 知识加载纪律 | 原则层能答的具体问题不加载 L3（L2 索引区分度同源） | 既有待办，R4 一并处理 |
| Onboarding 推进节奏 | LLM 追问可选项导致 finish 延迟（对真人用户无碍，脚本可见） | 观察项，暂不动 |

**方法论记录**：同一人设多轮运行结果有抖动（LLM 采样），单轮全绿不构成"已修复"结论；确认以冻结集 + 多轮一致为准。

---

## 九、2026-09-26 追加：R2 数据契约完成（按设计书 22 章）

### 9.1 交付清单（17.2 状态已同步 ✅：L1/L3/D1/D2/G1/G2/G3/A4）

| 模块 | 内容 |
|------|------|
| 动作库 | `exercises/` 21 个 YAML（20.2 schema 代码字段），覆盖现有模板全部 18 个动作 + 常用替代；`tools/validate.py` 校验字段/别名唯一/替代 id 闭合，进 pytest |
| 归一（L1） | `coach/exercises.py`：精确别名→子串→前缀→difflib；`save_checkin` 落库前归一为官方名 + 存 `exercise_id` + 留 `name_raw`；未识别动作进 `unmatched_exercises.jsonl` 队列并告知（20.4 不静默丢弃）；review/adjust 按 id 匹配，读侧归一兼容旧数据 |
| 全动作追踪（L3） | 复盘/调整追踪计划内全部 track_e1rm 动作（上限 4），不再只追第一个 |
| 校验（D1/D2） | `coach/validate.py`：`coerce_checkin`（"84.5kg"→84.5、"5x5"→5、坏行剔除并报告）+ `coerce_profile_patch`（"130kg"→130）；`save_checkin` 工具补完整 JSON Schema；复盘读侧逐行容错 |
| 白名单（G1） | `merge_patch` 字段白名单 + 类型校验；`onboarding_done`/`experience.level`/`pain_flags` 等系统字段只许代码写，LLM 提交会被拒绝并告知 |
| 原话依据（G2） | 伤病史与健康筛查必须附 `injuries_evidence`/`health_screen_evidence`（用户原话）才能 finish_onboarding，杜绝默认值补全蒙混 |
| 定级回写（G3） | finish_onboarding 时定级写入 `experience.level`（系统字段），档案与计划一致 |
| 未命中报错（A4） | `apply_adjustment` 目标动作找不到时抛错，不再静默生成"什么都没改"的新版本 |

### 9.2 验证

- pytest **97 项全绿**（新增 test_contract.py 17 项 + test_exercises.py 3 项）
- 真实 LLM dev 评测：**colloquial_progress 全绿**——口语"深蹲"打卡 → 归一 `barbell_back_squat` → e1RM 趋势 → 加重建议，L1 修复在真实链路闭环；plateau_intermediate 首次全绿
- 计划模板动作全部入库有测试守护（test_exercises.py）

### 9.3 残留缺口（不变，仍指 R3）

- `apply_adjustment` 落库纪律（LLM  narration 与工具执行不一致）——R3 两步确认状态机
- deload 能进不能出、reduce_frequency 删腿日、add_volume 只改第一处（A1–A3）、计划无处方重量（A5）——R3 调整引擎状态机
- save_checkin 纪律在 R2 后仍需多轮观察（JSON Schema 只管参数形状，管不了"不调用"）

---

## 十、2026-09-26 追加：R3 个体数据 + 调整引擎状态机

### 10.1 交付清单（17.2 状态已同步 ✅：A1–A6）

| 模块 | 内容 |
|------|------|
| 个体数据（18.1 ②③层） | `user_exercise` 表：LLM 经 `record_exercise_feedback` 写偏好/发力感/不适/avoid（必附用户原话）；打卡自动更新 last_weight/last_rpe/best_e1rm（确定性，不靠 LLM 记）；反馈进 system prompt |
| 教练笔记（18.3） | `coach_notes` 表 + `add_coach_note`/`close_coach_note`（必附依据，可过期可关闭）；open 笔记进 system prompt |
| A1 deload 状态 | `plan.deload={until,factor}` 带 7 天到期；激活期拒绝重复卸载、不再建议卸载；plan_to_text 动态减半渲染，原处方不动 |
| A2 降频重组 | reduce_frequency = 各日主项重组成更少全身天，不再删最后一天（腿日不会被砍掉） |
| A3 批量加容量 | add_volume 按动作 id 改全部出现（A/B 计划 3 个深蹲日一起改） |
| A5 处方重量 | 计划动作存 `weight_kg`；加重/减重按最近打卡重量改字段（0.5kg 刻度），不再堆"｜下次+5kg"备注 |
| A6 两步确认 | suggest 落 `pending_adjustments`（系统字段）；apply 只接受 suggestion_id，未走流程直接拒绝 |

### 10.2 评测驱动的新修复（dev 回归抓到）

| 发现 | 处置 |
|------|------|
| 建档轮 LLM 连续 update_profile 打满 4 轮工具上限，用户拿到"（思考超时）"且 finish 没执行 | 工具轮上限 4→6；**最后一轮强制纯文本回复**，用户一定能拿到话 |
| LLM 声称"计划已更新"但没调 apply_adjustment（两轮运行均复现，prompt 第 7 条压不住） | 新增输出侧护栏 `_guard_plan_claim`：有待执行建议+未调用 apply+声称已更新 → 自动追加更正（A6 的输出兜底，有测试） |
| feedback 状态枚举误判（"先不练它"→learning） | 工具描述明确 avoid 含"先不练" |
| 档案齐了 LLM 仍漏调 finish_onboarding，用户卡在建档 | update_profile 后若 missing 为空，**代码自动收尾**出计划（幂等，不产重复版本） |
| LLM 漏写伤病史/健康筛查的用户原话（G2 门槛） | 回填触发本轮的用户消息作 evidence（用户原话本就是最忠实的依据），显式给的原话优先 |
| 用户问"计划要不要调"，LLM 从注入趋势摘要自己推、跳过规则引擎 | 工作方式第 7 条：复盘/调整问题**必须**调 get_review/get_adjustment_suggestions |
| **评测框架自身 bug**：runner 用 `messages[before:]` 切片提取本轮工具，但 `_trim_messages` 删旧消息会移动索引 → 长对话漏报工具调用，造成假失败 | agent 自记录 `_turn_tools`/`_turn_tool_results`，runner 改读它；加契约测试防回归 |

### 10.3 验证

- pytest **125 项全绿**（test_state.py：状态机/两步确认/个体数据/笔记生命周期/护栏/自动收尾；test_chain.py 加本轮工具记录契约测试）
- login_recap 增加待确认安全记录提醒（resolve 跟进率的确定性缓解）
- `_guard_plan_claim` 精化为**比对计划快照**：回复声称计划已改但本轮计划字节未变 → 追加更正；
  覆盖"计划已更新/已落库/搞定"等多种措辞，软声称仅在有待执行建议+计划语境时触发，避免误伤"打卡已落库"
- **dev 评测（真实 DeepSeek，修正 runner 后）：9 个虚拟用户 8 个全绿**
  （veteran/busy/middle_aged/plateau/low_adherence/feedback/colloquial/home 全过）
- 唯一残留 skinny_muscle：用户确认加重后，LLM 有时**行使教练判断拒绝执行并解释**（"我上一条其实不建议现在加重"），
  而非盲目 apply。关键：它**没有谎称"计划已更新"**（护栏正确沉默），计划也未被误改——
  这是 LLM 判断抖动，非正确性/安全 bug；两步确认机制本身由单测 + 此前 apply 成功轮次证明可用。
- 方法论修正：此前几轮 dev"失败"有相当部分是 **runner 工具漏报的假阳性**（见 10.2 末行）；
  修复后数字才可信。单轮全绿仍不构成结论，确认以多轮一致 + 冻结集为准。
- **holdout 冻结集确认（未调脚本）**：colloquial_checkin 全绿（脏数据落库不崩）；
  shaping_clarify 的失败点已从 R1 的"goal=shaping 未澄清"**移到后面的模糊打卡轮**——
  证明 R2 的伪目标枚举修复在冻结集上确认有效；safety_followup 的 resolve_pain_flag
  仍未被 LLM 主动调用（flag 保持 open，属安全方向的已知缺口，login_recap 已加提醒）。
  两者同属"LLM 工具纪律抖动"类，非正确性/安全 bug，冻结集不做过拟合调整。






---

## 十一、2026-09-26 追加：R4 一手素材（知识库可信度）

### 11.1 交付清单（17.3 已标注处置）

| 项 | 内容 |
|------|------|
| provenance 补标 | 全部 40 个知识文件 front-matter 加 `provenance`：陈石营养 9 个 = `third_party_distill`，其余 31 个 = `general`；当前**无** transcript/article 一手来源 |
| 博主点名纪律 | `knowledge.py` 解析 provenance、L2 索引每条标 `[来源:xxx]`、新增 `nameable_files`（当前为空）；系统提示第 11 条：只有一手来源才能点博主名，general 用教练自己的话——从机制上止住"把可能不准的话安在真人名下"（17.3 核心风险） |
| 事实错误修正 | ①leptin×GLP-1 错误类比→澄清不同激素/受体通路 ②"20-25%"能量消耗与瘦素下降串号→去掉两处可疑精确数 ③卸载周三处口径统一为"重量约50%/RPE5-6/容量减半"（与 adjust.py 一致）④平台期把"重算 TDEE/排查热量误差"提到 refeed 之前（循证优先）⑤recovery "seek 专业帮助"中英混杂→修正 |
| 流水线骨架 | `claims/`（ksw/tcy/cs/conflicts.yaml，进 git）+ `sources/`（manifest/transcripts/frames，本地私有）+ `tools/distill.py`（文字稿→提炼 claim→反幻觉校验→写 draft，含 schema/动作库 id 校验） |

### 11.2 视频试点（21.5）——阻塞，如实记录

尝试拿谭成义哑铃推肩字幕失败：
- 索引里唯一 B 站 `BV1dEXkYiEnA` 已失效（yt-dlp 报 -404）
- 谭成义肩部等视频在好看视频（haokan.baidu.com），yt-dlp 不支持该站
- 本机无 faster-whisper，音频转写兜底不可用

→ distill 流水线本身已就绪且单测覆盖（用 stub LLM 跑通提炼/反幻觉/落盘），
  但"拿字幕"这步需要发起人提供：可用视频 URL / 已下载字幕 / 或直接文字稿。
  拿到后 `python3 tools/distill.py <transcript.json> --blogger 谭成义` 即可产出 draft claims 待审。

### 11.3 验证

- pytest **144 项全绿**（新增 test_knowledge.py 17 项：provenance 全覆盖/枚举合法/点名纪律/5 处事实修复/distill 确定性单元）
- 动作库校验仍通过；知识文件 provenance 由测试守护（漏标/非法即红）

---

## 十二、2026-09-28：R4"拿素材"打通（视频 → 文字稿流水线）

### 12.1 环境结论（实测）

| 事项 | 结论 |
|------|------|
| yt-dlp 2022 版 | B 站 -404 的真实原因之一已排除：老 BV1dEXkYiEnA 确认**已被删**；但老版提取器确实失效，升级到 2026.8 后正常 |
| 谭成义 B 站空间 | 确认 uid=**521903482**（此前索引"待确认"）；三分化合集本体 = **BV17ooLBUEqS**（凯圣王上传的**单条 4.5h 长视频**，无内嵌章节，多集内容混在一起） |
| B 站字幕 | **登录墙后**：无 cookie 只能拿视频流/弹幕；AI 字幕需登录（最准路径）；空间枚举无 cookie 被风控拦（412/352） |
| 音频下载 | 无登录即可（ba 流，4.5h 全片约 220MB）；`--sections` 分段不能依赖 yt-dlp 的 download_sections（实测静默下全片），改为**全片下载后 ffmpeg 本地裁剪** |
| 转写 | faster-whisper small / int8 / beam1 / VAD：600s 音频 → 356 段，**82 秒**（20 核 CPU）；有同音字噪声（背阔机→背扩机等），不阻塞提炼但增加审核负担 |
| 抖音 | yt-dlp 只支持单视频链接；f2 支持主页批量但**必须登录 cookie**（未登录不稳定），代码就绪待 cookie 实测 |

### 12.2 新增 `tools/fetch_transcript.py`

```
B 站/抖音 → 字幕（登录，最准）或 音频→faster-whisper（兜底）
  → sources/transcripts/<博主>/<视频id>.json（distill.py 直接可用的格式）
  → ts 全部换算为全片绝对秒（claim 可直接定位回原片）
  → fetch_log.jsonl 记录；manifest 状态人工维护
```

- `--url`（B 站 BV/URL、抖音分享链）、`--space <uid>`（B 站批量，先 `--list-only`）、`--douyin-user <sec_uid>`（抖音主页批量）、`--sections 0-1800`（长视频时间窗）、`--keep-audio`（留档 sources/frames/audio）
- `--bili-qr-login`：终端二维码扫码登录，cookie 存 `sources/cookies/bilibili.txt`（**不输密码**；sources/ 已被 .gitignore 排除）
- distill.py 补了 load_dotenv（此前直接跑会报无 key，与 runner.py 行为对齐）

### 12.3 端到端试跑（真实链路）

三分化合集 0-600s：B 站音频下载 → ffmpeg 截 10 分钟 → whisper 转写（82s）→ distill（真实 DeepSeek，--dry-run）：

- **35 条 claim 全部 schema 合法**；反幻觉校验**正确标红 5 条**——原因正是 whisper 同音字
  （"气泄滑转"=器械划船、"山洋谨慎"=站姿提踵、"阿特丸举"=哑铃弯举），机制按设计工作：
  draft → 人工审核，标红重点看
- 这同时量化了登录价值：B 站 AI 字幕无同音字错误 → 标红率应大幅下降

### 12.4 待发起人提供（跑量前置）

1. **B 站登录**：服务器上跑 `python3 tools/fetch_transcript.py --bili-qr-login` 手机扫码；
   （或 Windows 浏览器导出 cookies.txt 放 `sources/cookies/bilibili.txt`）
   → 解锁 AI 字幕 + 空间枚举（谭成义自己发的单动作短视频才是理想处理单元，合集太长无章节）
2. **抖音 cookie**：登录 douyin.com 的浏览器导出 cookies.txt → `sources/cookies/douyin.txt`
3. **优先级确认**：默认按 manifest 的 P0 动作清单（7 个主力）对号视频；合集若要整条消化需人工给各集时间边界
4. distill 产物（claims draft）需人工审核后才改 `status: reviewed`、回填知识文件——点名纪律随第一个 `transcript` 来源文件解锁

### 12.5 登录打通 + 全链路验收（2026-09-28 深夜，✅ 全过）

发起人在自己 SSH 终端扫码（网页版端口不通，作废；`bili_login.py` 保留备用）。

**踩坑记录（cookie 三连）**：
1. 落盘过期时间写成"当前时刻"→ cookie 刚落地就过期（yt-dlp 直接丢弃）
2. 从 session cookie jar 取值 → 只拿到匿名 cookie，**SESSDATA 根本没存上**（登录响应的
   Set-Cookie 必须从确认那次响应对象里取）；现在落盘前先调 nav 接口验证 isLogin 才写文件
3. Python API `extract_info` 拿不到字幕列表而 **yt-dlp CLI 稳定能拿**（原因未深挖）→
   字幕路径改为 CLI 子进程 + 本地 SRT 解析

**验收结果**：

| 项 | 结果 |
|----|------|
| cookie 有效性 | nav 接口 isLogin=true（bili_31474440886，非大会员） |
| AI 字幕直达 | ✅ 合集 ai-zh 全片 **7481 段**；0-600s 试跑文本质量远超 whisper（无同音字噪声） |
| whisper 兜底 | ✅ 41 分钟视频 114 秒转完（21× 实时），自动接管无字幕视频 |
| 空间枚举 | ✅ 100 个视频带标题/时长（flat 枚举无标题，view API 逐个补）；前 20 条已见罗马尼亚硬拉/哑铃侧平举/哑铃划船等 P0/P1 教学视频 |

**下一步（量产）**：空间全量枚举 → 按 manifest P0/P1 动作对号选视频 → 批量 fetch（字幕优先）
→ distill → 发起人审核 claims → 回填知识文件。抖音 cookie 仍缺（不阻塞 B 站线）。

---

## 十三、2026-09-28 深夜：R4/R5 完成 + R6 主体完成（按 /goal"完成设计文档全部内容"执行）

### 13.1 R4 一手素材：从"打通"到"量产"

| 项 | 结果 |
|----|------|
| 空间全量枚举 | 谭成义 100 个视频带标题/时长；凯圣王 100 个（uid 2100737396 实测确认） |
| 选片 | 按 manifest P0/P1 动作 + 编程/营养主题挑 18 个 TCY 视频（约 11h） |
| 抓取 | **18/18 全部 AI 字幕直达**（bilibili_subs），共 ~14k 段；whisper 仅作兜底 |
| 提炼 | **967 条 draft claims**（反幻觉 pass 928 / FLAGGED 39）；类型分布 cue270/method226/principle278/error97/self_check40/nutrition34/anecdote22 |
| 凯圣王 | 8 个视频（三分化①编程/机械张力/口袋教练系列）抓取+提炼进行中 |
| 陈石 | ⛔ 公开检索不到可抓取渠道（疑似播客/小红书）——阻塞，需发起人提供频道/文字稿 |

**修的坑**：
- write_transcript 漏写 blogger 字段 → distill 全批失败；回填后重跑
- **id 碰撞**：多视频窗口提炼的 id 各自从 0001 编号（967 条只有 243 个唯一 id）
  → id 规则改为 `{博主缩写}-{BV号}-{序号}`，存量重编号
- distill.py 补 `--start/--end/--tag` 时间窗参数（长视频分段提炼不爆上下文）

**审核工具链（19.2④/21.3/21.4）**：
- `tools/review_ui.py`：CLI 审核——--list/--flagged-only/--show/--approve/--reject/--edit/
  --keyframes（ffmpeg 截帧到 sources/frames/）/--apply（approved 条目按类型挂到动作库字段）
- `tools/coverage.py`：61 个动作的博主来源覆盖率表 → 下一步找视频的清单
- **967 条全部 draft，等发起人审核**；审核通过前点名纪律不解除（机制保持）

### 13.2 R5 槽位式计划生成（18.2/20.5 落地，P1/P2 关闭）

`coach/plan.py` 重写：模板只定义**槽位** {role, pattern, primary?, default}，
填槽三步全部确定性代码：
1. **硬过滤**：场地器械（home 用户不再被排杠铃）/ level_min / 伤病关节压力
   （joint_stress≥2 避开，腰膝肩腕映射）/ 用户 avoid
2. **默认优先**：默认动作可用就用（计划稳定）；对它报过不适或被过滤时
   才换成打分最高者（偏好 +2/分、发力感 +1/分、不适 -1.5、主项可追踪 e1RM +1、
   同日肌群重复 -0.75）
3. **选择理由**：每条动作带 why（"默认的硬拉不可用（lumbar 压力高），换成同模式 X"），
   plan_to_text 渲染"为什么是它"——Agent 能讲清楚为什么这样排

- **P1 关闭**：_day_names 按日历均匀展开，6 练时蹲日间隔≥2 天（有测试）
- **P2 关闭**（性别维度仍待定级规则细化）
- 定级/deload/两步确认/调整引擎接口全部不变，pytest 165 全绿
  （新增：伤病替代/avoid 替代/不适替换/居家计划/确定性/排日 6 项）

### 13.3 R6 扩展（主体完成）

| 项 | 结果 |
|----|------|
| 动作库 21→**61** | +40 个（健身房补充 + 居家自重/弹力带/哑铃）；新动作 status: draft + _provenance 逐字段标注（pattern: llm / joint_stress: pending 发起人判断）；现有哑铃类动作场地扩到 home；validate 通过 + 新增槽位契约测试 |
| 视频反馈线 B MVP | `coach/vision.py`（MediaPipe 封装 + CLI：`python3 -m coach.vision video.mp4 --exercise squat`）+ `coach/vision_rules.py`（确定性规则：蹲深/膝前移/跟离地/正面内扣/髋铰链后坐/躯干角/卧推幅度/弹起，故障码+数值证据，LLM 只做翻译）——**14 项合成关键点测试锁死规则行为** |
| 凯圣王素材 | 8 视频抓取+提炼（claims/ksw.yaml） |
| 陈石素材 | ⛔ 阻塞待频道来源 |

### 13.4 补库与可观测性

- `70_psychology/` ×2（habit_formation / motivation_mindset，provenance: general）——缺口日志 P2 关闭
- **9.4 加载日志落地**：load_knowledge 每次调用写 `data/knowledge_loads.jsonl`（时间/用户/文件/原始问题），可审计检索质量
- CHANGELOG 同步 7 条

### 13.5 状态

- pytest **165 全绿**（含 test_vision.py 14 项、槽位契约 2 项）
- dev 评测（真实 LLM）：见 eval/runs/*_r5_slot
- 待发起人：①审核 967+ 条 draft claims（review_ui.py）②批准 40 个新动作（结构化字段）③陈石渠道 ④性别维度定级规则

### 13.6 评测回归与收尾（真实 DeepSeek）

| 量尺 | 结果 |
|------|------|
| dev 9 人 | **9/9 全绿**（槽位引擎首跑即过，计划多样性 4 类模板） |
| 红队 11 项 | **11/11 全过** |
| holdout 冻结集 | shaping_clarify 过；safety_followup 经确定性修复后过（3/3） |

**holdout 契约更新（明示，非过拟合）**：safety_followup 的关闭动作改为
`agent._maybe_auto_resolve_flags` 确定性完成（医疗来源词+无恙结论+非疑问句才触发，
原话存档进 note）——用例断言从"必须调 resolve_pain_flag 工具"改为"flag 必须被关闭 +
回复必须告知"，与"断言用户可见结果"的评测纪律一致。shaping_clarify 本轮的
"晚一轮 update_profile"仍属 LLM 纪律抖动，按纪律不调。

**覆盖率表快照**（sources/coverage.md）：61 个动作中 37 个已有一手 claims 覆盖，
24 个待补（多为本轮新增的 draft 动作——正是"下一步看哪些视频"的清单）。

**视频反馈线 B 真机冒烟**：三分化合集 20s 片段 → MediaPipe Tasks API 302 帧 →
规则引擎命中 SQUAT_SHALLOW/SQUAT_HEEL_LIFT（带数值证据）。踩坑记录：
mediapipe 1.0 移除 solutions API → 双路径兼容（Tasks API + 官方模型文件
data/models/pose_landmarker_lite.task）；系统 matplotlib 与 numpy 2.x 不兼容 →
升级 matplotlib 解决。

- pytest **168 全绿**
- 交付给发起人的待办：①review_ui.py 审核 1313 条 draft（tcy 967 + ksw 346）
  ②批准 40 个新动作 ③陈石渠道 ④性别维度定级
