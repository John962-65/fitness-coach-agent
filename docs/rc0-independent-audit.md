# RC-0 独立源码审查

> 基线：`750cd3b`（P10）｜ 审查日期：2026-10-27
> 审查方式：源码走查 + 临时库复现 + 全量回归；**不读取 `data/` 真实用户数据**。
> 结论：**未发现 P0；原始发现 7 项 P1、10 项 P2、5 项 P3。RC-FIX 后 7 项 P1 全部关闭；剩余 P2 2 项、边界 2 项、P3 2 项；工程阻断项已消除，但最终 RC 仍受 T5/T6/专业审核阻断（见 RC-5）。**
> RC-FIX 关闭证据：[rc-fix-acceptance.md](rc-fix-acceptance.md)；RC-FIX 后探针：[probe-final](rc-fix-evidence/probe-20261027.json)。
> 复现入口：`FAKE_LLM=1 python3 tools/rc0_audit_probe.py`
> 原始输出：[probe-20261027.json](rc0-audit-evidence/probe-20261027.json)｜[RC-1 修复后复跑](rc0-audit-evidence/probe-20261027-after-rc1-fixes.json)（备份/报告/删除/窗口/洞察/尝试六项 P1 复现不变）

## 0. 基线核实

| 项 | 结果 |
|---|---|
| 分支 / 提交 | `master` / `750cd3b P10 — 发布准备门槛清单与路线图收尾` |
| 工作树（审查开始时） | clean |
| 后端全量回归 | **880 passed**（686.85s；命令见 README：`FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q -p no:cacheprovider --confcutdir=$PWD`） |
| 前端回归 | **74 passed / 11 files**（`npm test`） |
| 前端构建 | `npm run build` 通过（tsc --noEmit + Vite；592.45 kB / 918.33 kB 两个 chunk 有体积告警） |
| 文档基线 | `docs/p10-release-readiness.md` 声明“开发侧门槛全部就绪”；本审查逐项复核，发现该声明对导出/删除/备份恢复/长期报告等 4 项过于乐观 |

审查只针对源码与合成数据。真实模型行为见 [RC-1](rc1-real-llm-evaluation.md)；实体设备见 [RC-2](rc2-device-acceptance.md)；专业审核见 [RC-3](rc3-professional-review.md)；长期试用见 [RC-4](rc4-longitudinal-beta.md)。

## 1. 训练数据一致性

### 1.1 结论

周期统计、月历、动作表现、训练事实的大部分计算共用 `activity_class` 与 `set_volume`，方向正确；但仍有 **1 项 P1 数值错误**、1 项 P2 日期窗口不一致、1 项 P1 洞察过期缺口。

### 1.2 RC0-01（P1）长期报告只统计每个打卡的第一个动作

**位置**：`coach/analytics/long_term_report.py:209-244`，`_sessions_in()` 在第一个有工作组动作后直接 `break`。

**复现**：一次训练含卧推 60kg×10×4 与深蹲 100kg×5×4。

| 接口 | 工作组 | 容量 |
|---|---:|---:|
| `/period-summary`（同源口径） | 8 | 4400 kg |
| `/long-term-report`（P7-D） | **4** | **2400 kg** |
| 期望 | 8 | 4400 kg |

**影响**：长期报告（周/月/自定义区间）的系统性低报，且动作顺序不同会改变结果；与 P10 门槛 #4“历史纠错与统计一致”直接冲突。`test_p7d.py` 只用了单动作 fixture，未覆盖多动作。

**建议**：按打卡聚合所有动作的力量组/容量/有氧秒数，再追加一条会话记录；补多动作回归。

### 1.3 RC0-02（P2）训练事实/周期统计按 `created_at` 取窗，长期报告/月历按本地日期取窗

**位置**：`coach/analytics/training_calendar.py:218-226`（`since = datetime.now() - days` 后按 `created_at` 过滤）；`fact_service.get_training_facts()` 又把 `period_summary` 的结果嵌入“同口径”事实包；`long_term_report._sessions_in()` 按 `session_local_date()` 过滤。

