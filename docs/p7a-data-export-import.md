# P7-A 数据导出与备份导入——交付

> 基线：`e2a16d2`（P6-C）｜ 日期：2026-10-27

## 导出

`POST /users/{uid}/export` `{format: "json"|"csv", confirm: true}`
（敏感健康数据：未显式 confirm 一律 422）。

- **JSON**：`fcs-export-v1`，节包括 user_data（档案/计划/模板/训练打卡
  及修订史/餐次/自定义食物与食谱/身体/恢复/症状/限制/个人尝试/器械地点/
  洞察与动作分析索引）、source_revisions、exercise_mapping、
  equipment_mapping、media_manifest（文件引用+存在时 sha256，不导出
  临时 URL）、integrity_manifest（各节 sha256，可校验篡改）。
- **CSV**：zip（每节一文件；训练逐组展开 training_sets.csv；含完整性
  清单）。

## 导入

`POST /users/{uid}/import/preview`（不写库）→ 版本/未知节/完整性校验、
逐节计数、按内容指纹识别重复、动作/器械映射冲突（以当前库为准）、
媒体文件存在性说明 → `POST /users/{uid}/import/apply`
`{backup, confirmed: true}`：

- 白名单节 + 行级必填校验（缺字段快速失败，不进事务）；
- 单事务写入；异常整体回滚；
- 不覆盖既有记录（同指纹跳过，幂等）；
- 导入的计划版本非激活（不改变当前生效版本）；导入的训练限制置为
  lifted（不静默改变当前安全状态）。

## 测试

`test_p7a.py` 4 项：confirm 强制与 JSON 校验和、CSV 可读 zip、
预览重复/未知节/篡改拒绝、往返一致 + 幂等 + 事务回滚 + 用户隔离。
`test_experts.py` 更新（注册表新增 collaboration）。

已知限制：导入为"新增合并"模式，不做字段级覆盖合并；媒体文件本体不随
JSON 导出（清单可核对，文件复制属部署级备份方案）。
