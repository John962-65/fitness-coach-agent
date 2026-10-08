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
| 2026-10-04 | claims | claims/tcy.yaml 967→1396 | 谭成义 11 个新视频（R7） | 腹肌/器械/手臂/下肢臀部/居家×2/腿训/上肢关节调整/腰部不适/手臂安排；全部 draft 待审 |
| 2026-10-04 | claims | claims/ksw.yaml 346→649 | 凯圣王 9 个新视频（R7） | RM/RPE/RPE代入/组间休息/坐姿器械推胸/箭步蹲/臀冲/V字俯卧撑/女性力量训练①；全部 draft 待审 |
| 2026-10-04 | 修正 | tools/distill.py + 全部 claims 补 speaker | 修复意见 第8条 | 落盘时 speaker 字段曾丢失：distill 补写（LLM 未判出则"待确认"）；存量 2021 条回填 speaker=待确认，审核时对照原片确认 |
| 2026-10-04 | 基础设施 | sources/manifest/{谭成义,凯圣王}.yaml + tools/batch_distill_r7.py + coverage.md 刷新 | 设计书 21.4 覆盖率驱动 | 待补博主来源动作 24→11；凯圣王空间 100 条清单已枚举（sources/manifest/ksw_space.txt）；陈石公开一手渠道仍未找到（营养矩阵为付费课，搬运不采） |

