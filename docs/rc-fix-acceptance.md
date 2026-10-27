# RC-FIX 验收：发布阻断项修复

> 基线：`d0b26e8`（RC 验收提交）｜ 日期：2026-10-27
> 范围：RC-0 的 6 项未关闭 P1 + 与发布安全直接相关的 P2；不新增业务模块。
> 结论：**软件工程阻断项已消除；RC-2/T5、RC-3 专业审核、RC-4/T6 仍是外部未完成项，最终决策仍为 BLOCKED。**
> 本文件只把“有测试/探针/E2E 证据”的项标为已关闭；没有证据的项保持原状态。
> E2E 日志：[data-autonomy](rc-fix-evidence/e2e-data-autonomy.log)｜[trial/insight](rc-fix-evidence/e2e-trial-insight.log)；截图在 `docs/rc-fix-shots/`。

## 0. 验证入口

```bash
# 后端全量（最终数字见 §8）
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider --confcutdir=$PWD

# RC-0 探针（11 个 checks；任何 violation 退出码 1）
FAKE_LLM=1 PYTHONPATH=$PWD python3 tools/rc0_audit_probe.py

# 浏览器 E2E（需要 google-chrome；脚本自带临时后端/前端）
node tools/e2e_rc_fix.mjs
node tools/e2e_rc_fix_c.mjs

# RC-1 残余专项（真实模型；本地 .env 凭据）
python3 eval/run_rc1.py --only collab-tr-02-missing,rehab-03-numbness,... 
```

探针最终输出：[probe-20261027.json](rc-fix-evidence/probe-20261027.json)。

## 1. RC-FIX-A：完整备份与恢复（RC0-10）

### 1.1 实现

- 导出扩展为 45 个 `user_data` 节：计划（含 `active`）、打卡与修订、餐次/自定义食物/食谱、身体/恢复及修订、症状/观察、限制/修订、个人尝试、模板、器械、地点、训练方式/修订、营养目标/日状态、动作反馈、教练笔记、知识讨论、专业安排、设备记录、知识来源/分块/观点、对话/咨询、变更提案、媒体/动作分析元数据。
- 导入覆盖核心业务数据；关系映射：
  - 打卡 → checkin_revisions / 尝试 baseline_source_revisions；
  - 症状 → 观察 / 限制 related_episode_id；
  - 计划 → 尝试 plan_id；
  - 身体/恢复/限制 → 各自修订；
  - 自定义食物 → 餐次/食谱 items。
- 幂等：计划版本、打卡内容、身体指纹、恢复日期、症状指纹、限制指纹、尝试自然键、模板/食谱/食物/地点名称、器械 ID、知识内容哈希、修订 `(parent, revision)` 均跳过重复。
- 计划：默认**归档**（inactive）；`activate_plan=true` 且通过医疗许可/计划隔离/当前限制检查才恢复为可执行；目标已有生效计划时需 `replace_active_plan=true`。
- 安全状态：professional 限制解除缺少 ≥10 字专业人员说明时保持 `active` + `needs_review`；医疗筛查/训练许可默认置为“未核验”，只有显式 `accept_safety_import=true` 才按备份声明导入。
- 媒体：清单校验存在性 + sha256 + **只允许源用户 media 目录内路径**；不复制文件；`require_media_integrity=true` 时缺失/损坏/越界直接 422。
- 事务：profile/计划/所有业务写入在同一 `with db.conn` 内；注入中途异常测试验证回滚。
- 哈希：`_integrity` 规范化整数值浮点（75.0→75），避免浏览器 JSON roundtrip 后误判篡改；`verify_integrity` 兼容旧清单。

### 1.2 证据

- `test_rc_fix_a.py`（8 项）：两计划、3 打卡+修订、1 尝试、2 模板、1 食谱、身体/恢复+修订、症状+观察、professional 限制、2 地点、2 器械；导出→导入→关系核对→重复导入→再次核对；archive/executable、限制阻断、专业解除证据、profile 安全字段、媒体哈希、事务回滚。
- `test_p7a.py` 4 项仍通过（兼容旧 API）。
- 探针 `backup_restore`：重复导入后 counts 精确；专业限制保持 active；`checks` 通过。

## 2. RC-FIX-B：账户删除与前端数据自主（RC0-16/17）

### 2.1 实现

