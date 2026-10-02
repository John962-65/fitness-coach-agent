# P1 高频动作审核包（设计书 24.1）

> 生成：2026-10-02 22:41｜基线 commit：`9ef8222`
> 目标人群：无明确医疗禁忌、有一定训练基础、每周 2–4 次的健身房用户
> 审核范围：槽位模板实际用到的动作；类型只列 cue/method/error/self_check（anecdote 等本轮跳过）

## 杠铃深蹲（`barbell_back_squat`）· 主力

- **谭成义**：2 条（error×1、method×1）
- ⚠️ **speaker 待确认 1 条**（BV17ooLBUEqS，双人出镜/字幕不分说话人，审核时先定归属，无法确认就不作个人归因）
- 另有 2 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise barbell_back_squat --types cue,error,self_check,method
  ```

## 杠铃平板卧推（`barbell_bench_press`）· 主力

- **凯圣王**：5 条（cue×2、method×3）
- **谭成义**：18 条（cue×7、error×2、method×7、self_check×2，🚩 反幻觉标记 1 条（优先核））
- ⚠️ **speaker 待确认 7 条**（BV17ooLBUEqS，双人出镜/字幕不分说话人，审核时先定归属，无法确认就不作个人归因）
- 另有 14 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise barbell_bench_press --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise barbell_bench_press --types cue,error,self_check,method
  ```

## 罗马尼亚硬拉（`romanian_deadlift`）· 主力

- **凯圣王**：49 条（cue×18、error×15、method×15、self_check×1，🚩 反幻觉标记 1 条（优先核））
- **谭成义**：65 条（cue×39、error×9、method×14、self_check×3，🚩 反幻觉标记 3 条（优先核））
- ⚠️ **speaker 待确认 1 条**（BV17ooLBUEqS，双人出镜/字幕不分说话人，审核时先定归属，无法确认就不作个人归因）
- 另有 38 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise romanian_deadlift --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise romanian_deadlift --types cue,error,self_check,method
  ```

## 站姿推举（`overhead_press`）· 主力

- **谭成义**：9 条（cue×3、error×2、method×3、self_check×1）
- 另有 5 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise overhead_press --types cue,error,self_check,method
  ```

## 杠铃划船（`barbell_row`）· 主力

- **凯圣王**：3 条（error×1、method×2）
- **谭成义**：5 条（cue×1、error×1、method×3）
- 另有 4 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise barbell_row --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise barbell_row --types cue,error,self_check,method
  ```

## 硬拉（`deadlift`）· 主力

- **凯圣王**：1 条（error×1）
- **谭成义**：11 条（cue×1、error×6、method×3、self_check×1，🚩 反幻觉标记 1 条（优先核））
- 另有 6 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise deadlift --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise deadlift --types cue,error,self_check,method
  ```

## 高位下拉（`lat_pulldown`）· 次要

- **凯圣王**：46 条（cue×16、error×18、method×8、self_check×4，🚩 反幻觉标记 2 条（优先核））
- **谭成义**：36 条（cue×18、error×7、method×8、self_check×3）
- 另有 28 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise lat_pulldown --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise lat_pulldown --types cue,error,self_check,method
  ```

## 杠铃上斜卧推（`incline_bench_press`）· 次要

- **凯圣王**：4 条（method×4）
- **谭成义**：28 条（cue×12、error×3、method×11、self_check×2）
- ⚠️ **speaker 待确认 2 条**（BV17ooLBUEqS，双人出镜/字幕不分说话人，审核时先定归属，无法确认就不作个人归因）
- 另有 13 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise incline_bench_press --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise incline_bench_press --types cue,error,self_check,method
  ```

## 坐姿划船（`seated_row`）· 次要

- **凯圣王**：2 条（cue×1、method×1）
- **谭成义**：25 条（cue×10、error×5、method×7、self_check×3）
- 另有 7 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise seated_row --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise seated_row --types cue,error,self_check,method
  ```

## 倒蹬（`leg_press`）· 次要

**暂无 P1 类型素材**——本轮只能用通用知识教学（标 general，不点名博主）。

## 负重引体向上（`weighted_pull_up`）· 次要

**暂无 P1 类型素材**——本轮只能用通用知识教学（标 general，不点名博主）。

## 保加利亚分腿蹲（`bulgarian_split_squat`）· 次要

- **凯圣王**：16 条（cue×6、error×2、method×7、self_check×1，🚩 反幻觉标记 1 条（优先核））
- **谭成义**：27 条（cue×11、error×3、method×13，🚩 反幻觉标记 1 条（优先核））
- ⚠️ **speaker 待确认 1 条**（BV17ooLBUEqS，双人出镜/字幕不分说话人，审核时先定归属，无法确认就不作个人归因）
- 另有 18 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise bulgarian_split_squat --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise bulgarian_split_squat --types cue,error,self_check,method
  ```

## 侧平举（`lateral_raise`）· 辅助

- **凯圣王**：33 条（cue×8、error×9、method×13、self_check×3）
- **谭成义**：38 条（cue×15、error×8、method×14、self_check×1，🚩 反幻觉标记 1 条（优先核））
- 另有 21 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise lateral_raise --types cue,error,self_check,method
  ```
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise lateral_raise --types cue,error,self_check,method
  ```

## 杠铃弯举（`barbell_curl`）· 辅助

- **凯圣王**：3 条（error×1、method×2）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 凯圣王 --exercise barbell_curl --types cue,error,self_check,method
  ```

## 俯卧腿弯举（`lying_leg_curl`）· 辅助

- **谭成义**：5 条（cue×4、method×1）
- 另有 1 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise lying_leg_curl --types cue,error,self_check,method
  ```

## 站姿提踵（`standing_calf_raise`）· 辅助

- **谭成义**：7 条（cue×1、error×2、method×4，🚩 反幻觉标记 1 条（优先核））
- 另有 3 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise standing_calf_raise --types cue,error,self_check,method
  ```

## 面拉（`face_pull`）· 辅助

- **谭成义**：5 条（cue×4、method×1）
- 另有 1 条非 P1 类型（anecdote/principle 等，本轮跳过）
- 审核命令：
  ```bash
  python3 tools/review_ui.py --blogger 谭成义 --exercise face_pull --types cue,error,self_check,method
  ```

---
## 汇总

- 模板动作 17 个；P1 类型待审条目 **443 条**（🚩 反幻觉标记 12，speaker 待确认 12）
- 预估审核时长：每条 20–30 秒 ≈ **147–221 分钟**（不含跳转视频核对画面）
- 无 P1 素材的动作（2）：倒蹬（leg_press）、负重引体向上（weighted_pull_up）——教学时用通用知识，审核条目到位后再补

审核顺序建议：主力动作在前（深蹲/卧推/硬拉类，条目多、教练价值最高）；🚩 条目优先核对原文；speaker 待确认的先定归属再 approve。approve 后跑 `python3 tools/review_ui.py --apply` 挂到动作库，运行时即通过 get_exercise_coaching 带出处引用。
