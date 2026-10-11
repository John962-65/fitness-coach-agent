# 待发起人决策清单（2026-10-11，单次汇总）

> 本文件汇总当前全部等待发起人答复的事项，共 6 项。逐项标注：现状 / 选项 / 答复后解锁什么。
> 答复方式：直接在对话里逐项回复编号即可（如"1 通过、2 选 A…"）。

---

## 1. Q29 — skull_crusher 卡 v2 签核

- **现状**：v2 已 prepared（BV1Cz421i79n 三条归属确认条目进入正文：第 7 点"窄推 vs 仰卧臂屈伸"编程定位**并列保留**、第 8 点上斜凳哑铃替代；绑定 7→10）。v1 审批不延续，签核前运行时对该动作回退通用教学。
- **选项**：通过 / 退回修改（说明改哪里）/ 暂不使用（卡保持 v1 不动？——注意 v1 已被 v2 覆盖，选暂不使用则维持回退状态）。
- **解锁**：三头教学卡恢复服务并带新增编程定位。

## 2. plan.py:326 修法 — 无伤病用户可能被处方 draft 动作

- **现状**：`approved_only = bool(joints)` 只在有伤病限制时锁定已审动作；无伤病用户仍可能被选中 49 个 draft 动作之一（其关节压力/替代关系未经发起人审核）。
- **选项**：
  - **A（保守）**：全局锁 approved——处方域缩到 21 个动作，计划多样性下降，需回归评测；
  - **B（折中，建议）**：保持可选域，但选中 draft 动作时在计划备注里明示"该动作结构化属性未经审核"；
  - **C（维持现状）**：等动作属性审核铺开后自然收紧。
- **解锁**：消除 PROGRESS 19.7.2 挂账的最后半个问题。

## 3. git 提交授权

- **现状**：工作区 19 个文件未提交（C1 记忆契约、C2 目标协商、C3 讨论闭环、C4 训练前简报与个人尝试、九步场景验收测试、20 条 draft claims、skull_crusher 卡 v2 脚本、DESIGN/ZCODE/PROGRESS 文档修订、C0 矩阵）。全量回归 340 passed；凭据未触碰。
- **选项**：授权提交（我可以拆成多个有逻辑边界的 commit）/ 暂不提交。
- **解锁**：版本锚定——当前 eval/runs 报告只能绑 dirty 工作区，提交后才有可复现指纹。

## 4. 组 7 说话人指认（BV1aqsXeRE2B）

- **现状**：对谈 5 条（t≈174-232「功能性肌肥大 vs 孤立肌肥大」，含负重引体练二头表述）。Q9 已判定说话人非凯圣王本人；整批"确认归属"回答不了"实际是谁"。
- **选项**：看原片指认说话人（解锁 weighted_pull_up 素材）/ 放弃该素材（维持长期缺口）。
- **解锁**：负重引体动作卡的素材来源。

## 5. 「阿亮」频道是否纳入采集

- **现状**：BV1gYXAYYEzj（翼状肩胛调整）发言者自称"阿亮"，非三位博主（扫描频道归因误标）。按 §3 纪律未采集、未归名。
- **选项**：纳入（需身份核验 + 扩展采集范围授权）/ 不纳入（维持三博主范围）。
- **解锁**：肩胛体态类知识的新来源（或明确不做）。

## 6. personas_pilot 场景 2 重建

- **现状**：C1 确认流变更后，`personas_pilot.yaml` 场景 2（30 分钟）仍断言旧行为（改时长立即生效）。按 24.2 规则未擅自改确认集。
- **选项**：授权按新契约重建该场景（暂存→澄清→确认→落库→重排）→ 之后才能跑真实 LLM 验证 / 暂缓。
- **解锁**：真实 LLM 多轮验收（C5 的真实部分）。

---

**已完成等查验**（无需决策，供参考）：C0 能力矩阵与九步基线；C1 记忆契约＋冲突确认流；C2 目标协商（预览/版本绑定/评价切换）；C3 讨论记录闭环；C4 训练前简报＋个人尝试；C5 离线九步场景 340 项全绿（`eval/runs/nine_step_offline_20261011/report.json`）。