- `coach/account_deletion.py`：两阶段删除。
  - 先把 `media/<uid>` 原子移动到 `media/.deleting/<uid>-ts`；
  - 数据库删除（含无 `user_id` 的 `knowledge_chunks` / `expert_task_events`）；
  - 成功后删除回收目录、过滤 `unmatched_exercises.jsonl` / `knowledge_loads.jsonl`、WAL checkpoint + VACUUM；
  - 数据库失败恢复媒体目录并抛错；文件/日志清理失败返回 `complete=false`，不宣称彻底删除；
  - 响应包含备份保留期限、备份通知、法定保留说明、外部路径未删除清单。
- `db.delete_user` 增加无 `user_id` 子表清理；API 路由改用 deletion service。
- 前端：
  - 完整导出 JSON / CSV（调用服务端 `/export`）；
  - 选择备份 → 预览计数/冲突/安全字段/媒体报告 → 显式选项 → 确认导入；
  - 删除账户需输入 `DELETE` + 勾选 + 二次确认；
  - 删除成功后清 localStorage（`fc-*`/草稿）、IndexedDB 离线队列/失败记录、Cache Storage；失败/不完整不显示成功。
- 新增 `frontend/src/lib/localData.ts`、`offline.clearOfflineData()`。

### 2.2 证据

- `test_rc_fix_b.py` 4 项：DB/媒体/子表/日志清理、外部路径不删除且 complete=false、删除失败保留用户与文件、late rmtree 失败报告不完整；另一用户完整保留。
- `tools/e2e_rc_fix.mjs` 浏览器 E2E：
  - A 完整导出下载 → JSON 有效；
  - 切 B → 文件选择 → 预览 → 确认导入 → B 有训练记录；
  - 删除 B → 欢迎页 → B API 404、A API 200、localStorage 清空；
  - 截图：`docs/rc-fix-shots/rc-fix-e2e-delete-welcome.png`。

## 3. RC-FIX-C：长期报告、洞察与尝试窗口（RC0-01/02/03/08）

### 3.1 实现

- `long_term_report._sessions_in()`：同一打卡聚合全部动作，不再 break；力量组/容量/有氧分别累计；超级组不重复、递减/单侧按段容量、有氧/HIIT 不入力量口径。
- `training_calendar.period_summary()`：改为按会话本地日期过滤，与训练事实/长期报告同一窗口。
- 洞察生命周期：
  - 新增 `training_scope_signature()`（动作/窗口的 count、last_checkin_id、revision_total）；
  - next-training 与 collaboration 洞察写 `training_scope`；
  - `_revision_drift` 在读取时重算签名，新增/删除/纠错相关训练即失效；不相关动作不误伤；
  - 保留计划版本、恢复/营养/症状/限制/器械/rules 既有依赖。
- PersonalTrial：
  - 观察不再截断 8 条；
  - 使用 `start_checkin_id`/`end_checkin_id` + 完整时间边界，排除开始前同日记录和结束后新增；
  - 排除替换掉尝试动作的会话；
  - 结束时的复盘写入 `review_snapshot`，之后新增训练不改变历史；
  - 历史纠错使 `needs_rereview=true` 并列出变化；新增 `rereview_ended_trial` + `POST /trials/{id}/rereview`，原快照不自动覆盖。

### 3.2 证据

- `test_rc_fix_c.py` 9 项：1 会话 8 组/4400kg、复杂组/有氧/HIIT、本地日期窗口、相关/不相关训练失效、删除/纠错失效、协作失效、10 次观察+冻结+纠错复核、同日/替换排除。
- `test_rc_fix_a.py` 验证两计划、尝试 plan/checkin 引用映射。
- `tools/e2e_rc_fix_c.mjs`：真实浏览器中洞察显示「已失效」；PersonalTrial 显示观察期内 10 次训练，结束后新增训练仍冻结 10 次。截图：`docs/rc-fix-shots/rc-fix-e2e-trial-frozen.png`。
- 探针 `long_term_report`/`window_consistency`/`insight_staleness`/`trial_observation` 全部通过。

## 4. RC-FIX-D：安全 P2 与 RC-1 残余（RC0-06/07/12/13/15/20）

