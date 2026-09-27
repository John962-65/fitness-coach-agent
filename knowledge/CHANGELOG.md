# 知识库变更日志

> 每次知识库的新增/修正/推翻都记录在这里。
> 格式：日期 | 操作 | 文件 | 来源 | 备注

| 日期 | 操作 | 文件 | 来源 | 备注 |
|------|------|------|------|------|
| 2026-09-20 | 初始化 | 00_principles/ ×3 | 三家共识提炼 | 渐进超负荷/能量平衡/恢复 |
| 2026-09-20 | 初始化 | 10_programming/ ×2 | 凯圣王公开内容 | 三分化 + 5×5 |
| 2026-09-20 | 初始化 | 20_exercises/ ×13 | 谭成义公开视频整理 | 12 个动作 + 索引 |
| 2026-09-20 | 初始化 | 30_nutrition/ ×8 | chenshi-nutrition-skill 拆分 | 陈石营养体系 |
| 2026-09-20 | 初始化 | 40_collaboration/ ×6 | 凯圣王×谭成义三分化系列 | 6 集 |
| 2026-09-21 | 新增 | 60_injury_safety/red_flags.md | 运动医学通用共识 | 安全底线，代码拦截用 |
| 2026-09-21 | 新增 | 80_troubleshooting/fat_loss_plateau.md | 陈石+凯圣王整合 | 平台期突破 |
| 2026-09-21 | 新增 | 30_nutrition/alcohol_social.md | 陈石生活化减脂 | 应酬饮酒 |
| 2026-09-21 | 新增 | 10_assessment/onboarding_flow.md | 设计书整合 | 评估定级流程 |
| 2026-09-21 | 新增 | 30_nutrition/creatine_supplements.md | 循证文献（ISSN 立场） | 补剂指南，路径2/4缺口补齐 |
| 2026-09-21 | 基础设施 | CHANGELOG.md / knowledge_gaps.log / inbox README | 设计书 8.1/8.3 | 四条扩展路径机制落地 |
| 2026-09-21 | 新增 | 10_programming/advanced_periodization.md | 凯圣王+谭成义+陈石 | 老炮周期化/RPE |
| 2026-09-21 | 新增 | 10_programming/busy_schedule.md | 循证整合 | 忙人每周1-2练方案 |
| 2026-09-21 | 新增 | 80_troubleshooting/return_from_layoff.md | 循证整合 | 停训复训 ramp |
| 2026-09-21 | 代码 | coach/plan.py 重写 | 用户实测反馈 | 系统定级+3类新模板 |
| 2026-09-21 | 合规 | 30_nutrition/slow_cut_protocol.md 等 3 处 | 开源版权处理 | 大段博主原话引语改为转述 |
| 2026-09-26 | 重构 | 60_injury_safety/red_flags.md | 设计书 17.2 S1-S4 | 改三档机器可解析表格，作为 safety.py 关键词单一来源；补横纹肌溶解/同义词 |
| 2026-09-26 | 新增 | exercises/ ×21（动作库） | 设计书 20 章 | R2 数据契约：模板 18 动作 + 常用替代；别名/关节压力/替代关系 |
| 2026-09-26 | 修正+补标 | 全部 40 个知识文件 | 设计书 17.3/19.3（R4） | 补标 provenance；修正 leptin×GLP-1、20-25%串号、卸载周口径、平台期排序、recovery中英混杂 5 处事实错误 |
| 2026-09-26 | 基础设施 | claims/ + tools/distill.py | 设计书 19.2/19.4（R4） | 观点条目库 + 提炼流水线（含反幻觉校验）；视频试点阻塞于字幕源 |
| 2026-09-28 | 基础设施 | tools/fetch_transcript.py + bili_login.py | R4 解除阻塞 | B站/抖音→文字稿流水线：B站扫码登录、AI 字幕直达、whisper 兜底、空间枚举、时间窗切分 |
| 2026-09-28 | claims | claims/tcy.yaml 967 条 draft | 谭成义 18 个视频一手文字稿 | AI 字幕转写 → distill 提炼（反幻觉标红 39 条待人工审核） |
| 2026-09-28 | claims | claims/ksw.yaml | 凯圣王 8 个视频 | 三分化编程/机械张力/口袋教练系列（进行中） |
| 2026-09-28 | 基础设施 | tools/review_ui.py + tools/coverage.py | 设计书 19.2④/21.4 | CLI 审核工具（原文片段+跳转链接+关键帧+通过/拒绝）与动作覆盖率表 |
| 2026-09-28 | 新增 | 70_psychology/ ×2 | 通用行为科学（provenance: general） | 习惯养成、动机与阶段心态——补齐行为心理缺口（knowledge_gaps P2） |
| 2026-09-28 | 代码 | coach/plan.py 重写为槽位式 | 设计书 18.2/20.5（R5） | 硬过滤→默认优先/打分替换→选择理由；伤病同模式替代；P1 排日修复；居家可用 |
