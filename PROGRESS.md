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


