# P4 交付文档：动作技术与三维教学系统

> 交付日期：2026-10-25 ｜ 基线：P3（`ecc7b53`）｜ 状态：**已交付，验收通过**
> 总纲见 [expert-platform-roadmap.md](expert-platform-roadmap.md)

## 0. 交付范围

动作技术顾问工作台（`/experts/movement`）：首批五个三维动作（深蹲/卧推/
硬拉/划船/肩推）的三维教学、个人视频分析（质量门→确定性观察→周期切分）、
视频×三维分屏对照、长期技术档案、movement-review 洞察、康复安全联动。
**不重做**三维播放器（复用 Exercise3DViewer）、视频存储（复用 media 体系）、
动作库（稳定 exercise_id）。

## 1. P4-0 审计报告（现有能力 × 缺口）

| 项目 | 现状 | P4 动作 |
|---|---|---|
| 视频输入 | mp4/mov/webm/mkv ≤200MB；签名鉴权（media_sign 10 分钟短签名）；魔数校验；按 uid 隔离 | 复用 |
| 视频分析 | MediaPipe 本地 CPU（视频不出本机）+ vision-rules 确定性故障码；质量门双比例（detection/valid） | 复用+扩展 |
| 关键点 | 33 点+visibility；质量门按动作所需关键点组计算 | 复用 |
| 动作阶段 | segment_reps 峰值检测（蹲=髋高/铰链=躯干角/卧推=肘角） | 扩展到划船/肩推 |
| 三维资源 | 5 个 GLB + teaching_phases + 授权 manifest | 复用 |
| 视频历史 | motion_analyses 表（user 隔离）+compare 接口 | 扩展档案 |
| 教学审核 | teaching_content 各节 draft/reviewed/approved | 如实透传 |
| **缺口 1** | 划船/肩推不在 EXERCISE_RULES（五动作中两个无分析） | **新增 checkers** |
| **缺口 2** | 分析结果无 P4-2 结构（质量状态/观察/模型版本） | **新增技术档案表** |
| **缺口 3** | 无 VideoAnalysisCompleted 事件、MovementAgent 未接入 | **接入专家体系** |

## 2. 修改文件清单

### 后端

| 文件 | 变更 |
|---|---|
| `coach/vision_rules.py` | 新增 check_row / check_shoulder_press（肘角 ROM 保守规则）+ ROW_SHALLOW_PULL / PRESS_SHALLOW_LOCKOUT 标签 |
| `coach/motion_analysis.py` | 五动作映射；ANALYSIS_MODEL_VERSION 常量；build_observations（确定性观察：视角限制声明/周期计数/节奏/一致性/故障转写/不足声明）；detection_ratio 修正（空骨架帧不算检出） |
| `coach/db.py` | 新增 motion_tech_profiles（1:1 挂 motion_analyses）+ 方法（档案/版本/删除/备注） |
| `coach/movement/analysis.py` | movement-review 确定性洞察（观察转写+教学引用只取 reviewed/approved+draft 如实声明+无法判断清单+康复限制只读展示） |
| `coach/experts/registry.py` | movement ready；movement-review 任务注册；VideoAnalysisCompleted 订阅 |
| `coach/experts/insight_service.py` | 漂移检测扩展：motion 档案版本（含内容长度签名——同秒重算可区分） |
| `backend/routes.py` | worker 完成时写档案+触发事件（容错不回滚）；分析列表附 tech_profile；DELETE 分析；备注端点 |
| `test_p4.py` | 8 项专项回归 |

### 前端

| 文件 | 职责 |
|---|---|
| `src/pages/experts/MovementExpert.tsx` | 工作台四区（三维教学/视频分析/历史/洞察）；五动作切换；自定义动作如实"不支持" |
| `src/components/movement/MotionUpload.tsx` | 上传（视角选择+拍摄规范+轮询） |
| `src/components/movement/MotionAnalysisReport.tsx` | 质量→观察→故障→阶段时间轴→安全提醒→局限 |
| `src/components/movement/VideoComparison.tsx` | 分屏对照（独立播放/倍速 0.25-1.5x/手动对齐/阶段跳转/签名 URL） |
| `src/lib/movement.ts` | 展示工具（质量四态/观察 kind/可比性判断） |

## 3. 运动分析结果结构（P4-2）

