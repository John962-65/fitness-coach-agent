# 专家平台路线图（Expert Platform Roadmap）

> Fitness Coach 2.0 的分阶段建设总设计。本文件是各阶段的总纲：每阶段开工前
> 在此登记范围与边界，交付后回填状态与交付文档链接。**状态如实标注，
> 未交付的能力绝不宣称可用。**

## 总目标

建立一个集专业训练、营养、身体管理、恢复、动作教学、康复辅助与多专家
协作为一体的个性化智能健身系统。用户**不打开 AI 聊天界面**也能使用全部
专业功能；聊天只是各业务工作台的辅助入口。

核心纪律（全阶段有效）：

1. 事件 ≠ 调 LLM：确定性计算优先，模型只用于解释/知识比较/复杂方案；
2. 专家结论必须可追溯到具体事实、单位、时间窗口与来源版本；
3. 数据不足如实说明，不用单次表现外推，不用缺失数据生成看似确定的结论；
4. 任何影响用户长期方案的 AI 写操作必须经统一修改协议（确认门）；
5. 纪律性约束写在代码与测试里，不依赖提示词自律。

## 阶段总览

| 阶段 | 核心能力 | 状态 | 交付文档 |
|---|---|---|---|
| P0 | 专家工作台 + ExpertInsight + 任务调度 | ✅ 已交付（2026-10-25） | [p0-expert-platform.md](p0-expert-platform.md) |
| P1 | 食物库 + 饮食记录 + 营养顾问 | ✅ 已交付（2026-10-25） | [p1-nutrition.md](p1-nutrition.md) |
| P2 | 身体与恢复管理 | ✅ 已交付（2026-10-25） | [p2-body-recovery.md](p2-body-recovery.md) |
| P3 | 康复辅助及风险管理 | ✅ 已交付（2026-10-25） | [p3-rehab.md](p3-rehab.md) |
| P4 | 动作技术工作台 | ✅ 已交付（2026-10-25） | [p4-movement-expert.md](p4-movement-expert.md) |
| P5 | 进阶训练功能（组法/有氧/器械/统计） | ✅ P5-B 全阶段已交付（2026-10-26）；P5-C 待开始 | [p5b3-statistics-integration.md](p5b3-statistics-integration.md) |
| P6 | 跨专家协作 | ⬜ 未开始 | — |
| P7 | 设备、数据互通与长期使用 | ⬜ 独立规划 | — |

## 目标信息架构

一级导航：**今日｜训练｜饮食｜专家｜我的**

P1 已完成完整五栏；P2 新增 `/mine/body`（身体数据）与 `/experts/recovery`
（恢复工作台）。旧路径 `/coach`、`/explore` 保留重定向：

| 旧路径 | 新路径 |
|---|---|
| `/coach` | `/experts/chat`（主教练对话） |
| `/explore`、`/explore/:id` | `/experts/knowledge`（运动科学知识） |

## 专家架构

一个主教练 + 五个专业顾问 + 一个共享知识研究服务（原 Knowledge Agent
收编为后台能力，不单开聊天窗口）：

| Agent | 领域 | 工作台状态（P4 后） |
|---|---|---|
| TrainingScienceAgent | 训练计划、进阶、负荷与周期 | ✅ ready（训练后回顾） |
| NutritionAgent | 食物、营养目标、饮食分析 | ✅ ready（日常养回顾） |
| RecoveryAgent | 睡眠、疲劳、恢复状态 | ✅ ready（恢复回顾+训练前简报） |
| RehabilitationAgent | 症状记录、安全分流、训练限制 | ✅ ready（症状回顾+安全分流） |
| MovementAgent | 动作教学、视频分析、技术反馈 | ✅ ready（视频技术档案+三维对照） |

注册表（`coach/experts/registry.py`）是唯一事实来源：每位顾问登记数据
来源、确定性工具、工作台状态与订阅的事件。未实装的顾问在 UI 上如实标注
"建设中"及其数据依赖，只保留咨询入口。

## P0 建立的平台机制（后续阶段直接复用）

1. **ExpertTask**（`expert_tasks` 表）：事件驱动的分析任务，落库队列、
   dedup 幂等、重试、心跳恢复、取消、频率限制、主动分析开关、执行日志；
2. **ExpertInsight**（`expert_insights` 表）：统一分析结果对象——发现
  （带 fact_ids/source_ids）、事实快照、知识参考、方案（收益/代价/适用
   条件）、局限、规则化置信度、失效与到期；
3. **懒失效**：读取洞察时对比 source_revision 与当前数据（checkin 修订数、
   生效计划版本），漂移即 invalidated——任何写入路径造成的数据漂移都不会
   以旧充新；
4. **证据校验**（`evidence_validator.py`）：落库前复核发现引用的事实真实
   存在于快照，编造引用剔除并计数；
5. **建议 → 提案 → 确认**（`recommendation_service.py`）：方案转
   ChangeProposal 走既有 AI 确认门，顾问无直接写权限；
6. **触发协议**（`task_dispatcher.on_event`）：业务事件 → 订阅顾问 →
   任务，整体容错（专家失败不阻塞普通记录）。

## 后续阶段接入方式

- **P3 康复**：`SymptomReported` + 安全分流为确定性前置步骤（分流不过
  不进入建议生成），训练限制管理复用医疗安全门。
- **P4 动作技术**：`VideoAnalysisCompleted` 接线，洞察类型
  `movement-review`；EvidencePanel 已支持任意 fact 集。
- **P6 跨专家**：多顾问洞察 + 主教练整合（分歧并列），复用 ExpertInsight
  的 options 结构表达各方方案。

## 里程碑验收基线（每阶段通用）

- 自动化测试全绿（pytest + Vitest + CI），不允许跳过测试换绿色；
- 用户隔离测试（A 不可见 B 的任何领域数据）；
- 真实浏览器端到端流程验证 + 手机视口截图；
- 交付文档含：修改清单、数据模型与兼容方案、API 说明、前端交互说明、
  测试结果、实际发现并修复的问题、未完成事项与技术限制。