**复现**：插入一条 `created_at=now`、`session_meta.local_date=31 天前` 的训练。

| 接口 | 会话数 |
|---|---:|
| `get_training_facts(30)` | 1（来自 `period_summary`） |
| `period_summary(30)` | 1 |
| `long_term_report(month)` | 0 |

**影响**：同一时间窗的“训练事实”和“长期报告”可以给出相反结论；导入旧备份、纠错日期、跨时区/跨午夜记录都可能触发。当前边界只差 1 天，但根因是两套窗口口径。

**建议**：周期统计改为按 `session_local_date()` 过滤（可保留 `created_at` 预筛但必须再按本地日期裁剪），并加边界回归。

### 1.4 RC0-03（P1）新增训练记录不会使“下一次训练建议”洞察失效

**位置**：`coach/experts/insight_service.py:37-59` 的 `_revision_drift()` 只检查 `source_revision.checkins` 中**已引用**的打卡修订号、计划版本等；`coach/experts/training_science.py:768-782` 的 `next-training-review` 没有记录“训练记录总数/最新打卡”。

**复现**：1 次卧推 → 请求 next-training 洞察（`ready`）→ 再保存 1 次卧推 → 读取洞察。

```
status_before_new_workout = ready
status_after_new_workout  = ready
status_reason             = null
```

**影响**：用户完成新训练后仍会看到基于旧数据生成的“下一次训练建议”，且该洞察可继续走 `stage_option_proposal`（确认时虽会重校验计划/安全，但建议本身已过期）。跨专家 `collaboration-review` 同样只记录被引用打卡，新增训练不会使其失效（`build_evidence_bundle._rev()` 的 `checkins` 仅来自事实引用）。

**建议**：next-training 与 collaboration 洞察的 `source_revision` 增加 `training_records_count`（或最新训练打卡 id），`_revision_drift` 发现计数增加即 `invalidated`；post-workout 回顾不适用此规则。

### 1.5 通过项

- 周期统计/月历/动作表现/训练事实在力量、有氧、HIIT 的分类上共用 `activity_class` 与 `set_volume`；`test_p5b3`、`test_p5c3` 覆盖混合训练、复杂组、纠错后统计。
- `fact_service` 的 `insufficient` 不伪装成 0；无记录与零次训练区分（`frequency-*` 的 observed 0）。
- 纠错后的 `checkin_revisions` 计数会触发引用洞察失效（`test_p5b3`）。
- 月历按本地日期二次过滤；周期汇总的 `_MAX_SCAN_DAYS=400` 有上限。

### 1.6 RC0-04（P3）计划完成率“应练次数”取整

`long_term_report.build_report()` 用 `days_per_week * max(1, round(days/7))` 估算应练次数；30 天窗口 3 天/周得到 12 而不是 12.9，报告口径是“提示”而非完成率分母，影响有限，但应在文案或计算中明确取整规则。

## 2. 专家决策安全

### 2.1 结论

**未发现源码级可绕过硬安全门的写路径**。计划/训练方式修改统一走 `ChangeProposal`；`stage_ai` 只落 pending，`confirm_proposal` 会重新跑 `validate_change`（医疗许可、计划隔离、伤病关节、训练限制、乐观锁）；跨专家报告不直接改计划，协作 options 不携带 `proposal_hint`。但存在 **2 项 P2 语义/时效风险**，需要在 RC-1 用真实模型复测。

### 2.2 通过项

