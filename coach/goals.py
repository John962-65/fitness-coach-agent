"""C2 目标协商（DESIGN 26.4）：支持范围、取舍与过渡预览、目标版本绑定。

目标状态区分"已确认的当前目标"（profile.goal，带 version/evaluation/confirmed_at）
与"正在讨论的新目标"（pending_profile_changes 暂存项）；评价指标随目标一致切换。
"""
from __future__ import annotations

SUPPORTED_GOALS = ("fat_loss", "muscle_gain", "strength", "health", "shaping")

_GOAL_PROFILES = {
    "fat_loss": dict(
        label="减脂",
        training="力量训练保肌肉为主，训练为辅，配合饮食缺口",
        nutrition="热量缺口、慢减脂节奏",
        metrics="体重/围度趋势下降 + 力量尽量维持"),
    "muscle_gain": dict(
        label="增肌",
        training="容量 + 渐进超负荷，分化训练",
        nutrition="热量盈余 + 足量蛋白",
        metrics="力量渐进 + 围度增长 + 体重缓升"),
    "strength": dict(
        label="力量",
        training="大重量低次数、周期化与恢复安排",
        nutrition="足量碳水与蛋白支持训练表现",
        metrics="主要动作 e1RM 与组数×重量渐进"),
    "health": dict(
        label="健康",
        training="全面的基础动作模式与适度强度",
        nutrition="均衡饮食，不设激进缺口或盈余",
        metrics="执行率、体感与基础体能维持"),
    "shaping": dict(
        label="塑形",
        training="增肌与减脂按阶段组合编排",
        nutrition="按当前阶段在缺口与盈余间切换",
        metrics="围度比例与体脂趋势组合"),
}


def goal_label(primary: str) -> str:
    return _GOAL_PROFILES.get(primary, {}).get("label", str(primary))


def goal_metrics(primary: str) -> str:
    return _GOAL_PROFILES.get(primary, {}).get("metrics", "")


def goal_transition_preview(old: str, new: str) -> str:
    """取舍与过渡预览（26.4 步骤③，纯函数）：确认前给用户看的结构化对比。"""
    o = _GOAL_PROFILES.get(old, {})
    n = _GOAL_PROFILES.get(new, {})
    if not n:
        return ""
    lines = [
        f"【目标变更预览】{o.get('label', old)} → {n['label']}",
        f"训练侧重：{o.get('training', '（原目标未记录）')} → {n['training']}",
        f"营养侧重：{o.get('nutrition', '（原目标未记录）')} → {n['nutrition']}",
        f"评价指标：改为「{n['metrics']}」",
    ]
    if old == "fat_loss" and new == "muscle_gain":
        lines.append("注意：切换后体重不再下降不再默认当失败，评价改为力量/围度与体重缓升。")
    if old == "muscle_gain" and new == "fat_loss":
        lines.append("注意：切换后体重开始下降是预期结果，不视为退步。")
    lines.append("保留与过渡：动作能力记录、偏好、历史打卡与兼容处方重量全部保留，不清空历史；"
                 "旧阶段的复盘按旧目标评价，旧目标下待执行建议作废。")
    return "\n".join(lines)


def bump_goal_version(profile: dict) -> int:
    """确认目标变更时版本 +1；计划在生成时记录 goal_version 完成绑定（26.4 步骤⑤）。"""
    g = profile.setdefault("goal", {})
    g["version"] = int(g.get("version") or 0) + 1
    return g["version"]
