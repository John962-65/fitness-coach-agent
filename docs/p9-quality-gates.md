# P9 专业可信度与质量保障——交付状态

> 基线：`8438cfd`｜ 日期：2026-10-27
> 说明：P9-A/B/E 已实施并固化为测试与审计文档；**P9-C（真实模型评测）与
> P9-D（真实视频评测）需要外部资源（真实 LLM API / 真实拍摄视频集），
> 本轮交付评测框架与固定用例集，真实运行标注为待外部条件**。T1–T3 已
> 全绿；T4–T6 不能被 T1–T3 替代（分层声明见 §5）。

## P9-A 专业内容审核审计

每个用户可见的专业内容面都有来源与审核状态字段（已核）：

| 内容面 | 来源字段 | 审核状态 | 门 |
|---|---|---|---|
| 共享知识检索 | claims/*.yaml provenance | approved / **draft** | draft 命中只计数不给内容（`knowledge_search` 结构保证） |
| 分流规则 | `triage_rules.SOURCE`（通用常识性警示汇总，非临床指南） | `REVIEW_STATUS=system_default（待专业审核）` | 前端/洞察如实展示；不宣称临床有效 |
| 动作库 | exercises/*.yaml（内置校验 80 个） | 校验通过 | `tools/validate`（CI） |
| 进阶/协作规则 | rules_version（p5c/p6） | 版本化 | 版本漂移使旧候选/报告失效 |
| 营养数据 | foods.source_name/source_url/license/verified_status | reference / user_created | NULL=未知，绝不用 0 冒充 |
| 教学内容 | teaching 文档 + 状态字段 | 已审核/待审核区分 | 未审核不进入正式推荐 |

**审计结论：没有专业人员审核的内容未被标记为专业认可**；分流规则页与
洞察文案均带"不构成医疗诊断"边界声明。遗留：为全部教学卡补 reviewer/
reviewed_at 人工审核记录——需要真实专业人员（外部资源，已列入 P10 门槛）。

## P9-B 康复安全规则评测（已交付）

`test_p9b.py` 8 项 + `test_p3.py` 全量：急症识别、否定语义、多症状取最严、
持续天数→专业评估、信息不足保守处理、triage 限制同步与专业解除留痕、
旧计划恢复重过安全门、多专家冲突安全门优先。

**审计发现并修复**：急症召回缺口——"晕倒"（词表只有"昏倒"）、
"胸部剧烈疼痛"（不含"胸痛"连续词）原先漏判为 uncertain；已扩词表
（晕倒/意识丧失/出冷汗/胸部疼痛/胸口痛/剧烈疼痛）并用评测锁定。

## P9-C 真实 LLM 专家评测（框架已交付；真实运行待外部资源）

- 固定评测集：`eval/p9c-expert-eval-cases.json`（六位专家 × 边界用例：
  编造记录/错误指标/过期数据/未批准处方/解除限制/忽略数据不足/分歧
  伪装一致/替用户决定）；
- 运行器：`eval/run_p9c.py`——检测到真实 LLM 凭据（`FC_LLM_API_KEY`）
  才执行并输出逐案例记录（input/authorized_facts/expected_boundaries/
  model_response/evidence_validation/factual_errors/…/reviewer_decision）；
  无凭据时明确 SKIPPED，不伪造结果；
- 与 M6.5 的 49 案例确定性评测（eval/runs）互补：T1 自动化 ≠ T4 真实模型。

## P9-D 真实视频评测（待外部资源）

需要不同身材/机位/光线/速度/遮挡/格式的真实拍摄集；现有 P4 二维分析
保持保守观察定位（不生成统一正确性评分）。采集清单已列入 P10 门槛。

## P9-E 安全、隐私与可靠性验收（映射到既有自动化）

| 检查项 | 证据 |
|---|---|
| 用户越权 | test_p7b.py 越权矩阵（5 项） |
| 敏感数据导出保护 | test_p7a.py confirm 强制 + 完整性清单 |
| 媒体签名 | test_api 媒体签名用例（P1-5） |
| 导入安全 | test_p7a 白名单/完整性/回滚；test_p7c 白名单 |
| API 输入校验 | 各域 422 契约测试（全量 870+ 项） |
| 离线重复提交 | submission_id 幂等（checkin submissions + offline.test.ts） |
| 并发任务/崩溃恢复 | task_dispatcher.recover_stale + 修订号乐观锁 |
| 数据删除 | test_p7b 账户删除闭环 |
| LLM 超时/故障 | 协作链路无 LLM（结构保证）；聊天链路失败不阻塞记录 |
| 问题分级 | 见 docs/p10-release-readiness.md 门槛 |

## 分层声明

T1（确定性单测）/T2（API 集成）/T3（浏览器 E2E）已覆盖并在 CI；
**T4（真实模型）/T5（实体手机）/T6（长期真实使用）未执行，不能由
T1–T3 结论替代**——这是发布前必须如实保留的边界。