| 检查 | 证据 |
|---|---|
| AI 只能暂存提案，不能直接写计划 | `coach/changes.py:stage_ai()`；`recommendation_service.stage_option_proposal()` 只调 `stage_ai` |
| 确认时重校验版本与安全 | `confirm_proposal()` 调 `validate_change()`；`test_p3.py::test_restriction_cannot_be_bypassed_via_ai_stage` |
| 恢复旧计划同样过安全门 | `restore_plan_version()` 对恢复内容重新跑 `validate_plan_change()` |
| 跨专家分歧不投票、不合并 | `conflict_resolver.resolve()`；`coordinator.combine()` 只加“并列保留”说明 |
| 安全门优先于方案 | `coordinator.analyze_collaboration()` 在 `safety_gates` 存在时只保留 `keep-current`/`observe-only` |
| 协作报告不修改原始事实 | `insight_service.create_insight()` → `validate_evidence()` 只剔除非法引用，不改写 `facts_snapshot` |
| 协作方案不能直接生成长期提案 | 协作 options 无 `proposal_hint`；`stage_option_proposal()` 会拒绝 |
| 同轮自批被拒 | `confirm_proposal()` 比较 `created_message_id` 与最新用户消息 |

### 2.3 RC0-05（P2）主教练的自然语言仍可能“选边”

确定性 `combine()` 不选边，但主教练/专家 LLM 的输出可能用“听恢复顾问的”之类措辞替用户裁决。P9-C 的 8 例真实模型运行中，`collab-01-disagreement-merge` 即出现“听恢复顾问的：先观察，暂不加重”，随后才补充“双方并列”。这属于 **agency/表达层**问题，不是数据库写路径绕过，但违反“不替用户裁决”。

**处置**：RC-1 对主教练/协作场景使用更明确的“不得选边、不得声称一致”约束并重复测试；若仍复现，应把“并列呈现”做成确定性模板，LLM 只填事实，不自由总结。

### 2.4 RC0-06（P2）单一 pending 提案下，裸“好/确认”可被当作同意

**位置**：`coach/confirmation.py:87-106` 的 `classify_decision()` 把“好的/确认/行”判为 accept；`changes.confirm_proposal()` 只在**多条 pending**时要求注明提案 ID。

**场景**：用户对上一轮无关话题说“好的”，模型若错误地调用 `confirm_proposal`，在只有一条 pending 时会被接受。模型提示要求“必须指向该提案”，但代码没有强制引用；这是“模型纪律”而非“硬门”。

**建议**：单一 pending 也要求提案 ID 或明确的提案内容引用（至少一个来自提案的关键词/数值），或要求前端按钮确认；不要把裸“好”当长期方案同意。

### 2.5 RC0-07（P2）导入可改写安全相关字段，缺少来源/权限校验

`import_service` 会写入 `profile.conditions`（含伤病/健康筛查）、`symptom_episodes.professional_evaluated`、`training_restrictions.status`。它只校验 schema 与 SHA-256 清单；**SHA-256 只能证明“文件未被改动”，不能证明“来源可信”**。任何能调用导入接口的人都可以构造一份哈希自洽的备份，写入“无伤病”“已专业评估”“限制已解除”等状态。本地单用户模式下这是用户自己的数据；一旦按 P7-B 的云端方案复用同一接口，就是跨用户/越权写入风险。

**建议**：导入入口绑定身份与资源属主；`professional_evaluated`、`source_type=professional`、`plan_fence` 等安全字段要求额外确认或禁止导入；导入预览明确列出“将改变的安全状态”。

### 2.6 审查后由 RC-1 补充发现（已修复）

RC-1 的真实 agent 探针又发现 3 个**源码级**安全缺口，已在 RC-1 阶段修复并重跑（不计入本文件的 7 项 P1 统计，因为已关闭）：

1. `CoachAgent` 的 system prompt 没有 `TrainingRestriction` 统一安全视图：存在 professional 限制时，聊天仍建议受限动作（agent-02/04）。已增加 `_restrictions_text()` 与工作方式第 16 条。
2. 红旗词表缺少“胸口有点痛/胸口隐隐作痛/心口疼”等口语：agent-05 未立即建议就医。已扩 `red_flags.md` 与 `triage_rules.py`，并由确定性前置直接返回急症话术。
3. `parse_advice` 对字符串字段直接丢弃：16 个真实模型案例的 `conditions/risks` 会从产品建议中消失。已改为单元素列表保留，并补测试。

详见 [RC-1](rc1-real-llm-evaluation.md) §4。

## 3. 候选与个人尝试

### 3.1 通过项

