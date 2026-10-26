# P5-B1.1 验收记录：有氧 idle、HIIT 身份与严格契约

> 基线：`60c8a32` ｜ 日期：2026-10-26 ｜ 状态：**通过，可进入 P5-B2**

## 范围

1. 有氧显式 `idle → running → paused → ended`；新增和模板载入不自动开始，旧持久化会话保持原计时状态。
2. HIIT 移除硬编码 `jumping_jack`：已收录动作使用稳定 ID，自定义活动使用 `custom_hiit` 通用身份并独立保存名称；模板载入保持 idle。
3. HIIT 元数据严格一致性：计划轮次=编排总和；完成/跳过不超过计划；未提前结束时必须覆盖全部计划；工作+休息秒数必须等于记录时长。
4. 不一致数据明确告警并丢弃间歇元数据，不再保留看似有效的计划/完成轮次。

## 自动化

```bash
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider --confcutdir=/home/johb/fitness-coach-agent
# 777 passed

cd frontend
npm test   # 11 files / 65 tests passed
npm run build  # tsc + Vite passed

python3 tools/validate.py  # 80 actions passed
```

专项覆盖：

- `frontend/src/components/workout/execution.test.ts`：有氧 idle/开始/暂停/刷新恢复；HIIT idle、稳定/通用身份、轮次、跳过、提前结束、跨阶段确认。
- `frontend/src/store.test.ts`：旧会话无 `status` 时按原时间戳恢复为 running/paused/ended，不重置 startedAt。
- `test_p5b.py`：严格拒绝轮次、完成数、时长、跳过范围不自洽的数据；自定义 HIIT 身份与统计隔离；非法块身份回落并告警；模板身份校验；原离线幂等和纠错回归。

## 真实 Chrome E2E（390×844）

运行：

```bash
# 隔离临时库后端 :18001 + Vite :5173
PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" node tools/e2e_p5b11.mjs
```

| 场景 | 结果 | 截图 |
|---|---|---|
| A 卧推 + 跑步模板；先完成卧推，再开始跑步 | 跑步载入为 `未开始`；卧推完成后才开始计时；实际记录 2 秒，5km 手动补录 | [01](p5b11-shots/01-A-template-bench-running-idle.png) / [02](p5b11-shots/02-A-cardio-finished.png) |
| B HIIT 开始、暂停、刷新、恢复、跳过、提前结束 | 刷新后仍为暂停；完成 0 轮、跳过 1 轮，落库一致 | [04](p5b11-shots/04-B-hiit-paused-after-refresh.png) / [05](p5b11-shots/05-B-hiit-stopped-early.png) |
| C HIIT 模板载入 | 显示 `未开始`，等待 1.6 秒未自动进入工作阶段 | [03](p5b11-shots/03-C-hiit-template-idle.png) |
| D 自定义间歇活动 | 计划/活动名称独立；落库 `exercise_id=custom_hiit`，块名称 `波比跳` | [06](p5b11-shots/06-D-custom-hiit-planner.png) / [07](p5b11-shots/07-D-custom-hiit-result.png) |

E2E 使用系统 Chrome headless + CDP，临时用户和临时数据库，结束自动清理；不读写正式 `data/coach.db`。该验收覆盖真实 DOM、网络、保存与重载，不等同于实体手机锁屏测试。