```json
{
  "exercise_id": "barbell_back_squat", "analysis_id": 2,
  "video_quality": {"status": "usable", "view": "side",
    "detection_ratio": 0.95, "valid_ratio": 0.9, "limitations": []},
  "motion_observations": [{"kind": "view-limitation", "text": "…二维投影角…"},
    {"kind": "rep-count", "text": "…2 个动作周期…"}, {"kind": "rhythm", "text": "…"}],
  "phase_timestamps": [{"rep": 1, "start_s": 0.3, "end_s": 1.5, "peak_s": 0.9}],
  "model_version": "motion-1: mediapipe-pose + vision-rules-1",
  "review_status": "unreviewed"
}
```

- 质量不足（detection<0.5 / valid<0.5 / 关键点缺失）→ status=poor + 具体
  原因 + 建议重拍；**不输出看似精确的角度**（观察只有 insufficient 声明）；
- 视角限制声明永远存在（"所有角度均为二维投影角，不是真实三维关节角"）；
- 划船/肩推信号=肘角（肩-肘-腕），与卧推同一确定性周期机制（有测试）。

## 4. 数据兼容方案

`motion_tech_profiles` 以 analysis_id 主键 1:1 挂 `motion_analyses`——
**单一视频分析历史**，无第二套。旧记录无档案 → UI 如实标"旧版分析"。
删除分析级联删档案。洞察漂移锚=档案版本（count+时间+内容长度签名，
同秒重算可区分，有测试）。

## 5. 与康复辅助联动（P4-6）

- 洞察 findings 附 `safety-restriction`（safety_view 中与本动作相关的
  限制，只读展示："观看/学习教学不受影响；是否执行请遵循限制"）；
- movement-review **无任何 proposal 类选项**（有测试断言）——分析不取消
  限制、不生成冲突训练建议；限制版本变化 → 洞察失效（有测试）；
- 分析结果不诊断损伤（测试断言不含力矩/腰椎损伤/半月板词，排除
  unable-to-judge 声明本身）。

## 6. 测试与验收

### 自动化（`test_p4.py` 8 项；全量 750 项通过）
五动作支持映射/划船肩推周期切分/场景 B 上传→档案→洞察（draft 教学
如实声明、无诊断词、证据闭合）/关键点缺失降级（detection 修正）/poor
质量→重拍选项/场景 D 历史漂移删除隔离备注/场景 E 限制展示不越界+
限制变化失效/模型版本。前端 tsc+52 项+构建通过。

### 真实浏览器 E2E（390×844）
- **场景 A**：五动作切换 → 三维演示（视角/播放/倍速/阶段提示）→ 结构化
  教学各节渲染（**修复**：common_errors 节 items 为 {error,consequence,fix}
  对象，React #31 白屏 → 分类渲染）→ 草稿状态"不作为已确认指导依据"
  标注（截图 01）；
- **场景 B**：生成骨架测试视频经 API 上传 → 真实 MediaPipe **拒绝识别
  火柴人**（detection=0 → poor + 具体原因）——质量门真实生效；播种一条
  自动化流程验证过的 usable 分析后，报告展示质量/观察/阶段（截图 02）；
- **场景 C**：分屏对照——视频签名加载、播放（1.5s/3s verified）、3D 独立
  控制面板、手动对齐滑杆、阶段跳转、"不与动画重合≠错误"提示（截图 03）；
- **场景 D**：两条历史 → 确定性对比 → **视角/质量不可比提示**优先展示
  （截图 04）；洞察列表 usable=ready/medium 与 poor=invalidated 并存
  （漂移留痕）（截图 05）；
- **场景 E**：限制联动由 test_p4 场景 E 覆盖（展示不越界+失效）。

### 实际发现并修复的问题
1. React #31 白屏：教学 items 元素为对象 → 分类渲染（E2E 抓出）；
2. `/experts/movement` 路由漏注册 → 补；
3. detection_ratio 把空骨架帧当检出 → 修正；
4. 观察分流/档案版本同秒重算不触发漂移 → 内容长度签名；
5. 分析器对缺字段 phase 不容错 → p.get() 化。

## 7. 已知限制与后续计划

1. **真实手机拍摄视频兼容性未验证**（E2E 用合成视频；真机拍摄的光照/
   抖动/分辨率差异需单独实测——任务书已预告）；
2. 自动对比的"跨周期深度逐周期一致性"为整体范围提示，逐周期对比属
   后续增强；无器械关键点跟踪；
3. 教学 review_status 目前全为 draft——**教学来源审核缺口如实透传**，
   洞察明确声明"不足以作为已确认的专业指导依据"；
4. 真实 LLM 评测未执行（FAKE 通过不宣称建议质量可靠）；
5. 对照不自动时空配准（首版按设计手动对齐）；切换 3D 视角不影响视频
   数据（独立面板）；
6. 上传后分析仍在进行时的提示文案已覆盖（轮询 40 次≈60s，超时引导
   历史页刷新）。