- 候选 `option_id` 由确定性引擎生成；`start_trial_from_candidate()` 服务端重算候选，记录 `origin{kind, origin_insight_id, origin_option_id, rules_version}`、`plan_id/plan_version`、`chosen_target`、观察指标与基线快照；`test_p5c3.py::test_trial_from_candidate_records_linkage_and_baseline` 覆盖。
- 同一时间只允许一个 active 尝试；`keep/adjust/stop` 不自动修改长期计划（`test_p5c3.py` 覆盖）。
- 纠错后观察读取 `revision`，`test_p5c3.py` 覆盖。
- 计划版本变化会在观察中标 `plan_changed_since_start`，复盘把它列入“无法确认”。

### 3.2 RC0-08（P1）PersonalTrial 观察只取最近 8 次，且不按结束时间冻结

**位置**：`coach/training_progression/trial_service.py:211-236`。

```python
start = str(trial.get("created_at") or "")[:10]
sessions = [... if s["date"] >= start]
for s in sessions[:8]:
```

**复现**：尝试开始后 10 次训练 → `trial_observation.sessions_total = 8`（实际 10）；结束尝试后再加 1 次 → 观察仍把新记录计入（`ended_at` 已存在）。

**影响**：
1. 观察期超过 8 次时，只统计**最新** 8 次，早期未达标记录被丢掉，结果偏向“达成”；
2. 尝试结束后复盘仍会随新训练变化，`outcome` 文本与 `trial_review` 可不一致；
3. `created_at[:10]` 是服务器日期，尝试当天更早的训练也会被算进观察期。

**建议**：观察窗口以 `[created_at, ended_at or now]` 的完整时间过滤；不截断计数（展示可分页）；复盘以结束时的快照冻结，后续只读。

### 3.3 RC0-09（P2）尝试与计划版本的关联没有覆盖“同一天计划变更”

`plan_changed_since_start` 只比较 `plan_id/plan_version`；同一天内计划版本变化仍会被识别（版本号变化），但观察指标仍按旧 `chosen_target` 计算，复盘只提示“同期变化”，不重算目标。建议在计划变化后把观察标记为 `not_comparable`，而不是继续给出达成/未达成。

## 4. 数据导入导出

### 4.1 RC0-10（P1）备份“恢复”不完整且不幂等

**位置**：`coach/data_transfer/import_service.py:168-300`。

**复现**（同一份备份导入新用户两次）：
- 导出包含 17 个 `user_data` 节；导入只处理 checkins/plans/meals/body/recovery/symptoms/restrictions/custom_foods。
- 两次导入后：`plans=3`（新用户原有 1 个 + 2 次重复导入）、`body_measurements=2`、`symptom_episodes=2`、`training_restrictions=4`；`personal_trials/training_templates/nutrition_recipes/user_equipment/training_locations` 全部为 0。
- 所有导入的 `training_restrictions.status` 被写成 `lifted`（包括 `source_type=professional`）。
- 导入的计划 `active=0`；新用户导入后 `get_active_plan_record()` 为 `None`。
- `inserted["recovery"]` 在 `INSERT OR IGNORE` 跳过时仍 +1，计数与实际行数不一致。

**影响**：
- 用户以为“完整备份已恢复”，实际丢失个人尝试、模板、食谱、器械、地点、洞察/动作索引；
- 重复导入造成计划版本、身体、症状、限制重复；
- 专业限制被静默降级为 lifted，恢复后的安全状态比备份源更宽松；
- 新用户没有生效计划，无法直接继续训练。

**建议**：以 `(user_id, version)` 唯一约束 + `INSERT OR IGNORE` 去重计划；为 body/symptoms/restrictions 建内容指纹；恢复 `personal_trials/templates/recipes/equipment/locations`；安全字段保持原状态或要求显式确认；恢复 active plan 时明确提示并让用户选择；修正计数。

### 4.2 RC0-11（P2）完整性清单不是来源证明

