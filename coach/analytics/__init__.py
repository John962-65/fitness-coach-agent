"""M6.3：专业训练记录分析——直接基于逐组记录（set_logs）计算，不依赖聚合代表组。

设计约束（来自产品复查）：
- 训练容量 = 全部有效正式组的 外部负重 × 次数 之和（自重组贡献 0，如实呈现）；
- 估算 1RM（Epley）只在 1-12 次的适用区间内逐组计算取最佳，且只是模型估计；
- 不同指标独立计算，互不混用（容量最大组 ≠ 最大力量组）；
- 肌群组数按动作 primary 主肌群归口，一组只记一次，避免重复统计。
"""
from __future__ import annotations

from .exercise_metrics import exercise_sessions, personal_records
from .training_calendar import month_calendar, period_summary

__all__ = ["exercise_sessions", "personal_records", "month_calendar", "period_summary"]
