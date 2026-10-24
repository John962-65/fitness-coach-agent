# Fitness Coach 2.0 — UI/UX 全面改版交付说明

日期：2026-10-24 · 范围：`frontend/`（纯前端改版，后端零改动）

## 一、视觉设计规范

### 1. 设计变量（唯一来源：`tailwind.config.js` + `index.css`，页面禁止另行定义颜色）

| Token | 值 | 用途 |
| --- | --- | --- |
| `canvas` | `#F6F7F3` | 应用主背景（暖白） |
| `surface` | `#FFFFFF` | 卡片/输入框/导航表面 |
| `night` | `#18251D` | 深色表面：今日主视觉卡、侧栏、训练执行顶栏、休息计时条 |
| `ink` | `#17231B` | 主文字 |
| `muted` | `#68756D` | 次级文字（对白底 4.8:1，≥AA） |
| `faint` | `#98A49C` | 三级辅助信息（时间戳等） |
| `line` / `lineStrong` | `#E7EBE5` / `#D6DDD4` | 边框/分割线 |
| `accent` | `#B8EE70` | 品牌青柠：主按钮、激活态、进度 |
| `accent-dim` / `accent-soft` / `accent-deep` | `#A3DD57` / `#EFFADF` / `#3D5A26` | 按压态 / 浅底 / 深底上的可读强调文字 |

对比度已验证：`ink` on `accent` ≈ 12.2:1；`accent` on `night` ≈ 11.8:1；`white` on `night` ≈ 15.9:1。

### 2. 基础规则
- 字体：系统栈（PingFang SC / Microsoft YaHei 等）；正文基准 15px，正文最小 14px，辅助标签 12–13px；数据一律 `.nums` 等宽数字。
- 圆角：卡片 `18px`、按钮/输入 `14px`、标签全圆。
- 阴影：`shadow-card`（轻）与 `shadow-pop`（悬浮/弹层）两级。
- 点击区：`.btn`/`.input` 最小高度 44px；图标按钮 ≥36px；底部导航格高 56px。
- 动画：仅 3 组轻量 keyframes（fade-up / sheet-up / pulse-soft 骨架）；`prefers-reduced-motion` 下全部瞬时。
- 语义状态色沿用 Tailwind 调色板：安全警告=红（`ErrorBox`/红色 2px 边框卡）、提醒=琥珀、信息=蓝、品牌提示=青柠软底。

### 3. 组件体系（`components/Bits.tsx` 为唯一入口）
`Card` / `CardNight` / `Tag` / `Button`（primary·night·ghost·soft·danger）/ `PlainButton` / `Field` / `Input`（forwardRef）/ `Textarea` / `Select` / `ErrorBox` / `Notice` / `Empty` / `Spinner` / `Skeleton` / `PageHeader` / `SubHeader`（次级页返回栏）/ `SectionLabel` / `Stat` / `ProgressBar` / `Segmented` / `Chip` / `Sheet`（移动底部抽屉+桌面居中对话框，滚动锁定/Esc） / `SuccessBlock`。
媒体组件：`components/media.tsx`（短时签名 URL 含过期预刷新、`ExerciseCover`、`CoverPlaceholder` 统一占位视觉）。

## 二、文件清单

### 新增
| 文件 | 说明 |
| --- | --- |
| `src/components/SideNav.tsx` | 桌面侧边栏（lg+），与底栏同一信息架构 |
| `src/components/media.tsx` | 签名媒体 URL（TTL 缓存）、动作封面 Hook、统一占位封面 |
| `src/pages/ExploreDetail.tsx` | 动作详情独立页（教学/动作分析/知识依据 三标签） |
| `src/pages/MineApproach.tsx` | 训练方式编辑与版本历史（次级页） |
| `src/pages/MineSettings.tsx` | 高级设置与数据管理（次级页） |
| `docs/redesign-shots/*.png` | 四档尺寸实拍截图 |

### 重写
`tailwind.config.js`、`src/index.css`、`src/components/Bits.tsx`、`src/components/BottomNav.tsx`、`src/App.tsx`、`src/pages/Today.tsx`、`Training.tsx`、`Workout.tsx`、`Coach.tsx`、`Explore.tsx`、`Mine.tsx`、`History.tsx`、`PlanEditor.tsx`、`Onboarding.tsx`、`components/ExercisePicker.tsx`、`components/KnowledgePanel.tsx`

### 微调
`index.html` / `manifest.webmanifest` / `icon.svg`（主题色 `#F6F7F3` + 新品牌图标）、`public/sw.js`（缓存版本 v10→v11）、`vite.config.ts`（代理目标支持 `FC_API_TARGET` 覆盖，默认 8000 不变）

### 未改动
`api.ts`、`offline.ts`、`store.ts`、`types.ts`、`lib/protocol.ts` 及全部后端代码。

## 三、整体布局

- **移动端**：底部五栏导航（今日/训练/AI 教练/探索/我的），Lucide 图标 + 顶部指示条，`env(safe-area-inset-bottom)` 兼容；Emoji 全部替换。
- **桌面端（≥1024px）**：左侧 240px 固定侧栏（品牌区/主导航/训练历史/设置/当前用户），内容区 `max-w-3xl~5xl` 多列布局（今日=主列+侧栏列、教练=对话+提案/咨询双栏、探索=3 列卡片网格）。**不再有 512px 单列限制。**
- **训练执行 `/workout/:day`**：完全沉浸式——无侧栏/底栏，深色吸顶栏（返回+进度+休息倒计时章），固定底部完成条。