---

## 附：答复后的执行预案（已备好，答复即可一次性落地）

### 第 3 项 git 提交 — 拟拆 5 个逻辑 commit（按依赖顺序）

| # | commit 主题 | 文件 |
|---|---|---|
| 1 | docs: DESIGN v0.6 冲突处理对齐 26.9 + 任务书直提线与状态更新 + C0 能力矩阵 + 待决策清单 | DESIGN.md、ZCODE_KNOWLEDGE_MAINTENANCE.md、PROGRESS.md、C0_CAPABILITY_MATRIX_2026-10-11.md、PENDING_DECISIONS_2026-10-11.md |
| 2 | coach: C1–C4 运行时（记忆契约/目标协商/讨论闭环/训练前简报与个人尝试，含新表与迁移） | coach/db.py、coach/profile.py、coach/agent.py、coach/plan.py、coach/review.py、coach/goals.py |
| 3 | tests: C1–C4 与九步场景（339→341 全绿基线） | test_memory_contract.py、test_goal_negotiation.py、test_knowledge_discussion.py、test_c4_workflow.py、test_pilot.py、test_nine_step_scenario.py |
| 4 | claims: 直提线三轮 20 条 draft（凯圣王 11 / 谭成义 9） | claims/ksw.yaml、claims/tcy.yaml |
| 5 | eval+tools: 九步离线验收报告 + skull_crusher 卡 v2 准备脚本 + pilot 场景 2 重建草稿 | eval/runs/nine_step_offline_20261011/、tools/_skull_card_v2_20261011.py、eval/drafts/personas_pilot_scenario2_pending_item6.yaml |

注：卡本体、runs、字幕在 sources/（不进 git）；commit 前照例做凭据扫描与全量回归。

### 第 6 项 pilot 场景 2 — 重建草稿已备好

`eval/drafts/personas_pilot_scenario2_pending_item6.yaml`（未并入确认集）。授权后：整体替换 `personas_pilot.yaml` 的 pilot_time_preference 场景 → 删除草稿 → 记录确认集版本变更 → 方可申请预算跑真实 LLM 多轮验收。

### 各项答复后的即时动作

1 通过 → 运行 `approve_card` 签核流程（记录对话原话 + 指纹复验）恢复三头卡服务；2 选 B → 小改 plan.py 备注逻辑＋测试；4/5 → 采集线对应处置。

---

## 决议记录（2026-10-11，授权原话：「继续任务,我给你权限审批通过」）

| 项 | 决议 | 落地 |
|---|---|---|
| 1 Q29 | ✅ 通过 | skull_crusher approved_v2（指纹 2a76d3df…），运行时恢复服务；备注如实记录"整批授权、未逐字复核" |
| 2 | ✅ 按建议项 B 执行 | plan.py 选中 draft 动作时计划备注明示"结构化属性未经审核"（授权未指定选项，取清单建议项，可逆） |
| 3 | ✅ 授权提交 | 5 个逻辑 commit（见上方预案），提交前全量回归＋凭据扫描 |
| 4 组7 | ⏳ 不在授权范围 | 指认说话人是事实判断（需看片），"审批通过"无法替代；维持搁置，未来采集命中本人 solo 视频再启用 |
| 5 阿亮 | ⏳ 不在授权范围 | 新增创作者需身份核验结论先行（§3）；维持不采集、不归名 |
| 6 | ✅ 授权重建 | pilot_time_preference 按 C1 契约重建为 4 轮并入 personas_pilot.yaml，草稿删除，版本变更记录于 PROGRESS 三十 |
| Q30 | ✅ 通过 | plank approved_v1（指纹 0b79d44b…），运行时服务；6 条 speaker 批量确认（未逐条看片，批量性质如实记录） |

**预算**：真实 LLM 多轮验收的调用额度不在本授权内（§5 需单独授予）——确认集已就绪，等额度即跑。
