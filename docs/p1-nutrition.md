# P1 交付文档：完整饮食营养系统

> 交付日期：2026-10-25 ｜ 基线：P0（`150ccb9`）｜ 状态：**已交付，验收通过**
> 总纲见 [expert-platform-roadmap.md](expert-platform-roadmap.md)

## 0. 交付范围

P1 只做营养领域：食物库、确定性营养计算、每日饮食管理、营养目标与
营养顾问工作台（MealRecorded → 日常养回顾洞察）。未启动 P2-P7。
一级导航升级为完整的：**今日｜训练｜饮食｜专家｜我的**。

## 1. 修改文件清单

### 后端（新增）

| 文件 | 职责 |
|---|---|
| `coach/nutrition/__init__.py` | 包纪律说明（确定性计算/未知≠0/快照/已记录口径） |
| `coach/nutrition/food_catalog.py` | 内置食物目录（72 条公开参考值约值，含来源声明）+ 自定义食物校验 |
| `coach/nutrition/nutrient_calculator.py` | 确定性计算：份量换算/按参考量缩放/快照构造/汇总（未知项计数） |
| `coach/nutrition/meal_service.py` | 餐次记录/修改/删除/复制日/趋势/常用食物/日版本（漂移锚） |
| `coach/nutrition/target_service.py` | 目标参考估算（Mifflin-St Jeor + 活动系数；只供参考不代填） |
| `coach/nutrition/nutrition_analysis.py` | 营养顾问日回顾分析器（确定性，无 LLM） |
| `test_nutrition.py` | 14 项专项回归 |

### 后端（修改）

| 文件 | 变更 |
|---|---|
| `coach/db.py` | 新增 5 表（foods/meal_entries/nutrition_days/nutrition_targets/nutrition_recipes）及方法 |
| `coach/experts/registry.py` | nutrition 工作台 planned → ready；登记 daily-nutrition-review |
| `coach/experts/task_dispatcher.py` | 幂等键改为输入引用整体摘要（支持 day_version 锚） |
| `coach/experts/insight_service.py` | 漂移检测扩展：饮食日版本 + 营养目标版本 |
| `coach/experts/evidence_validator.py` | source_ids 支持 `meal:ID` 引用 |
| `backend/routes.py` | 新增 17 个营养 API |
| `backend/app.py` | 启动装载内置食物目录 |

### 前端（新增）

| 文件 | 职责 |
|---|---|
| `src/pages/Nutrition.tsx` | 饮食主页：日期导航/已记录汇总 vs 目标/完整标记/四餐次/食谱入口 |
| `src/pages/nutrition/FoodPicker.tsx` | 搜索/分类/我的食物 + 份量单位换算预览 + 自定义录入 |
| `src/pages/nutrition/MealEditor.tsx` | 编辑餐次（份量/单位/餐次/备注/删除） |
| `src/pages/nutrition/RecipeSheet.tsx` | 食谱保存与整餐复用 |
| `src/pages/nutrition/NutritionHistory.tsx` | 7/30/90 天趋势 |
| `src/pages/nutrition/NutritionTargets.tsx` | 目标设置 + 参考估算展示 |
| `src/pages/experts/NutritionExpert.tsx` | 营养顾问工作台（五区） |
| `src/lib/nutrition.ts` + 测试 | 展示工具（未知显示 — 而非 0 等）+ 4 组单测 |

### 前端（修改）

BottomNav/SideNav 加「饮食」；App.tsx 注册 4 条路由；api.ts/types.ts 营养客户端与类型。

## 2. 数据模型与兼容方案

```
foods               id(bi-*/food-*)、user_id(NULL=内置公共)、
                    serving_units[{unit,grams}]、营养六项（NULL=未知）、
                    reference_amount/unit、source_name/license/source_version、
                    verified_status(reference/user_created)
meal_entries        items JSON（MealItem：记录时营养快照 + intake）、
                    local_date/meal_type/notes
nutrition_days      (user_id, local_date) → complete 标记
nutrition_targets   手动目标四项 + preferences/allergies/budget/precision_willing
nutrition_recipes   快照整餐复用
```

老库无损升级（全部 CREATE TABLE IF NOT EXISTS）。**快照纪律**：餐次条目
保存记录时的食物营养值——食物库后续更新不改变历史（有测试断言）。

## 3. 后端 API（17 个）

食物：`GET /nutrition/foods`（搜索/分类/范围，公共+按 uid）；
`GET /nutrition/foods/{id}`；`POST/PUT /users/{uid}/nutrition/foods`（自定义）。
餐次：`GET /users/{uid}/meals?date=`（日汇总）；`POST /users/{uid}/meals`；
`PUT/DELETE /users/{uid}/meals/{id}`；`POST /users/{uid}/meals/copy-day`。
统计：`GET .../nutrition/summary`、`/nutrition/trends?days=`、`/nutrition/frequent`。
目标：`GET/POST .../nutrition/targets`（POST 触发当天重分析）。
天标记：`POST .../nutrition/days/{date}/complete`（触发重分析）。
食谱：`GET/POST .../nutrition/recipes`、`DELETE .../{id}`。

