# RC-2 实体设备验收（T5）

> 基线：`750cd3b`｜ 日期：2026-10-27
> 结论：**T5 未执行。没有可用的实体 Android/iOS 设备或移动模拟器；本文不把桌面浏览器移动视口当作实体机验收。RC-2 门槛未通过。**

## 0. 执行环境与证据边界

| 项 | 结果 |
|---|---|
| 主机 | Linux 6.8.0-138-generic x86_64（Ubuntu 22.04） |
| Android 设备 / ADB | `adb` 不存在；无已连接设备 |
| Android 模拟器 | `emulator` 不存在（`/dev/kvm` 存在，但未安装 AVD/模拟器） |
| iOS 设备 / Xcode / Safari | 不可用（Linux 主机，无 Apple 设备） |
| 桌面 Chrome | 153.0.8010.47 |
| 桌面 Firefox | 158.0.1 |
| Node / npm / Python | 24.17.0 / 11.13.0 / 3.10.12 |
| 前端离线回归 | 74 passed / 11 files（`npm test`） |
| 前端生产构建 | `npm run build` 通过（tsc --noEmit + Vite） |
| 既有浏览器 E2E 截图 | `docs/p3-shots/`、`docs/p5c3-shots/`、`docs/p6-shots/` 等，均为**桌面 Chrome 的移动视口**，不是实体机 |

**不能替代的关系**：桌面 Chrome 移动视口可以验证布局与部分交互，但不能验证实体机的软键盘、触摸滚动、锁屏/后台、摄像头/相册、MediaPipe 原生解码、PWA 安装、iOS Safari 的 standalone 行为、存储配额与网络切换。故本轮不给出任何“设备通过”结论。

## 1. 任务书要求的测试项与状态

状态定义：`NOT EXECUTED` = 没有在实体设备上执行；`AUTOMATED COVERAGE` = 只有代码/自动化间接证据，不能算 T5。

### 1.1 完整训练（Android Chrome / iOS Safari/PWA）

流程：打开计划 → 记录训练组 → 休息计时 → 切换应用 → 返回 → 结束并保存。

| 检查 | 状态 | 现有间接证据 | 实体机必须观察 |
|---|---|---|---|
| 打开今日计划并进入训练 | NOT EXECUTED | 前端 store/E2E 截图 | 首屏、软键盘、返回手势 |
| 逐组记录（重量/次数/RPE） | NOT EXECUTED | `checkin.test.ts` 13 项 | 数字键盘、输入法遮挡、误触 |
| 组间休息计时 | NOT EXECUTED | `execution.test.ts` | 切后台/锁屏后计时是否按真实时间恢复 |
| 切换应用后返回 | NOT EXECUTED | 无 | iOS 冻结、Android 进程回收 |
| 结束并保存 | NOT EXECUTED | API/离线队列测试 | 弱网、重复点击、保存反馈 |
| 刷新后草稿恢复 | NOT EXECUTED | `store.test.ts`、`offline.test.ts` | 浏览器崩溃/被系统杀掉后的恢复 |

### 1.2 HIIT（开始 → 锁屏/后台 → 返回 → 恢复状态 → 提前结束）

| 检查 | 状态 | 现有间接证据 | 实体机必须观察 |
|---|---|---|---|
| 开始 HIIT | NOT EXECUTED | `execution.test.ts`、P5-B E2E | 触摸开始/暂停/结束按钮 |
| 锁屏/切后台 | NOT EXECUTED | 逻辑层 `hiit` 状态测试 | iOS/Android 定时器节流、音频/振动 |
| 返回恢复状态 | NOT EXECUTED | `store` 持久化测试 | 是否从正确轮次/剩余秒数恢复 |
| 提前结束 | NOT EXECUTED | `test_p5b11` 逻辑 | 结束原因、已完成轮次、容量口径 |

### 1.3 营养（搜索 → 份量 → 记录 → 修改 → 统计）

| 检查 | 状态 | 现有间接证据 | 实体机必须观察 |
|---|---|---|---|
| 食物搜索 | NOT EXECUTED | `nutrition.test.ts` | 中文输入、搜索延迟、结果滚动 |
| 份量输入/单位换算 | NOT EXECUTED | 营养计算测试 | 数字键盘、单位选择 |
| 记录/修改/删除 | NOT EXECUTED | API 测试 | 误触、重复提交、离线 |
| 查看日/周统计 | NOT EXECUTED | 统计测试 | 小屏图表可读性 |

### 1.4 动作技术（真实手机视频 → 上传 → MediaPipe → 三维对照 → 历史）

| 检查 | 状态 | 现有间接证据 | 实体机必须观察 |
|---|---|---|---|
| 手机拍摄/相册选择 | NOT EXECUTED | 无 | 摄像头权限、HEVC/格式、方向元数据 |
| 上传大视频 | NOT EXECUTED | 200MB 流式上限/魔数校验 | 移动网络中断、后台被杀 |
| MediaPipe 分析 | NOT EXECUTED | 桌面/CPU 逻辑测试 | 手机端是否在服务端跑、耗时、内存 |
| 三维对照渲染 | NOT EXECUTED | `Exercise3DViewer` 构建 | WebGL 兼容、发热、掉帧 |
| 历史查看 | NOT EXECUTED | API 测试 | 缩略图/视频签名 URL 过期 |