- **RC0-06**：确认必须引用提案 ID 或具体修改内容（操作值/reason n-gram）；裸“好/确认”返回 `pending/unclear`。UI 确认消息带 proposal id；`test_rc_fix_d.py` 覆盖，`test_changes.py` 更新为显式引用。
- **RC0-07**：导入安全字段默认不可信；`accept_safety_import=true` 才按声明；限制 source_type/status 白名单校验；专业限制缺依据保持 active；`test_rc_fix_a.py` 覆盖。
- **RC0-12**：媒体清单存在性+sha256+路径边界；`require_media_integrity` 拒绝损坏/缺失/越界。
- **RC0-13**：`Content-Length` 中间件（JSON 50MB/上传 200MB）、字幕 2MB、PDF 20MB/200 页/2M 字、导入 JSON 深度 40/节点 200k、50MB 上限。
- **RC0-15**：CSV 单元格 `= + - @ \t \r` 前缀转义；`test_rc_fix_d.py` 验证。
- **RC-1 残余**：`eval/run_rc1.py` 明确 `source_revisions/safety_gates` 不是 fact_id，urgent 与 triage 对齐；专项复跑 16 条，0 unknown citation，红旗 urgent 3/3 对齐。
- 证据：`test_rc_fix_d.py` 5 项；`docs/rc1-evidence/rc1-20261027-133708.json` + review。

## 5. 探针结果（RC-FIX 后）

`tools/rc0_audit_probe.py` 的 6 个既有复现案例 + 11 个 checks：

| check | 结果 |
|---|---|
| backup_restore_counts | PASS（无重复、无缺失） |
| backup_restore_restrictions_active | PASS |
| long_term_report_matches | PASS（8 组/4400kg） |
| deletion_media_gone / orphans_gone / complete / profile_gone | PASS |
| window_consistent | PASS（事实/周期/报告均 0） |
| insight_invalidated | PASS |
| trial_all_sessions / trial_frozen | PASS（10/10） |

`violations=[]`，退出码 0。原始输出见 [probe-20261027.json](rc-fix-evidence/probe-20261027.json)。

## 6. 全量回归

| 项 | 结果 |
|---|---|
| 后端 pytest | **909 passed / 691.40s**（最终全量） |
| 前端 Vitest | 74 passed / 11 files |
| 前端构建 | tsc --noEmit + Vite 通过 |
| 新增专项 | `test_rc_fix_a.py` 8、`test_rc_fix_b.py` 4、`test_rc_fix_c.py` 9、`test_rc_fix_d.py` 5 |
| 原有回归 | `test_p7a`、`test_p7b`、`test_p5c2`、`test_p5c3`、`test_changes`、`test_analytics`、`test_p7d` 等通过 |

## 7. 提交

| 提交 | 内容 |
|---|---|
| RC-FIX-A | 备份导出、完整恢复、幂等、计划激活、限制安全、媒体校验 |
| RC-FIX-B | 账户删除、媒体回收、前端数据自主、E2E |
| RC-FIX-C | 长期报告、洞察 scope、PersonalTrial 窗口/冻结 |
| RC-FIX-D | 确认引用、导入来源、资源上限、CSV、RC-1 残余、文档 |

实际 commit hash 见 `git log`；本文件在最终提交前生成。

## 8. 最终记录（2026-10-27）

- 后端全量：**909 passed**（691.40s；最终全量见测试日志）。
- 前端：74 passed；构建通过。
- 探针：11/11 checks，violations=[]。
- E2E：
  - 数据自主：`ok=true`，A 完整导出、B 预览恢复、B 删除 404、A 完整、localStorage 0 key。
  - 洞察/尝试：`ok=true`，insight_invalidated=true，trial_sessions=10，review_frozen=true。

## 9. 仍然不能宣称的事

- 不能宣称 RC 通过：T5/T6/RC-3 专业审核仍未完成。
- 不能宣称临床安全：RC-1 是固定样本真实模型评测，不是临床验证。
- 不能宣称“账户删除在所有部署中彻底完成”：应用内已清理 DB/媒体/子表/可归属日志；部署方备份/快照/`agent.log` 需按保留政策处理，API 以 `complete=false` 明示。
- 不能宣称导入来源可信：哈希只证明文件未变，导入权限仍依赖本地单用户边界。
- 不能宣称媒体文件随 JSON 恢复：JSON 只含清单与哈希；文件需单独复制/恢复。
- 不能宣称多用户隔离：本地共享令牌边界仍在；云端身份方案未实现。
- 剩余 P2/P3：主教练自然语言选边、尝试计划变更仍按旧目标、PWA 图标、应练次数取整等，见 RC-0。

## 10. 外部门槛（不变）

- RC-2/T5：实体 Android/iOS 验收未执行。
- RC-3：合格专业人员审核 0。
- RC-4/T6：2–4 周真实试用 0 人。
- 因此 [RC-5](rc-release-decision.md) 仍为 **BLOCKED**；本阶段只关闭软件工程阻断项。
