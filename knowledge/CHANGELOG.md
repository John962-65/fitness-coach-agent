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
| 2026-10-09 | 卡 | sources/maintenance/cards/card-action-face_pull.json +review(approved_v1) + card_review_queue.json / cards_catalog.json / state.json / budgets/collection_batch_20261009.json / runs/maint_20261009_handover.json | ZCODE 任务交接 opencode 首轮（发起人 2026-10-09 原话「q8和q9,面拉卡都通过」） | 面拉卡 v1 批准（14 条绑定指纹复验一致、无隔离条目）；Q8 通过=现在过一遍 31 条发言者归属（清单 5 视频，纠正原 3 视频说法）；Q9 通过=授权 6 次 LLM 调用；账本 0/6；catalog 补至 24 张；claims 快照对齐 6354 全 draft；零付费调用、未动 git；test_cards_runtime.py 2 处对照样例更新（face_pull→barbell_curl）；302 passed"
| 2026-10-09 | 确认 | claims/tcy.yaml ×27、claims/ksw.yaml ×4 | Q8（发起人「1确认」） | 腿弯举12+提踵19 共31条 speaker 由「待确认」改为记录归属+「（发起人 2026-10-09 确认归属）」留痕；全量31条核对清单 p1_speaker_sheet_20261009.md（原10-08清单每视频只列前4条，工具 tools/q8_speaker_sheet_full.py 补全） |
| 2026-10-09 | 建库 | exercises/{lateral_band_walk,bent_over_triceps_extension,seated_cable_curl}.yaml + claims/tcy.yaml ×18 | 发起人「2建库」「3新建」 | 3 个新动作（draft，joint_stress pending）；9 条 K-A02 错挂证据 + 9 条 barbell_curl 误挂重挂新 id；BV1ND5S6pEgx-0009/0010 经字幕上下文核对并入 seated_cable_curl；BV1wvMF6ZEqL-0010 保留 cable_pushdown 双映射；动作库 61→64，校验通过 |
| 2026-10-09 | 卡 | sources/maintenance/cards/{card-action-lying_leg_curl,card-action-standing_calf_raise}.json + card_review_queue.json | Q8 确认后出卡 | 腿弯举卡绑12条/正文343字、提踵卡绑19条/正文401字；组次分歧并列保留不裁决；「第二心脏/改善血糖」等原话类比说法只入 limits 不作医疗结论；queue 重建为 2 卡 + Q10-Q12 三问 |
| 2026-10-09 | 选片 | sources/transcripts ×10 + sources/manifest/{tcy,cs}_space.txt + fetch_log.jsonl | Q9（发起人「4选片」） | 免费抓取并扫描 10 个候选视频字幕（KSW 三分化④⑥/背部计划、TCY 居家背/焚决/背部教学/新视频）：负重引体内容 0 命中；6 次额度账本 collection_batch_20261009 留存 0/6；登记 TCY BV18ypx6mE6m（10-09 发布）、CS BV1WApM6XEaY（10-07 发布） |
| 2026-10-09 | 卡 | sources/maintenance/cards/{card-action-lying_leg_curl,card-action-standing_calf_raise}.json | Q10（发起人「Q10通过」） | 两卡 approved_v1（绑定 12+19 条，批准前指纹复验一致）；运行时服务卡 24→26 |
| 2026-10-09 | 确认 | claims/tcy.yaml ×14 | Q11（发起人「Q11确认」） | 3 个新动作相关 14 条 speaker 改为记录归属+留痕（原问题写 11 条为笔误，已在队列记录更正；BV1MvwxzGEio×4/BV1ND5S6pEgx×2/BV1pZiZBxE8y×5/BV1wvMF6ZEqL×3） |
| 2026-10-09 | 卡 | sources/maintenance/cards/{card-action-lateral_band_walk,card-action-bent_over_triceps_extension,card-action-seated_cable_curl}.json + card_review_queue.json | Q11 确认后出卡 | 3 张新动作教学卡 prepared（绑定 5+4+9 条）；队列改为 3 卡 + Q12/Q13 两问 |
| 2026-10-09 | 选片 | claims/ksw.yaml +5（BV1aqsXeRE2B 窗口）+ budgets/collection_batch_20261009.json 6/6 | Q9 选项 a（负重引体全量扫描） | TCY+KSW 226 个新抓字幕、85 个无字幕跳过；唯一命中 BV1aqsXeRE2B t≈197 负重引体说法，但出自三人对谈、说话人以'凯哥'称呼凯圣王（非本人），5 条 draft speaker 全待确认不可引用；缺口未闭合，处置选项在 state.json |
| 2026-10-09 | 卡 | sources/maintenance/cards/{card-action-lateral_band_walk,card-action-bent_over_triceps_extension,card-action-seated_cable_curl}.json | Q13（发起人「通过」） | 三卡 approved_v1（绑定 5+4+9，指纹复验一致）；Q12 joint_stress 按「设计书保持不动」维持 pending；运行时服务卡 26→29，全库 29 张全部审批有效 |
| 2026-10-10 | 修正 | claims/tcy.yaml ×7、claims/ksw.yaml ×7 | K-A02 同类新发现（P1 收尾批选片时发现） | BV1FL2MBME3G（肩后束热身视频）7 条外旋激活内容解除 dumbbell_bench_press 错挂；BV1we4y1J72N 的 T 杆深蹲 7 条解除 t_bar_row 错挂；待建 t_bar_squat / lying_db_external_rotation 登记（回归未加测试——映射为空不触发旧断言，待建卡时补） |
| 2026-10-10 | 卡 | sources/maintenance/cards/{card-action-barbell_curl,card-action-dumbbell_bench_press,card-action-t_bar_row,card-action-pec_deck,card-action-push_up}.json + card_review_queue.json | P1 收尾与槽位替换批 | barbell_curl 补 PPL 拉日最后一个 P1 空槽；4 张槽位实际处方/替换动作卡；89 条绑定全部 speaker 已确认、指纹复验一致；分歧处并列保留（直杆/曲杆、哑铃平板新手态度）；队列 5 卡 + Q14/Q15 |
| 2026-10-10 | 卡 | sources/maintenance/cards/{barbell_curl,dumbbell_bench_press,t_bar_row,pec_deck,push_up}.json | Q14（发起人「q14签约通过」） | 5 卡 approved_v1（89 条绑定复验一致）；运行时服务卡 29→34；P1 17 槽位 16 个有卡（weighted_pull_up 无素材） |
| 2026-10-10 | 测试 | test_cards_runtime.py | Q14 后测试规格同步 | 无卡对照样例 barbell_curl→dumbbell_row（杠铃弯举卡已获批），正面断言其被服务；302 passed
| 2026-10-10 | 卡 | sources/maintenance/cards/{dumbbell_row,cable_pushdown,hanging_leg_raise,cable_fly,cable_lateral_raise}.json + card_review_queue.json | P1 后槽位替换批 2 | 按周计划覆盖与互补选片（背/三头/核心/胸-绳索/肩-绳索），82 条绑定全部 speaker 已确认；直臂下压经字幕核对为谭成义三头课直杆变式；队列 5 卡 + Q16/Q17 |
| 2026-10-11 | 卡 | 5 张动作卡 approved_v1（dumbbell_row/cable_pushdown/hanging_leg_raise/cable_fly/cable_lateral_raise）+ cards_catalog.json + state.json | Q16（发起人对话原话「q16通过」） | 批准前复验 82 条绑定指纹一致、引文命中原文、无隔离条目；运行时服务卡 34→39，全库 39 张全部审批有效；catalog 按磁盘实际重建为 42 张（此前停在 24 张） |
| 2026-10-11 | 建库 | exercises/{t_bar_squat,lying_db_external_rotation}.yaml + claims/ksw.yaml ×6 + claims/tcy.yaml ×7 | Q15（发起人对话原话「q15登记啊继续」） | 两动作建库（draft，joint_stress pending，占位值 provenance 标注 pending）；13 条错挂解除后的 claims 重挂新 id 并清除重复键残行（ksw 6 条→t_bar_squat、tcy 7 条→lying_db_external_rotation）；动作库 64→66，validate 通过 |
| 2026-10-11 | 卡 | sources/maintenance/cards/{card-training-cardio-basics,card-nutrition-alcohol,card-nutrition-supplements}.json + coach/cards.py 主题路由 + test_cards_runtime.py + card_review_queue.json | Q17 方向②（发起人对话原话「q17选择方向2」） | 首批 3 张训练/营养主题卡 prepared：有氧 23 绑定（凯圣王6/谭成义9/陈石8）、饮酒 20（陈石17/凯圣王3）、补剂 18（凯圣王7/谭成义7/陈石4）；全部引文命中原文、无 FLAGGED、无隔离条目；口径分歧（有氧强度与空腹、深睡眠影响、肌酸剂量时机）一律并列保留；候选中 2 条 FLAGGED 从严剔除；减脂平台期仅 2 条、停训复训仅 1 条不足以出卡（缺口提交 Q19）；测试对照样例 dumbbell_row→leg_extension、新增方向②路由测试；303 passed |
| 2026-10-11 | 卡 | 3 张主题卡 approved_v1（card-training-cardio-basics/card-nutrition-alcohol/card-nutrition-supplements）+ test_cards_runtime.py | Q18（发起人对话原话「q18通过」） | 批准前复验 61 条绑定指纹一致、引文命中、无隔离、无 FLAGGED；运行时服务卡 39→42，主题路由三卡生效；测试对照样例 leg_extension→back_extension（腿屈伸卡进新批） |
| 2026-10-11 | 采集 | sources/maintenance/runs/q19_theme_scan_{hits.json,status.jsonl,log} + tools/sweep_q19_themes.py + state.json collection_gaps | Q19（发起人对话原话「q19继续采集」，选项①登记缺口） | 本地存量字幕扫描：平台期 34 处/13 视频（BV1uuhV6YEGW t≈110/1085s 等未提炼段落）、停训复训 12 处/7 视频；补抓三空间剩余未抓视频 84 个（9 抓到字幕/75 无字幕），新抓对两主题零命中——缺口在字幕层面成立；提炼需额度未动用（账本 6/6 用尽） |
| 2026-10-11 | 修正 | claims/tcy.yaml ×6、claims/ksw.yaml ×5 | K-A02 同类（出卡前映射核查发现） | tcy-BV1utntzhE9a-0008~0013 俯身哑铃飞鸟由 dumbbell_fly 重挂 rear_delt_fly（库内有正主）；ksw-BV1MG4y1G76W 地面卷腹 5 条解除 cable_crunch 错挂（其中 0052 连挂的 hanging_leg_raise 一并清除），crunch 建库提案入队列 Q21 |
| 2026-10-11 | 卡 | sources/maintenance/cards/{card-action-t_bar_squat,card-action-lying_db_external_rotation,card-action-leg_extension,card-action-dumbbell_fly,card-action-cable_crunch}.json + tools/_p1_batch7_20261011.py + card_review_queue.json | Q18 后批 | 5 卡 prepared（绑定 6+7+10+25+7=55，全部 speaker 已确认、无 FLAGGED、无隔离）；构建脚本新增「绑定必须真的映射到本动作」检查；back_extension 素材池混正向/反向两种用法未出卡（待拆分）；队列 5 卡 + Q20/Q21 |
| 2026-10-11 | 测试 | test_exercises.py | 重挂回归（10-10 欠账补上） | 新增 test_claim_remap_after_k_a02_unmapping：13+2 处映射期望锁死（行级扫描不解析全量 YAML）；304 passed |
| 2026-10-11 | 卡 | 5 张动作卡 approved_v1（t_bar_squat/lying_db_external_rotation/leg_extension/dumbbell_fly/cable_crunch）+ test_cards_runtime.py | Q20（发起人对话原话「q20通过」） | 批准前复验 55 条绑定指纹一致、引文命中、无隔离、无 FLAGGED、映射一致；运行时服务卡 42→47 |
| 2026-10-11 | 建库 | exercises/crunch.yaml + claims/ksw.yaml ×5 + test_exercises.py 期望更新 | Q21（发起人对话原话「q21建库」） | crunch（地面卷腹，自重）建库 draft，joint_stress pending；命名避开单用「卷腹」防与绳索卷腹归一混淆；5 条地面卷腹 claims 重挂 crunch；动作库 66→67，validate 通过 |
| 2026-10-11 | 卡 | sources/maintenance/cards/{card-action-rear_delt_fly,card-action-machine_shoulder_press,card-action-chest_supported_row,card-action-hip_thrust}.json + tools/_p1_batch8_20261011.py + card_review_queue.json | Q20/Q21 后批 | 4 卡 prepared（绑定 20+6+8+6=40，全部 speaker 已确认、无隔离、映射一致）；2 条 FLAGGED 与周期敏感条目（卵泡期）从严剔除；machine_chest_press 因素材薄且与 pec_deck 卡绑定重叠放弃；队列 4 卡 + Q22 |
| 2026-10-12 | 卡 | 4 张动作卡 approved_v1（rear_delt_fly/machine_shoulder_press/chest_supported_row/hip_thrust）+ test_cards_runtime.py | Q22（发起人对话原话「q22通过」） | 批准前复验 40 条绑定指纹一致、引文命中、无隔离、无 FLAGGED、映射一致；运行时服务卡 47→51 |
| 2026-10-12 | 建库 | exercises/reverse_back_extension.yaml + exercises/back_extension.yaml 拆分注记 + claims/tcy.yaml ×15 | 发起人裁定「拆成两个动作」 | 反向山羊挺身（练腹）自 back_extension 拆出建库 draft，15 条谭成义反向 claims 改挂，back_extension 保留正向练竖脊肌（凯圣王素材）并在 provenance 记拆分；动作库 67→68，validate 通过 |
| 2026-10-12 | 修正 | claims/ksw.yaml ×1、claims/tcy.yaml ×3 | K-A02 同类（下一批摸底发现） | ksw 俯身臂屈伸技巧 1 条由 skull_crusher 重挂 bent_over_triceps_extension；tcy 反手杠铃臂屈伸 3 条由 close_grip_bench_press 重挂 skull_crusher（均库内有正主） |
| 2026-10-12 | 卡 | sources/maintenance/cards/{card-action-reverse_back_extension,card-action-knee_push_up}.json + tools/_p1_batch9_20261012.py + test_exercises.py + card_review_queue.json | 拆分后出卡批 | 2 卡 prepared（绑定 12+7=19，全部 speaker 已确认、无隔离、映射一致；反向卡 3 条 FLAGGED 未纳入）；band_pull_apart 素材与定义有出入暂缓出卡待映射复核；队列 2 卡 + Q23 |
| 2026-10-12 | 卡 | 2 张动作卡 approved_v1（reverse_back_extension/knee_push_up）+ test_cards_runtime.py | Q23（发起人对话原话「通过」） | 批准前复验 19 条绑定指纹一致、引文命中、无隔离、无 FLAGGED、映射一致；运行时服务卡 51→53 |
| 2026-10-12 | 卡 | sources/maintenance/cards/{card-action-crunch,card-action-skull_crusher,card-action-front_squat}.json + tools/_p1_batch10_20261012.py + card_review_queue.json | 清尾批 | 3 卡 prepared（绑定 5+7+5=17，全部 speaker 已确认、无隔离、映射一致）；出完本批已提炼素材的干净池清空，剩余候选 <5 条或混池（bodyweight_squat/band_pull_apart 待映射复核）；队列 3 卡 + Q24 |
| 2026-10-12 | 修正 | claims/ksw.yaml ×7、claims/tcy.yaml ×9、claims/cs.yaml ×3 + state.json | 发起人指示「混池复核」 | bodyweight_squat 7→1：筛查2条解除（overhead_squat_screen 提案）、血糖/代谢课表/Cindy 4条解除（非动作教学）、深蹲后脚跟1条已绑深蹲卡冻结待重签；band_pull_apart 16→3：凯圣王俯身弹力带肩胛训练3条保留、谭成义上回旋/后倾4条解除（band_scapular_upward_rotation 提案）、待确认speaker绕肩/外旋/死虫/旋后等9条解除 |
| 2026-10-12 | 采集 | sources/maintenance/runs/thin_material_scan_hits.json + state.json thin_material_scan | 发起人指示「素材薄的继续收集」 | 免费扫描全部本地字幕 8 个薄动作：约 114 个候选窗口（cable_row 26/plank 25/back_extension 22/close_grip 16/hack_squat 11 等）；字幕已全量抓取，下一步仅剩提炼，需新采集账本（Q26，cb29 剩 2 次授权范围不符不挪用） |
| 2026-10-12 | 提炼 | claims/cs.yaml ×4 + claims/ksw.yaml ×18 + runs/zcode_distill_20261012.json | 发起人问「提炼你不能提炼吗」→ 开启 zcode 直提线 | 首批平台期/停训复训 22 条：cs 4 条（diet break/停训休息，speaker=陈石可引用级）、ksw 18 条（对谈 speaker 待确认，进卡需归属确认）；两遍法自校验，1 条 ASR 噪声归一化按纪律标 FLAGGED；全部 draft、零 API 费用、不动账本；304 passed |
| 2026-10-12 | 卡 | 3 张清尾卡 approved_v1（crunch/skull_crusher/front_squat）+ test_cards_runtime.py | Q24（发起人对话原话「24通过」） | 复验 17 条绑定一致；运行时服务卡 53→56，队列清空（56 张全部审批有效） |
| 2026-10-12 | 建库 | exercises/{overhead_squat_screen,band_scapular_upward_rotation}.yaml + claims ×6 | Q25（发起人对话原话「25建库」） | 两动作 draft 入库（70 动作 validate 通过），筛查/上回旋 claims 各自改挂 |
| 2026-10-12 | 提炼 | claims/ksw.yaml ×5 + claims/tcy.yaml ×5 + 4 条存量重挂 + runs/zcode_distill_20261012.json batch2 | Q26（发起人对话原话「26直提」） | 关键修正：关键词扫描 114 窗口经 ts 对照存量 claims 去重后仅 65 处真未提炼；本轮 10 条新提炼（窄推vs仰卧臂屈伸/自重蹲局限/肘撑肩胛/拉锯平板/锤式弯举/坐姿划船窄宽距）+4 条已提炼山羊挺身存量补挂 back_extension；镜像/器械介绍/合集重复窗口登记跳过；304 passed |
| 2026-10-12 | 审核 | sources/review_packet/speaker_confirmation_sheet_20261012.md（35 条/13 组） | Q27①（发起人对话原话「确认解锁」） | 出卡线阻塞条目的归属确认清单：每条带跳转点与前置交接词线索，按视频分组；确认后解锁 back_extension 正向卡、平台期/停训复训主题卡、close_grip/skull_crusher 增量 |
| 2026-10-12 | 审核 | claims/ksw.yaml ×26 + claims/tcy.yaml ×4 speaker 留痕 | Q27（发起人对话原话「确认」） | 13 组/35 条清单按组批量确认：30 条落「凯圣王/谭成义（发起人 2026-10-12 确认归属）」；组7（BV1aqsXeRE2B 5 条）因 Q9 已判说话人非本人、整批确认无法回答实际归属，维持不可引用 |
| 2026-10-12 | 卡 | sources/maintenance/cards/{card-action-back_extension,card-training-layoff-comeback,card-training-fat-loss-plateau}.json + coach/cards.py 主题路由 + tools/_p1_batch11_20261012.py + card_review_queue.json | 归属确认后解锁批 | 3 卡 prepared（绑定 10+8+13=31，全部为已确认归属素材、无隔离）；tcy-0261（FLAGGED）从严剔除；两张主题卡兑现 Q19 登记的减脂平台期/停训复训缺口；主题路由新增两条（避开 progression 的「平台期」与 energy 的「减脂」关键词碰撞）；队列 3 卡 + Q28 |
| 2026-10-12 | 卡 | 3 张解锁卡 approved_v1（back_extension/layoff-comeback/fat-loss-plateau）+ test_cards_runtime.py + card_review_queue.json | Q28（发起人对话原话「28通过」） | 复验 31 条绑定一致；运行时服务卡 56→59，队列清空；back_extension 正向卡=拆分裁定收尾；对照样例 back_extension→plank；组7（BV1aqsXeRE2B 5 条）内容已展示、待发起人指认对谈嘉宾归属 |
| 2026-10-12 | 裁定 | state.json speaker_confirmation.group7_decision | 发起人对话原话「不管那个人」 | BV1aqsXeRE2B 5 条永久搁置、不指认归属，维持不可引用；weighted_pull_up 接受为长期素材缺口（未来采集命中本人 solo 视频再启用） |
| 2026-10-12 | 裁定 | claims/ksw.yaml ×5 speaker + state.json | 发起人确认「组7那个是别人,一个陌生人」 | BV1aqsXeRE2B 该段说话人为陌生对谈嘉宾、非三位博主；speaker 改「未知对谈嘉宾（发起人 2026-10-12 确认非三位博主本人）」，source_issues 机械拦截永不进卡；weighted_pull_up 唯一候选素材就此排除，缺口为长期状态（未来采集命中博主本人 solo 视频再议） |