### 1.5 数据可靠性（断网、刷新、关闭、重开、存储空间、重复提交）

| 检查 | 状态 | 现有间接证据 | 实体机必须观察 |
|---|---|---|---|
| 断网保存 | NOT EXECUTED | `offline.test.ts` 7 项 | 飞行模式、弱网切换 |
| 刷新/关闭重开 | NOT EXECUTED | IndexedDB 队列测试 | iOS 存储清理策略 |
| 存储空间不足 | NOT EXECUTED | 无 | QuotaExceeded、失败提示、是否丢记录 |
| 重复提交 | NOT EXECUTED | `submission_id` 幂等测试 | 双指/连点/网络重试 |
| 长时间使用后恢复 | NOT EXECUTED | 无 | 缓存膨胀、SW 版本升级、历史读取 |

## 2. 本轮实际执行的补充检查（不构成 T5）

### 2.1 前端回归与构建

- `npm test`：74 passed（协议、校验、营养、身体、专家、打卡、Markdown、离线、store、训练执行）。
- `npm run build`：通过；产物 `dist/assets/index-*.js` 592.45 kB（gzip 183.13 kB）、`Exercise3DViewer-*.js` 918.33 kB（gzip 250.42 kB），有 chunk 体积告警。实体机弱网/低端机加载时间需实测。

### 2.2 PWA 静态检查

| 项 | 观察 | 风险 |
|---|---|---|
| manifest | `display=standalone`、`start_url=/`、`theme_color` 存在 | 基本合格 |
| 图标 | 只有 `icon.svg`（`sizes:any`），无 192/512 PNG | Android 安装性/iOS 主屏图标可能降级 |
| iOS | `index.html` 无 `apple-touch-icon`、无启动图 | iOS 添加到主屏可能使用截图/空白 |
| Service Worker | 缓存应用外壳；`/api` 一律网络；离线记录走 IndexedDB 队列 | 逻辑合理，但未在实体机验证 SW 更新/配额 |
| viewport | `width=device-width, initial-scale=1, viewport-fit=cover` | 基本合格；刘海/底部安全区需真机看 |

### 2.3 既有 E2E 证据

`docs/p3-shots/`、`docs/p5c3-shots/`、`docs/p6-shots/` 等截图证明桌面 Chrome 在 390×844 视口下走过训练、HIIT、营养、康复、协作等路径。它们由桌面浏览器生成，**不能**证明 iOS Safari 的 standalone、软键盘、锁屏、摄像头或存储行为。

## 3. 实体机验收协议（待执行）

### 3.1 设备矩阵（必须填真实值）

| 设备 | 型号 | OS | 浏览器/版本 | 安装方式 | 结果 |
|---|---|---|---|---|---|
| Android | （待填） | （待填） | Chrome（待填） | 浏览器 / PWA 安装 | NOT EXECUTED |
| iOS | （待填） | （待填） | Safari（待填） | 浏览器 / 添加到主屏 | NOT EXECUTED |

至少一台 Android Chrome + 一台 iOS Safari/PWA；只有单平台时必须明确标注另一平台未验证。

### 3.2 执行步骤（每项记录：时间、操作、预期、实际、截图/录屏、是否通过）

1. **安装与首屏**：HTTPS 或局域网地址；安装 PWA；冷启动；检查图标、启动画面、离线壳。
2. **完整训练**：按 1.1 流程；记录切后台 30s/5min 两组；检查休息计时是否按真实时间恢复；结束保存后刷新/重开确认记录。
3. **HIIT**：按 1.2 流程；锁屏 1 分钟；返回检查轮次/剩余秒数；提前结束并保存；检查统计口径。
4. **营养**：按 1.3 流程；用中文搜索、输入小数份量、修改餐次；检查日统计与记录一致。
5. **动作技术**：用手机相机拍 10–20 秒侧视深蹲/卧推；上传；等待分析；检查质量门提示、三维对照、历史；再拍一段正面视频验证“不可判断”提示。
6. **可靠性**：飞行模式保存 → 恢复网络同步；强制关闭 App 重开；重复点击保存；填满存储/低电量模式；检查失败记录是否保留且可导出。
7. **边界**：锁屏/来电/通知/蓝牙耳机/旋转屏幕；iOS 低电量模式；Android 省电模式。

### 3.3 通过标准（建议）

- 训练记录无丢失、无重复、日期/统计一致；离线队列可恢复；失败记录不静默删除。
- HIIT 切后台后状态可恢复，提前结束不丢已完成轮次。
- 营养记录/修改/统计一致；食物未知值不显示为 0。
- 视频上传/分析有明确进度与失败原因；不可判断时不伪造结论；3D 不崩溃。
- PWA 可安装、可离线打开外壳；iOS/Android 图标与启动不空白。
- 所有失败都有用户可见提示与可恢复路径。

## 4. 结论

**RC-2 = NOT EXECUTED（T5 未通过）。** 原因不是“测试失败”，而是没有实体设备/模拟器条件；桌面移动视口、自动化测试和构建只能作为补充证据。任务书要求记录设备型号、系统版本、浏览器版本与实际观察结果——本轮这些字段为空，不能填写推测值。

在获得至少一台 Android Chrome 与一台 iOS Safari/PWA 实体机并按 §3 执行之前，不得把版本标记为 RC，也不得宣称“支持平台已经验收”。
