# P5-B2 交付：地点、器械与动作替代

> 基线：`531b55c` ｜ 日期：2026-10-26 ｜ 状态：**已交付；P5-B3 尚未开始**

## 范围

- 训练地点：健身房/居家/户外/自定义，支持创建、编辑、删除、选择当前地点。
- 器械：系统稳定 ID 目录 + 用户自定义器械（按用户隔离）；每个地点分别配置必需/可选器械。
- 动作库筛选：肌群、器械、动作模式、地点类型、常用、当前地点可执行。
- 替代候选：确定性筛选动作模式、目标肌群、器械/地点、记录类型、训练水平和 P3 限制；输出适用差异并明确“不代表动作等价”。
- 替换分两条路径：仅本次会话替换（不写计划）与长期计划替换（ChangeProposal 待确认后才生效）。
- 服务端保存复核：临时替换动作必须通过当前安全层，且记录口径必须与候选动作一致。

## 数据模型

| 表 | 用途 |
|---|---|
| `training_locations` | 用户地点、类型、必需/可选器械 ID、当前地点 |
| `user_equipment` | 用户自定义器械：名称、分类、别名、可选等效系统器械 |

系统器械目录位于 `coach/equipment.py`，动作 YAML 的 `equipment` 字段直接使用同一组稳定 ID。
`rack`、`weight_belt` 属于可选支撑器械，缺失会提示但不单独判为不可用；“杠铃、哑铃、训练凳”
这一验收配置因此可以正确执行杠铃卧推。

## API

- `GET/POST /users/{uid}/locations`、`PATCH/DELETE /users/{uid}/locations/{id}`
- `POST /users/{uid}/locations/{id}/select`
- `GET/POST /users/{uid}/equipment`、`PATCH/DELETE /users/{uid}/equipment/{id}`
- `GET /exercises` 新增 `pattern/location/location_id/available/frequent`
- `GET /users/{uid}/exercise-substitutes`
- `POST /users/{uid}/exercise-substitutions/validate`
- 长期替换复用 `/changes/ai` → `/changes/{id}/confirm`

## 安全与确认

1. 候选生成与直选校验都调用 P3 `safety_view()` 与 `restriction_blocks()`。
2. 医疗/隔离状态阻断候选；活动限制动作从候选中剔除，直选返回 422。
3. 保存训练时再次校验 `session_replacement_of` 的目标动作安全状态与记录类型。
4. 仅本次替换只写当前会话；长期替换先创建 pending 提案，计划版本在确认前保持不变。
5. 器械不可用时只提示，不自动删除或修改任何已有动作。

## 测试

```bash
FAKE_LLM=1 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python3 -m pytest -q -p no:cacheprovider --confcutdir=/home/johb/fitness-coach-agent \
  test_p5b2.py test_p5b.py test_p3.py
# 35 passed；全量 783 passed

cd frontend
npm test    # 11 files / 67 tests passed
npm run build
```

`test_p5b2.py` 覆盖地点/器械 CRUD、用户隔离、自定义器械等效映射、六类筛选、
候选差异、器械/水平/记录口径过滤、P3 候选剔除与直选阻断、保存口径校验、
本次替换计划不变，以及长期 ChangeProposal 确认前后版本对比。

## 真实 Chrome E2E（390×844）

```bash
PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" node tools/e2e_p5b2.mjs
```

核心结果：

- 健身房配置：杠铃、哑铃、训练凳；居家配置：哑铃、弹力带、训练凳；
- 杠铃卧推在居家不可用，仍保留原动作，显示缺少杠铃并给出替代入口；
- 候选“哑铃卧推”通过器械、模式、肌群、水平和安全筛选；
- 仅本次替换落库 `exercise_id=dumbbell_bench_press`、
  `session_replacement_of=barbell_bench_press`，计划版本保持 `v1`；
- 创建 P3 限制后，哑铃卧推候选消失，服务端直选返回 `422`；
- 长期替换先进入待确认，确认后计划才从 `v1` 变为 `v2`。

截图：

1. [地点与器械配置](p5b2-shots/01-locations-gym-home-config.png)
2. [健身房卧推可用](p5b2-shots/02-gym-bench-available.png)
3. [居家识别杠铃不可用](p5b2-shots/03-home-bench-unavailable.png)
4. [筛选后的替代候选](p5b2-shots/04-substitute-candidates.png)
5. [仅本次替换与记录](p5b2-shots/05-session-only-replaced.png)
6. [P3 限制移除受限候选](p5b2-shots/06-p3-restricted-candidate-removed.png)
7. [长期提案待确认](p5b2-shots/07-long-term-proposal-pending.png)
8. [长期提案确认后](p5b2-shots/08-long-term-confirmed.png)

## 已知边界

- 候选列表最多展示 8 个，按确定性评分排序；不代表医学/康复等价建议。
- 自动计划生成仍使用建档时的基础地点条件；本阶段不会因切换地点自动重写长期计划。
- E2E 为系统 Chrome headless + CDP，不等同于实体手机测试。
- 本轮不包含 P5-B3 统计整合与下一次训练建议。