`_validate_payload()` 只检查 `schema_version`、未知节、`verify_integrity()`（各节 SHA-256）。攻击者可以重算哈希；`exported_for` 不要求等于目标用户；导入预览明确允许把 u 的备份导入 v（`test_p7a.py`）。这与任务书“SHA-256 不能证明来源可信；导入入口仍需严格校验和权限控制”一致，属于必须记录的边界。

### 4.3 RC0-12（P2）媒体清单只核对“文件存在”，不核对 sha256

`apply_import()` 返回 `missing_media_files` 时只 `os.path.exists(file_ref)`；清单中的 `sha256` 未复核。文件存在但内容错误/被替换时会被当作可用；`file_ref` 是绝对路径，备份不可移植且泄露本机目录结构。媒体文件本体不随 JSON 导出（P7-A 已声明），但“恢复验证”不能只靠存在性。

### 4.4 RC0-13（P2）上传/解析资源上限不完整

- `backend/routes.py:693` 字幕文件 `subtitle_path.write_bytes(await subtitle.read())` 无大小上限；视频有 200MB 流式上限，字幕没有。
- `/knowledge/imports` 的 PDF `base64.b64decode` 与 `fitz.open` 无请求体/页数上限；本地/局域网令牌持有者可造成内存/CPU 压力。
- `import/preview` 的 `payload: dict = Body(...)` 先完整解析 JSON，再校验；无请求体大小限制。
- 视频容器只检查首 16 字节魔数（`ftyp`/EBML），不是完整解码；这是合理的轻量门，但不能证明文件安全。

**建议**：给字幕/PDF/JSON 设置显式 body 大小上限（如 2MB/20MB/50MB），在解析前拒绝；字幕只接受 UTF-8 文本并限制行数。

### 4.5 RC0-14（P3）路径包含判断使用字符串前缀

`backend/routes.py:639` 媒体文件、`backend/app.py` SPA 静态文件都用 `str(target).startswith(str(base))`。若未来允许 `name` 含路径分隔符，`/media/u` 与 `/media/u2` 的前缀碰撞会放行；应使用 `Path.is_relative_to()` 并显式拒绝 `..`/绝对路径。当前路由参数不含 `/`，利用条件有限，列为纵深防御。

### 4.6 RC0-15（P3）CSV 导出未防公式注入

`export_service.export_csv()` 直接把用户可控字段（动作名、备注、食物名）写入 CSV；以 `= + - @` 开头的单元格在 Excel 中可能被当公式执行。本地自用风险低；若导出文件被分享/云端多用户，应加前缀转义。

### 4.7 通过项

- 导入白名单节 + 行级必填校验 + 单事务回滚（`test_p7a.py::test_import_apply_roundtrip_rollback_and_isolation`）。
- 重复 checkin 按内容指纹跳过；设备导入按 `(source_platform, source_record_id)` 去重，单位白名单换算。
- 上传文件名 `Path(filename).name` 去路径；视频首块魔数校验；每用户文件数/总容量配额。
- 导出需 `confirm=true`；JSON 完整性清单可检测意外篡改。

## 5. 账户删除

### 5.1 RC0-16（P1）删除范围不完整：媒体、知识分块、任务事件、客户端缓存

**位置**：`coach/db.py:670-688`。

`delete_user()` 只删除“含 `user_id` 列的表”。复现（临时库）：

```
deleted_rows = {expert_tasks: 1, knowledge_sources: 1, media_assets: 1, users: 1}
media_file_still_exists = true
orphan_knowledge_chunks = 1
orphan_task_events = 1
```

具体缺口：
- `data/media/<uid>/` 下的视频、封面、片段不删除；`motion_analyses.video_path` 指向的文件同样保留；
- `knowledge_chunks` 无 `user_id`，随 `knowledge_sources` 删除后成为孤儿，正文仍在库中；
- `expert_task_events` 无 `user_id`，随任务删除后成为孤儿；
- 未 `VACUUM`，删除行可能留在 SQLite 空闲页/WAL；
- 前端 `localStorage`（计划缓存、离线队列、访问令牌）与 IndexedDB（失败记录）没有在删除后清理；
- `data/unmatched_exercises.jsonl`、`data/agent.log`、`knowledge_loads.jsonl` 等日志含用户 id/问题片段，未纳入删除；
- 备份保留政策未文档化（`data/` 备份、导出文件副本、部署级快照）。