## 四、各页面改版前后差异

| 页面 | 改版前 | 改版后 |
| --- | --- | --- |
| **Today** | 均质灰卡列表（PageHeader+Card 堆叠） | 问候语+日期头 → **深色主视觉卡**（今日训练/继续训练+动作预览+大 CTA）→ 本周训练（7 日条+进度）→ 三指标块 → AI 教练快捷入口；安全隔离改为 2px 红框卡；桌面双栏 |
| **Training** | 每天一张卡纵向排列 | 训练日横向切换 chips（今天带点标）→ 单日详情卡：**封面缩略图+名称+组×次×重量**、教学链接；版本历史/备注收纳；编辑入口入页头 |
| **PlanEditor** | 旧样式表单 | 同一逻辑（草稿+协议+乐观锁）换新视觉：图标化排序/替换/删除、SubHeader 返回 |
| **Workout** | 挤在一行的 kg/次/RPE 小输入 | 沉浸式：深色吸顶头（进度实时）、动作卡（大标题/教学/目标行）、**组记录表**、48px 大输入区、热身独立 chip、**可展开 RPE**、完成组大按钮、固定底部**休息计时条**（进度+跳过）+ 完成训练常驻入口；成功页改用 SuccessBlock |
| **History** | 卡片列表 | 类型图标+逐组行（#序号/热身标签/RPE）；纠错弹窗改 `Sheet` |
| **Coach** | 提案/咨询/聊天混在一页纵向滚动 | **三分离**：移动端 Segmented Tabs（对话/待确认修改 n/专家咨询）；桌面左聊天+右侧栏常驻。提案卡结构化：修改内容框+影响范围+同意/先不改（**确认协议与报文完全不变**）；气泡重绘（用户=青柠右、教练=白卡+头像）、打字指示、空状态建议点击填充；专家咨询的"发起尝试"链路保留 |
| **Explore** | 文字列表+底部抽屉详情 | 卡片网格（1/2/3 列自适应）：占位封面（首字母+深墨渐变，无第三方素材）+肌群中文筛选 chips；**详情改独立页 `/explore/:id`**：头图（用户媒体优先）+三标签（教学/动作分析/知识依据）；分析上传、重复时间轴、故障提示、对比、签名媒体全部保留 |
| **Mine** | 全部塞一页 | 概览页：资料卡（头像/定级/摘要）+训练方式概览（四宫格）+个人尝试+入口列表；**次级页** `/mine/approach`（五维编辑+版本历史+两版对比）、`/mine/settings`（休息时长/导出/切换用户/令牌/同步失败处理） |
| **Onboarding** | 文字 tag 步进 | 品牌 Header+分段进度条（图标+标签）；目标=带图标选择卡；场地=选择卡；PAR-Q 逐项作答（**未答校验原样保留，实测拦截漏答**）；结果页区分暂停/成功 |
| **KnowledgePanel** | 混用旧色 | Segmented 分栏+新 tokens，检索/导入/待审/隔离/视频导入/新动作提案逻辑全部不变 |

## 五、验收记录

- **尺寸**：390×844、430×932、768×1024、1440×900 全部实机截图（`docs/redesign-shots/`，共 24 张）。
- **横向溢出**：10 条路由 × 3 档宽度 = 30 组合，`scrollWidth-clientWidth` 全部为 0。
- **交互实测**（浏览器自动化，真实后端）：四步建档全流程（含 PAR-Q 漏答被拦截）→ 规则引擎生成计划 → 开始训练 → 记录 2 组（休息计时器、撤销、连续记录）→ 完成训练入库 → 历史纠错弹层 → 动作选择器弹层 → 训练方式初始化/编辑 → 教练对话发送（错误态展示正常）。
- **对比度**：深色卡（`#18251D`）主文字白 ≈15.9:1、次级 `white/70` ≈9.6:1、青柠强调 ≈11.8:1，均远超 AA。
- **测试**：`vitest` 9/9 通过；`tsc --noEmit` 零错误；`vite build` 成功（gzip JS 102KB）；`pytest` 后端 **583/583** 通过。
- **数据真实性**：所有截图数据来自真实建档用户 `uidemo`（走真实 UI 与 API），无虚构数据。

## 六、未完成 / 限制说明

1. **软键盘遮挡**：桌面浏览器无法模拟移动端软键盘；已用 `dvh`/吸底输入区/`overscroll-contain` 预防，需真机复验（iOS Safari + 微信内置浏览器）。
2. **离线视觉态**：离线横幅与队列逻辑未改（`offline.ts` 原样），"断网横幅"样式已适配但未做端到端断网实拍。
3. **教练 LLM**：本环境未配置模型密钥，对话返回 500 由 ErrorBox 如实呈现；提案卡/咨询卡为空态截图，含提案的满态视觉依赖真实 LLM 输出（协议渲染逻辑未变）。
4. **动作封面**：仅当用户通过"视频导入"关联了封面媒体时显示真实封面，否则为统一占位视觉（设计使然，不引入未授权素材）。
5. **PWA**：`sw.js` 缓存版本已升到 v11；图标/主题色已更新，未做安装向导类增强（不在本轮范围）。
6. **旧版 `/history` 等直达链接**：路由全部保留，旧链接无失效。
