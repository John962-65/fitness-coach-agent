# 受控试用与内容验收

本页是操作入口，不是“项目全部完成”的证明。工程测试、原文预核、人工专业审核、真实对话验收和持续使用证据分别记录。

## 1. 接着已有 P1 材料做，不重复预核

已有 `tools/p1_backlog.py`、`tools/p1_precheck_all.py`、`precheck_mid_P1.md` 和合作视频发言者分析继续保留。包含率、AI 精读和“语境归因”只作为审核线索，不自动转换成专业审核通过。

```bash
python3 tools/prepare_review.py
python3 tools/coverage.py
```

审核包放在 **sources/review_packet/**（本地私有，不发布原文片段），默认复用现有 P1 排序的前 12 个动作。`packet.json` 包含原文窗口、视频时间、来源指纹、审核缺口和方法论候选。

`precheck_mid_P1.md` 末尾的 11 条疑问仍应优先处理：前平举/侧平举、反向飞鸟/面拉等动作映射不能凭名称相似强行合并；含混数字需要回看视频。这里不代替人工作出最终结论。

## 2. 两层签核

先核对视频与发言者，再评估适用人群、限制和专业依据。两步都通过且正文没有改变，条目才可供运行时引用。

以下是命令格式，ID、审核者和依据必须填写实际值，不要原样复制占位内容：

```bash
python3 tools/review_ui.py --show <claim_id> --blogger <博主>
python3 tools/review_ui.py --approve <claim_id> --blogger <博主> \
  --stage source --speaker <原片确认的发言者> --by <实际审核者> --note <来源核对依据>
python3 tools/review_ui.py --approve <claim_id> --blogger <博主> \
  --stage applicability --by <实际审核者> --note <适用条件及专业依据>
python3 tools/review_ui.py --apply --blogger <博主>
```

要修正动作映射，可以用 `--edit <claim_id> --exercise-ids <动作ID列表>`；不确定应映射哪个动作时可清空映射，不能随便挂到近似动作。正文、发言者或映射变化会使旧签核失效，需要重新审核。

陈石素材缺口：请提供认可的原始公开视频 URL，或本地 JSON 文字稿（`video/blogger/segments[{start,end,text}]`）。没有原始来源时继续标注第三方整理，不补写不存在的原话或审核记录。

## 3. 离线与真实验收分开

```bash
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider
```

真实验收必须显式指定**共享调用账本**，失败请求也计数，SDK 不自动重试；重跑必须沿用同一账本，不能更换账本规避授权上限。

```bash
python3 eval/runner.py --set pilot --tag design24_real1 \
  --budget-ledger eval/runs/design24_oct04_budget.json --max-calls 50
```

上述 50 次是本轮已经获得的总调用授权，不是每条命令各 50 次。后续要提高额度或开启新一轮预算，需要重新确认。仅使用合成用户，不发送真实健康记录。额度耗尽时报告 `incomplete`，不能当作全部通过。

报告包含代码/数据指纹、实际调用计数、token 用量及逐轮断言结果。旧版本通过率不能代替当前版本验收，也不能只凭输出关键词判断教练效果。

## 4. 连续试用记录（2–4 周）

先由发起人自用，不直接面向陌生用户大规模开放。每天只记录实际发生的事件，不生成虚构的使用天数或成功率：

| 日期 | 发生了什么 | 期望行为 | 实际结果 | 是否需要修正 |
|---|---|---|---|---|
| 待开始 | — | — | — | — |

至少检查：
- 时间从 60 分钟改成 30 分钟后，真实处方是否减少且保留热身/休息。
- 单纯不喜欢某动作，是否能在安全候选中换成偏好动作。
- 没有新信息时，是否保持稳定而不是频繁重排。
- 打卡记错后能否纠正原记录、保留历史，复盘与最佳值是否同步修正。
- 已消失的不适能否明确清除；独立医疗限制不能随之被自动解除。
- 睡眠偏少或疲劳信号上升时，是否避免同时建议加量/加重，并澄清信息是否仍有效。
- 临时时间约束结束后，主动更新档案或请教练重新评估，不能把旧画像当成永久事实。

2–4 周主要验证流程、可执行性与适配，不能单凭短期体重/力量变化证明因果效果。

记录结构见 `trial.example.json`；初始 entries 为空，不代表已经试用。汇总内容、实际验收报告与试用记录：

```bash
python3 tools/trial_status.py --acceptance-report <本轮report.json路径> \
  --trial-file <你实际填写的试用记录.json> --out sources/review_packet/acceptance_status.json
```

不提供试用记录时，省略 `--trial-file`，工具会明确报告缺少持续使用证据；它不会连接真实用户数据库。

## 5. 视频验收仍需真实标注

视频反馈仍按实验功能对待，样例清单格式见 `video_acceptance.example.json`。准备有拍摄角度、体型、遮挡、动作变式信息的真实样例；由合适人员标注“能判断什么、不能判断什么”及预期结果。没有标注时不计算准确率；低质量视频应允许拒绝判断。

合成关键点测试、一次真机冒烟不等于真实动作纠错已可靠。手机界面和视频正式接入仍遵循 DESIGN 第24章的验收顺序，不能用界面完成度替代专业审核和实际试用。