**结论**：P10 门槛 #10“用户能导出/删除个人数据 ✅”不成立。当前 API 删除后，健康视频与部分文本仍留在磁盘。

### 5.2 RC0-17（P1）前端“导出我的数据”只导出 3 个对象，且没有删除账户入口

**位置**：`frontend/src/pages/MineSettings.tsx:23-42`。

“导出我的数据（JSON）”只 `api.profile / api.approach / api.trials` 三个请求，然后本地拼 JSON；没有调用 `POST /users/{uid}/export`，因此训练、饮食、身体、恢复、症状、限制、媒体清单、完整性清单都不在文件里。UI 也没有 `DELETE /users/{uid}/account` 的入口。P10 的“导出 + 删除闭环”只在 API 层存在，用户实际不可完成。

**建议**：UI 直接调用后端导出（confirm 二次确认），删除入口放在危险操作区并二次输入；删除成功后清空本地缓存与 IndexedDB，提示备份保留政策。

### 5.3 RC0-18（P2）本地模式媒体/资源的“用户隔离”依赖共享令牌

`/api/media/{uid}/{name}` 在无令牌本地模式不校验 uid 归属；配置 `API_ACCESS_TOKEN` 后也只校验共享令牌，不校验“令牌属于哪个 uid”。这与 P7-B 的本地单用户定位一致，但不能外推为多用户隔离。云端多用户模式必须按 P7-B §3 实现逐资源授权，当前未实现，不能仅凭设计文档宣称可用。

## 6. 其他发布工程发现

### 6.1 RC0-19（P1，已修复）P9-C 运行器无法检测真实凭据

原 `eval/run_p9c.py`：
- `from coach.llm import LLM`（不存在，实际类名 `LLMClient`）；
- 未 `load_dotenv`，也不把仓库根加入 `sys.path`，从根目录运行时 `import coach` 失败；
- 因此即使 `.env` 有真实 key，也永远输出 `llm_available=False, ran=0, skipped=8`。

**处置**：本次 RC-1 准备中已改为 `LLMClient` + `load_dotenv` + `sys.path` 注入；修复后 8/8 真实运行（见 RC-1 文档）。这是一项“评测门本身不可用”的 P1，不是产品运行时缺陷。

### 6.2 RC0-20（P2）P9 自动检查对否定句误报

P9 的 `_AUTO_CHECKS` 用裸正则匹配“120kg”“处方:”，把“不能按 120kg”“无法开处方”也标成 fabrication/prescription。修复后的 P9 运行中 `train-01`、`nutri-01` 均被误报。RC-1 runner 已改为否定窗口 + 人工复核，但 P9 自身的历史 flags 不能直接当安全错误统计。

### 6.3 RC0-21（P3）PWA 安装资产不足

`frontend/dist/manifest.webmanifest` 只有 `icon.svg`（`sizes: any`），无 192/512 PNG；`index.html` 无 `apple-touch-icon`。iOS Safari 添加到主屏幕的图标/启动图可能回退或空白；Android Chrome 的安装性也建议提供 192/512 图标。属于 RC-2 的静态风险，不是功能阻断。

### 6.4 RC0-22（P3）文档与代码的措辞不一致

- `import_service.apply_import()` 返回 note 写“导入的训练限制默认置为 resolved”，代码写 `lifted`；
- P10 门槛 #4/#10 的 ✅ 与本审计的复现结果不一致（尤其 #10）。
- 这些不是运行时缺陷，但会误导发布决策；建议在修复前把 P10 表改为“待修复”。

## 7. 分级汇总

