"""专家注册表：一主教练 + 五专业顾问 + 共享知识研究。

每位专业顾问登记：
- label / domain：用户可见身份与职责边界；
- data_sources：明确的数据来源（授权范围，用户可见）；
- tools：确定性基础分析工具（代码，不是提示词）；
- workbench：工作台状态——ready=业务功能已上线；planned=该领域数据
  系统尚未建设（P1-P4），只保留咨询入口，不伪造分析能力；
- triggers → task_types：本领域订阅的业务事件与对应分析类型。

P0 实装：training_science 的 post-workout-review；P1 实装：nutrition 的
daily-nutrition-review；P2 实装：recovery 的 recovery-review（三者均为
确定性，复用 fact_service / 确定性营养计算 / 确定性恢复指标）。
其余触发源在枚举中登记，待对应领域数据系统落地后接线。
"""
from __future__ import annotations

# 业务事件（2.0 §2.3）；P0 已接线：WorkoutSaved / UserRequested / PlanChanged(失效)
TRIGGERS = ("WorkoutSaved", "MealRecorded", "RecoveryRecorded",
            "BodyMeasurementRecorded", "SymptomReported",
            "VideoAnalysisCompleted", "PlanChanged", "TrialReviewDue",
            "UserRequested")

# 任务类型 → 执行器（task_dispatcher 按表派发；确定性函数，不调 LLM）
TASK_TYPES: dict[str, str] = {
    "post-workout-review": "coach.experts.training_science.analyze_post_workout",
    "daily-nutrition-review": "coach.nutrition.nutrition_analysis.analyze_daily_nutrition",
    "recovery-review": "coach.recovery.recovery_analysis.analyze_recovery",
}

SPECIALISTS: dict[str, dict] = {
    "training_science": {
        "label": "训练科学顾问",
        "domain": "训练计划、进阶、负荷与周期",
        "data_sources": ["训练打卡记录（逐组口径）", "当前训练计划", "动作统计与趋势"],
        "tools": ["训练事实服务（30/60 天窗口）", "趋势分析（前后半窗中位数）"],
        "workbench": "ready",
        "workbench_path": "/experts/training",
        "triggers": {"WorkoutSaved": ["post-workout-review"],
                     "UserRequested": ["post-workout-review"]},
    },
    "nutrition": {
        "label": "营养顾问",
        "domain": "食物、营养目标、饮食分析",
        "data_sources": ["饮食记录（含营养快照）", "营养目标（你设置的）",
                         "食物库（内置参考值 + 你的自定义）"],
        "tools": ["确定性营养计算（份量换算/快照求和）", "记录完整度与趋势汇总"],
        "workbench": "ready",
        "workbench_path": "/experts/nutrition",
        "triggers": {"MealRecorded": ["daily-nutrition-review"],
                     "BodyMeasurementRecorded": ["daily-nutrition-review"],
                     "UserRequested": ["daily-nutrition-review"]},
    },
    "recovery": {
        "label": "恢复顾问",
        "domain": "睡眠、疲劳、恢复状态",
        "data_sources": ["恢复打卡（睡眠/疲劳/酸痛，自报 1-5）",
                         "训练事实（同源口径的负荷上下文）"],
        "tools": ["确定性恢复指标（窗口均值/高分计数/区域汇总）",
                  "训练前简报（确定性）"],
        "workbench": "ready",
        "workbench_path": "/experts/recovery",
        "triggers": {"RecoveryRecorded": ["recovery-review"],
                     "WorkoutSaved": ["recovery-review"],
                     "UserRequested": ["recovery-review"]},
    },
    "rehabilitation": {
        "label": "康复与伤痛风险顾问",
        "domain": "症状记录、训练限制、风险提示",
        "data_sources": ["医疗安全门（档案伤病与许可）"],
        "tools": ["训练许可判定（medical.training_permission）"],
        "workbench": "planned",   # P3
        "workbench_note": "身体不适记录与训练限制管理将在康复辅助阶段提供",
        "triggers": {"SymptomReported": []},
    },
    "movement": {
        "label": "动作技术顾问",
        "domain": "动作教学、视频分析、技术反馈",
        "data_sources": ["动作库与结构化教学", "个人视频姿态分析（若有）"],
        "tools": [],
        "workbench": "planned",   # P4
        "workbench_note": "动作技术工作台（视频对照三维演示）将在下一阶段提供",
        "triggers": {"VideoAnalysisCompleted": []},
    },
}

# 共享知识研究（原 Knowledge Agent 定位：后台能力，不单开聊天窗口）
SHARED_SERVICES = {
    "knowledge_research": {
        "label": "运动科学知识研究",
        "note": "所有顾问共用的知识检索；命中带来源与审核状态，草稿不得当结论",
    },
}

ORCHESTRATOR = {"key": "orchestrator", "label": "主教练",
                "note": "整合各顾问事实与分歧，展示方案取舍，不替用户裁决"}


def specialists_view() -> list[dict]:
    """注册表的对外视图（Experts 中心页用；不含内部执行器路径）。"""
    out = []
    for key, spec in SPECIALISTS.items():
        out.append({"specialist": key, "label": spec["label"],
                    "domain": spec["domain"],
                    "data_sources": spec["data_sources"],
                    "tools": spec["tools"],
                    "workbench": spec["workbench"],
                    "workbench_path": spec.get("workbench_path"),
                    "workbench_note": spec.get("workbench_note")})
    return out


def subscribed(specialist: str, trigger: str) -> list[str]:
    """某顾问对某事件订阅的任务类型列表。"""
    spec = SPECIALISTS.get(specialist) or {}
    return list(spec.get("triggers", {}).get(trigger, []))


def specialist_label(specialist: str) -> str:
    return (SPECIALISTS.get(specialist) or {}).get("label", specialist)
