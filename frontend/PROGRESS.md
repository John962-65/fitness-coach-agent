
## 四十六、M5.2 复查处置：存储边界/审核原子性/UI 闭环/覆盖率/证据绑定（2026-10-24）

对照与证据见 TASKBOOK_2.0.md §十六。

- **P0-1**：custom_exercises 表 + coach/exercise_service.py 统一动作服务；审核入库写 SQLite（本人可见），搜索/详情/计划/媒体全走 service（resolver 注入 plan_edit/changes）；exercises/ 目录零写入。
- **P0-2**：审核原子化（pending 校验→冲突→插入→读回→提交；四类失败保持 pending）；测试覆盖重复批准/非法 id/别名冲突/id 已存在。
- **P0-3**：三步上传 UI + 无候选视频手动提案（端点+表单，转写首句作依据）→ 审核入库全链路；E2E 含多用户隔离矩阵（A 可见可加入 / B 搜索空、详情 404、加入 422）。
- **P1**：detection_ratio+valid_ratio 双质量门；citations 证据绑定（编造剔除、无引用标 inferred）；草稿命中逐引擎读取修复。
- **验证**：全量 **583 passed**（577 零退化+6）；E2E 截图链路。
- 发起人建议接受：静态审查驱动的连续修复到此收束，转入真实使用验证（M6，需发起人执行）。