| 2026-10-05 | claims | claims/cs.yaml 0→285 | 陈石官方B站（uid 364281292）首批 18 个视频 | 浏览器核实"B站唯一本人号"；慢减脂/GI/蛋白质/睡眠/皮质醇/行为全部 draft 待审；付费课盗版合集不采 |
| 2026-10-05 | claims | claims/ksw.yaml +569 / claims/tcy.yaml +58 | R7c 补缺口 13 个视频（浏览器定位老"详解"系列） | 倒蹬/T杆划船/引体/侧平举变式/核心技能包/家庭私教课等；待补动作 11→6，余 6 个为变式级映射决策 |
| 2026-10-05 | claims | 全库 2899→3922（CS 581 / KSW 1655 / TCY 1686） | R7d 第三波 38 个视频 | 陈石补剂/糖/酒精/女性/运动时间；凯圣王新手一分化/二分化带练/FMS筛查/女性系列/宏量营养/睡眠；谭成义拉伸/泡沫轴/肩痛/体态；待补动作 6→3（早安式/上斜俯卧撑/负重引体，均为变式级映射决策） |
| 2026-10-05 | 基础设施 | fetch_transcript.py 枚举上限 100→200；三博主空间全量清单入库 | 设计书 19.2① | TCY 187 全量 / KSW 200 / CS 140；谭成义"焚决系列"教学为下一批候选 |
| 2026-10-05 | 整改 | claims/tcy.yaml ×10、claims/cs.yaml ×1、tools/distill.py、test_knowledge.py | KNOWLEDGE_AUDIT_2026-10-05 第7节第一轮 | K-A02 错配修复（回归锁死）/ K-A03 改有条件研究发现 / K-A01 提炼契约（只填原文明确条件）/ K-A04~A06 入 50 条待审队列与 conflicts 台账；维护基础设施 sources/maintenance/ 就位；本轮零付费调用 |
| 2026-10-06 | claims | 全库 3922→4416（TCY 1897 / KSW 1881 / CS 638） | CB26 收集批次 18 个视频（账本 40/40） | 发起人指示收集优先、vlog/备赛纳入：TCY 焚决/器械教学+47min训练vlog、KSW 口袋教练余下各期、CS 代谢抗阻/江南饮食/肠道营养；全部 draft 待审 |
| 2026-10-06 | claims | 全库 4416→5034（TCY 2192 / KSW 2116 / CS 726） | CB26b 续批 19 个视频（账本 40/40） | TCY 胸/肩/背/手臂跟练系列、KSW 口袋10/大剪刀/器械技巧/透视④/功能筛查①/睾酮详解、CS 肌酸补脑/极速减肥/冷水浴/空腹训练/Omega-6；BV192Nwz4E9n 无 AI 字幕 whisper 0 收，标注待人工看片 |
| 2026-10-06 | claims | 全库 5034→5602（TCY 2359 / KSW 2404 / CS 839） | CB27 批 19 个视频（账本 40/40） | TCY 未知长视频×3（干货30min/啰嗦24min/25min）+饮食记录胸部细节+背部功能；KSW 透视①②/马格南/下斜卧推/Newtech高位下拉/卧推③计划⑩饮食/功能筛查②；CS ISSN抗氧化①/水果果糖/美国膳食指南/护肝/体脂秤/抽筋；全部 draft 待审 |
| 2026-10-06 | claims | 全库 5602→6014（TCY 2470 / KSW 2600 / CS 944） | CB28 批 19 个视频（账本 38/40，跳过1个纯音乐vlog） | TCY 胸部教学上下/肩部教学/日常训练/训练日/16分钟干货；KSW 卧推⑫⑬⑯/双杠臂屈伸⑮/功能筛查③④/女性②抗衰（59条本批最高产）；CS ISSN抗氧化②/姜黄素/Mind饮食/睡眠果汁/耐力补糖/酵母蛋白；全部 draft 待审 |
| 2026-10-06 | 机制 | coach/cards.py + test_cards.py + sources/maintenance/{cards/,card_review_queue.json,quarantined.json,cards_catalog.json} | 任务书 §12 减负修订 | 核心卡机制（版本指纹/审批范围/用途隔离/批量上限）7 项测试；14 条高风险隔离；20 卡目录；首批 5 张动作/训练卡（每卡绑定6条 claim 指纹+原文出处）+3 个待决问题提交发起人；底层 claims 全部保持 draft |
| 2026-10-06 | 修正 | claims/ksw.yaml ×27 + test_knowledge.py | K-A02 同类新发现 | 《New tech下斜卧推》27条错挂 incline_bench_press（上斜≠下斜），取消映射并回归锁死；库内暂无下斜动作，待建归档 |
| 2026-10-06 | 机制 | tools/card_review.py + 下一批 5 张动作卡 | 卡片M2 | 三问裁决落档（机制启用/口径处理认可/先补动作卡）；审批 CLI（--approve/--return 必附审核者与依据，不改 claims）；上斜/坐姿划船/硬拉/推举/杠铃划船卡备好，首批审完即推 |
| 2026-10-07 | 修正 | claims/ksw.yaml ×21 + test_knowledge.py | K-A02 同类② | 《倒蹬详解》21条统一挂 leg_press（19条原未挂、2条错挂深蹲/高脚杯——引用标准≠教学对象），回归锁死 |
| 2026-10-07 | claims+卡 | claims/ksw.yaml +10（BV1iQ4y1e7YL 深蹲详解，账本 2/8）+ 3 张动作卡 | 卡片M3 | 首批5卡全部approved；第2批5卡推送；深蹲/倒蹬/引体卡备好（20张动作卡全部完成起草）；目录 weighted_pull_up→pull_up |
| 2026-10-07 | 卡 | 第2批5卡approved；第3批5卡推送（深蹲/倒蹬/引体/目标时间取舍/进阶调整） | 卡片M4 | 累计批准10/20；全部卡绑定指纹校验一致；剩恢复执行+4营养卡后20卡齐 |
| 2026-10-07 | 卡 | 第3批5卡approved；第4批5卡推送（恢复执行+能量/蛋白质/习惯/睡眠） | 卡片M5 | 20张核心卡全部起草完成；累计批准15/20；绑定指纹全库一致 |
| 2026-10-07 | 卡 | card-nutrition-protein-basics v2 + conflicts.json conf-2026-1007-01 + claims/ksw.yaml +12 | 发起人要求核查三位博主蛋白质内容 | 全库181条/33视频盘点；发现新手vs老手蛋白质需求真冲突（陈石引ISSN 1.6-2.0 vs 凯圣王'新手少吃'），卡v2三方并列不自动裁决；补抓《增肌饮食误区》12条 |
| 2026-10-07 | 卡 | card-nutrition-protein-basics v2 + conflicts.json conf-2026-1007-01 + claims/ksw.yaml +12 | 发起人要求核查三位博主蛋白质内容 | 全库181条/33视频盘点；发现新手vs老手蛋白质需求真冲突（陈石引ISSN 1.6-2.0 vs 凯圣王'新手少吃'），卡v2三方并列不自动裁决；补抓《增肌饮食误区》12条零标红 |
| 2026-10-07 | 里程碑 | 20/20 核心卡全部批准 | 卡片M6（第4批5卡approved） | 12动作+4训练+4营养；绑定120条claim指纹全部一致；隔离区14条未上线；运行时接入为下一步 |
| 2026-10-07 | 运行时 | coach/cards.py 运行时层 + coach/agent.py 接线 + test_cards_runtime.py | 任务书 §12 第四层 | 20张已批卡进入教练工具链：动作教学卡优先、get_coaching_card 主题路由；仅服务审批有效卡、用途受限、出处留痕；292 项测试全绿 |