触发链：餐次增删改/完整标记/目标更新 → `_fire_meal_recorded`
（dedup 锚 = local_date + day_version + targets_version）→
MealRecorded → daily-nutrition-review → ExpertInsight。

## 4. 营养分析器（确定性内核）

- 事实四类：已记录能量/蛋白/碳水/脂肪（快照求和；status=observed，
  含未知条目时降级 estimated 并标注 unknown_items）；
- 目标比较（仅目标已设置时）：recorded/target 百分比，未标记完整时
  明示"仅代表已记录部分"；
- 方案规则：永远含「维持记录习惯」；不完整/缺餐次 → 「先把记录补完整」
  （**不完整记录不产生摄入判断**）；完整且与自设目标差 ≥20% →
  「参考方向：可自行调整」（明确由用户决定，持续观察优先）；
- 置信度规则：完整标记 + ≥3 餐次 + 近 14 天 ≥5 天记录 → high；
  ≥2 餐次 → medium；1 餐次 → low（写入 basis）；
- 限制：已记录≠全天、参考约值、未知保留缺失、非医疗处方。

**全程不调用 LLM**（P1 验收"计算结果可复现"由构造保证）。

## 5. 前端交互

- 饮食页：日期切换/复制昨天/四餐次卡片/每餐小计/编辑入口；
  「已记录摄入」四格带目标百分比（无目标显示"未设目标"）；
  完整标记开关（未标记时明示"不代表全天总摄入"）；
- FoodPicker：中文搜索（名称/别名如"地瓜"）/12 分类/我的筛选/份量
  单位换算实时预览（本条能量蛋白…）/自定义录入（未知留空）；
- 营养工作台五区：概览（今日已记录+14 天记录习惯+口径说明）→
  数据（今日明细/任务日志/记录纠错入口）→ 分析（洞察+证据面板，
  source_ids 显示"餐次 #N"）→ 建议（方案取舍/忽略/重新分析）→
  咨询（营养相关咨询历史+主教练入口）。

## 6. 测试与验收

### 自动化

- 后端：`test_nutrition.py` 14 项（搜索与别名/自定义隔离与校验/份量换算
  可复现/未知≠0/编辑更新统计/复制昨日/食谱/趋势/目标/可追溯洞察/
  不完整不判断/high 置信度路径/同日重分析幂等与漂移/删除失效/用户隔离/
  快照存活）；**全量 722 项通过**（含 P0 更新 1 项断言）；
- 前端：tsc 零错误；Vitest 49 项（新增 4）；生产构建通过。

### 真实浏览器端到端（390×844 视口）

1. 饮食页首次进入：四餐次"未记录"+完整标记提示+口径提示；
2. 搜索"鸡蛋"（含别名"地瓜"→红薯验证）→ 选"鸡蛋" → 份量 2 个（50g/个）
   → 预览 144 kcal → 加入早餐；
3. 午餐加米饭 1.5 碗（预览 348 kcal，换算正确）与鸡胸肉 1 块；
4. **发现并修复交互路径**：鸡胸肉误入早餐 → 用"编辑"把整餐改到午餐 →
   三餐归位（编辑/换餐次链路实测通过）；
5. 晚餐米饭 1 碗 → 标记"当天记录完整"；
6. 目标页：BMR 1699/活动系数展示 → 设能量 2200+蛋白 140 → 保存；
7. 营养工作台自动出现洞察：「已记录 883.6 kcal、蛋白 55.8g（3 餐次，
   已标记完整）」；证据面板：能量/蛋白/目标比较 40.2%/39.9% +
   记录习惯；置信度 medium（basis 写明规则）；
8. 建议页两方案（维持观察 / 与目标差距大可自行调整）→ **忽略** →
   "已忽略（历史保留）"；
9. 编辑晚餐米饭 1→2 碗 → 汇总 883.6→1115.6 kcal（40%→51%）实时更新，
   且旧洞察自动失效（day_version 漂移）。

截图：`docs/p1-shots/`（01 三餐汇总 / 02 工作台概览 / 03 方案取舍 /
04 编辑后统计 / 05 趋势 / 06 双工作台中心页）。

### 实际发现并修复的问题

1. 分析器空 data_quality 下标崩溃（任务重试暴露）→ 修复；
2. 同秒洞察排序不稳定 → generated_at 同值时按 rowid 倒序；
3. 完整标记不改变 day_version → 幂等重分析被吞 → 版本纳入 complete 位；
4. 目标保存不触发重分析（目标比较缺失）→ 保存后对当天触发
  `_fire_meal_recorded`（锚含 targets_version）；
5. `add_custom_food` 唯一索引不覆盖"与内置同名"→ 显式查重（含别名场景）。

## 7. 未完成事项与技术限制

1. 扫码/包装 OCR/拍照识别（2.0 §3.2 后续增强，不阻塞）；
2. 常用餐组合复用只做了"食谱→加餐"单入口，"保存常用餐"入口在食谱面板内；
3. 内置目录 72 条为常见参考值约数；品牌级数据依赖用户自录或未来接入
  许可允许的公开数据集；
4. 身体指标联动（体重变化 vs 摄入）属 P2 身体数据模块；
5. 营养 LLM 增强（如饮食方式讨论）仍在主教练咨询链路，工作台为确定性。
