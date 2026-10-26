# P6 跨专家协作系统——交付与验收

> 基线：`c8b06af`（P5-C3）｜ 日期：2026-10-27
> 状态：**P6-A/B/C 三次提交全部交付**；P7 未启动

## 1. 定位与总原则

独立专家 ≠ 专家协作。P6 实现：

**共享经过验证的事实 → 各专家独立分析 → 识别一致与分歧 → 主教练整合
（保留分歧）→ 用户选择 → 后续跟踪。**

- 不把多个 Agent 的聊天回复拼接成"联合报告"——全链路确定性，无 LLM；
- 不采用多数投票；分歧被并列保留，由用户决定；
- P3 安全限制优先级最高，不可被任何"多数意见"覆盖；
- 复用 ExpertTask / ExpertInsight 基础设施（任务队列、生命周期、证据
  校验、options、懒失效），不建第二套系统。

## 2. P6-A：跨领域事实与协作基础设施（`af6d690`）

`coach/collaboration/`：

| 模块 | 职责 |
|---|---|
| `models.py` | CrossDomainEvidence / SpecialistOpinion / CollaborationReport 结构契约（含结构化 directions 供确定性裁决） |
| `evidence_bundle.py` | 跨领域事实包：按场景圈定授权领域（training/nutrition/body/recovery/rehabilitation/movement），逐域复用既有口径（fact_service / meal_service / body_metrics / recovery_metrics / restriction+symptom+triage / motion 档案）；未请求领域不进入包；每条事实带 source_ids/source_revisions/calculation/data_quality/limitations；版本指纹覆盖 checkins/plan/meals/recovery（按记录修订计数）/restrictions/symptoms/equipment/motion/营养目标 |
| `specialist_runner.py` | 五顾问各自领域观点（观察/解释/建议/依据/局限 + 结构化方向），纯函数、不调 LLM；空数据如实标注"未知"（不解释为零） |
| `conflict_resolver.py` | 确定性张力规则表（如 maintain_or_progress × observe_and_reduce_risk → training-vs-recovery 分歧）；每条分歧含双方立场+共同事实+缺少的信息+维持现状项；安全门最高优先级 |
| `coordinator.py` | 三个场景注册表 + 联合分析编排 → `collaboration-review` 类型 ExpertInsight（完整报告随 facts_snapshot 持久化）；趋势判定复用 progress_analysis |
| `decision_service.py` | ignore / observe（只读）与 propose（仅携带服务端构造提案提示的方案，走 ChangeProposal 确认协议） |

## 3. P6-B：三个核心场景与安全集成（`5efc7a4`）

| 场景 | 参与方 | 关键行为 |
|---|---|---|
| training-recovery | 训练科学 × 恢复 × 康复 | 表现趋势 vs 自报信号并列；分歧保留并给出缺失信息清单；单次疲劳不构成过度训练判定（免责文案唯一化） |
| training-nutrition | 训练科学 × 营养 × 康复 | 营养目标对照是观察性的；记录不完整时明确"不能代表真实摄入"；不断言"蛋白质不足"；矛盾数据并列不隐藏 |
| movement-rehab | 动作技术 × 康复 | 症状事件+确定性分流进入事实包；急症分流成为安全门（优先于一切）；视频观察不与伤病归因混同 |

评测（`test_p6b.py` 10 项）覆盖任务书 2.7 全部条目：矛盾数据、记录不完整、
恢复缺失、下滑无因、意见冲突、P3 限制、旧报告失效（含跨领域修订：症状
状态变更、恢复纠错）、关闭主动分析不影响显式请求、拒绝所有方案、无可执行
方案、确定性降级（AST 检查无 LLM 依赖）。修复：症状状态变更指纹秒级碰撞。

## 4. P6-C：联合工作台与用户决策（本次提交）

- 路由 `/experts/collaboration`（专家中心卡片自动出现——注册表
  workbench_path）；首页在"恢复信号偏高 + 有训练计划"时显示"发现一项
  值得进行跨领域复盘的情况"提示卡（仅由真实数据规则触发）。
- `pages/experts/Collaboration.tsx` + `components/collaboration/` 五组件：
  场景选择 → 请求联合分析（不调聊天）→ 展示联合主题/参与顾问、不同
  专业观点、共识分歧未知与安全门、可以选择的方案、事实来源及局限。
- 用户决定：继续观察 / 忽略（只读）；申请长期调整（仅当选中方案携带
  服务端构造的提案操作——当前三场景候选均为 advisory，故按钮会得到
  明确的 422 提示而非静默无操作；训练执行类调整走 P5-C 训练页通道）。
- 已有有效报告直接展示；失效报告显示原因并可重新分析。

## 5. 测试与验收

- 后端：`test_p6a.py` 6 项 + `test_p6b.py` 10 项；全量后端 846+ 项全绿
  （见提交时 CI/本地记录）。
- 前端：tsc + vite 构建通过；vitest 74 项。
- 浏览器 E2E（截图 `docs/p6-shots/`）：
  1. 首页提示卡（恢复 caution + 计划在册）→ 点击直达工作台；
  2. 请求联合分析 → 报告渲染（3 位顾问、28 条共享事实、分歧并列、
     安全门横幅仅在真实限制/急症时出现）；
  3. 选择"保持当前计划"→ 继续观察 → "未产生任何修改"；计划版本不变、
     提案数为 0；
  4. 全程未进入通用聊天页（验收标准达成）。

## 6. 已知限制 / 未完成

- 当前三个场景的候选方案均为只读 advisory（训练调整类方案的正确入口是
  训练页的确定性候选与确认协议）；携带可执行提案操作的联合方案留待
  具体场景需要时按 P5-C3 adopt 模式扩展。
- 协作洞察的 facts_snapshot 含完整报告，体积大于普通洞察（窗口 14 天
  上限内可控）。
- 主教练"整合"目前是结构化并列（共识/分歧/未知），不生成自然语言总结
  ——按平台纪律留待 T4 真实模型评测阶段评估是否引入受控 LLM 叙事层。