| ID | 级别 | 主题 | 状态 |
|---|---|---|---|
| RC0-01 | P1 | 长期报告多动作低报 | **已修复**（RC-FIX-C + 专项测试） |
| RC0-03 | P1 | 新训练不使 next-training/collab 洞察失效 | **已修复**（训练 scope + 专项测试） |
| RC0-08 | P1 | 尝试观察截断 8 次 + 结束后仍变化 | **已修复**（全量观察 + 冻结快照） |
| RC0-10 | P1 | 备份恢复不完整/不幂等/限制降级 | **已修复**（RC-FIX-A + 完整备份测试） |
| RC0-16 | P1 | 删除范围不含媒体/孤儿/日志/缓存 | **已修复**（RC-FIX-B + 删除测试） |
| RC0-17 | P1 | UI 导出不完整、无删除入口 | **已修复**（前端完整导出/预览恢复/删除 + E2E） |
| RC0-19 | P1 | P9-C 运行器不可用 | **已修复**（RC-1 准备） |
| RC0-02 | P2 | 周期统计 vs 长期报告日期窗口 | **已修复**（统一本地日期窗口 + 探针） |
| RC0-05 | P2 | 主教练自然语言可能选边 | **未关闭**：RC-1 协作案例通过，但无确定性约束 |
| RC0-06 | P2 | 单一 pending 下裸“好”可确认 | **已修复**（必须引用提案 ID/内容） |
| RC0-07 | P2 | 导入可写安全字段/来源不可证 | **已修复（受限）**：安全字段需显式接受；来源仍不可证 |
| RC0-09 | P2 | 尝试计划变更后仍按旧目标判定 | **未关闭**（仅标记同期混杂） |
| RC0-11 | P2 | 哈希清单非来源证明 | 边界保留（不做来源证明） |
| RC0-12 | P2 | 媒体只查存在性 | **已修复**（存在性+sha256+路径边界） |
| RC0-13 | P2 | 字幕/PDF/JSON 资源上限 | **已修复**（Content-Length/字幕/PDF/JSON 深度） |
| RC0-18 | P2 | 本地共享令牌非多用户隔离 | 边界保留（本地单用户） |
| RC0-20 | P2 | P9 自动检查否定误报 | **评测侧已修**（RC-1 人工复核；P9 历史 flags 不作结论） |
| RC0-04 | P3 | 应练次数取整 | 记录（未关闭） |
| RC0-14 | P3 | 路径前缀包含 | **已修复**（Path 包含判断） |
| RC0-15 | P3 | CSV 公式注入 | **已修复**（单元格前缀转义） |
| RC0-21 | P3 | PWA 图标资产 | 记录（未关闭） |
| RC0-22 | P3 | 文档措辞/门槛表 | **已修复**（P10 banner + RC 文档） |

**P0：0 项。P1：7 项全部关闭；P2：10 项（6 项关闭、2 项未关闭、2 项边界保留）；P3：5 项（3 项关闭、2 项记录）。另有 3 项 RC-1 补充安全缺口（§2.6）已修复并重跑。**

## 8. 审查局限

- 只审查 `750cd3b` 的源码与合成数据；未读取 `data/coach.db`、真实媒体、真实日志。
- 未执行实体设备、专业人工审核、2–4 周真实试用；这些在 RC-2/3/4 单独记录。
- 未做渗透测试/依赖 CVE 扫描/许可证逐项审计；RC-0 是源码与数据流审计，不是完整安全认证。
- 真实模型行为与“模型是否遵守提示”不在本文件下结论；见 RC-1。
- 复现脚本覆盖 6 条主路径，不等于全量形式化验证；审查结论以源码路径与可复现观测为准。

## 9. 对 RC 的影响

RC-FIX 后 **RC-0 工程阻断项已消除**：7 项 P1 全部关闭，`tools/rc0_audit_probe.py` 全部 checks 通过（11/11），完整备份/删除/报告/洞察/尝试均有专项测试与浏览器 E2E。
但仍不能据此标记 RC：剩余 P2（主教练自然语言选边、尝试计划变更）与边界项（哈希非来源证明、本地共享令牌）需要后续约束/部署边界；更关键的是 RC-2/RC-3/RC-4 仍是外部未完成项。最终决策见 [rc-release-decision.md](rc-release-decision.md)。
