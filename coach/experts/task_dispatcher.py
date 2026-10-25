"""专家任务调度：事件 → ExpertTask（落库队列）→ 执行 → ExpertInsight。

执行原则（2.0 §2.3）：
- 事件不等于调用 LLM。P0 的 post-workout-review 是纯确定性分析
  （fact_service 同源口径），不请求模型；LLM 仅在未来需要解释/知识比较的
  任务类型中使用（analysis_mode 字段已预留）；
- 任务按用户隔离，dedup_key 唯一约束保证事件级幂等（同一打卡重放不
  重复分析）；
- 失败重试（max_retries 内回到 pending），超限落 failed + error_code；
- 用户可关闭主动分析（settings.proactive_enabled）、可设频率限制
  （min_interval_minutes），UserRequested 不受 proactive 开关限制；
- 执行状态全部落库：进程重启后 pending 继续可执行，running 凭
  heartbeat_at 判定崩溃（recover_stale）；
- 专家失败绝不阻塞普通记录（routes 侧 try/except 包裹 on_event）。
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta

from . import insight_service, registry

MAX_RUN_PER_CYCLE = 5          # 单次 run_pending 最多执行的任务数
STALE_MINUTES = 10             # running 心跳超过该分钟数视为崩溃残留


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _analyzer(task_type: str):
    """任务类型 → 确定性分析器（registry 登记的模块路径）。"""
    path = registry.TASK_TYPES.get(task_type)
    if not path:
        raise ValueError(f"未登记的任务类型 {task_type!r}")
    module_name, _, func = path.rpartition(".")
    return getattr(importlib.import_module(module_name), func)


def _dedup_key(specialist: str, task_type: str, trigger: str,
               input_refs: dict) -> str | None:
    """事件级幂等键：引用同一数据状态的同一分析只做一次。

    - 锚点 = 输入引用整体摘要（如 MealRecorded 的 {local_date, day_version}：
      同日新增餐次会改变 day_version，从而触发新一轮分析而不是被去重掉）；
    - UserRequested / regenerate 不设键（用户可以主动重复请求，
      由频率限制约束）。
    """
    if trigger == "UserRequested":
        return None
    if not input_refs:
        return None
    anchor = "-".join(f"{k}:{v}" for k, v in sorted(input_refs.items()))
    return f"{specialist}:{task_type}:{trigger}:{anchor}"


def enqueue(db, user_id: str, specialist: str, task_type: str,
            trigger: str, input_refs: dict, max_retries: int = 2) -> dict | None:
    """入队（含设置检查、频率限制、幂等去重）。返回任务或 None（被拦截）。"""
    if specialist not in registry.SPECIALISTS:
        raise ValueError(f"未知专家 {specialist!r}")
    if task_type not in registry.TASK_TYPES:
        raise ValueError(f"未知任务类型 {task_type!r}")
    settings = db.expert_settings(user_id)
    if trigger != "UserRequested" and not settings["proactive_enabled"]:
        return None  # 用户已关闭主动分析：静默不入队（事件本身照常保存）
    # 频率限制：同 (specialist, task_type) 在窗口内已有 pending/running → 不重复
    min_minutes = settings["min_interval_minutes"]
    if min_minutes > 0:
        cutoff = (datetime.now() - timedelta(minutes=min_minutes)
                  ).isoformat(timespec="seconds")
        row = db.conn.execute(
            "SELECT id FROM expert_tasks WHERE user_id=? AND specialist=?"
            " AND task_type=? AND status IN ('pending','running')"
            " AND created_at >= ? LIMIT 1",
            (user_id, specialist, task_type, cutoff)).fetchone()
        if row:
            return None
    return db.create_expert_task(
        user_id, specialist, task_type, trigger,
        dict(input_refs or {}),
        dedup_key=_dedup_key(specialist, task_type, trigger, input_refs or {}),
        max_retries=max_retries)


def run_task(db, task: dict, llm=None) -> dict:
    """执行单个任务（pending → running → ready/failed）。

    确定性分析器抛出的 ValueError 视为输入问题（不重试）；其他异常按
    重试策略回到 pending，超限落 failed。
    """
    if task["status"] not in ("pending",):
        return {"task": task, "insight": None, "skipped": True}
    db.update_expert_task(task["user_id"], task["id"], status="running",
                          event="started")
    try:
        analyzer = _analyzer(task["task_type"])
        payload = analyzer(db, task["user_id"], task["input_refs"])
        insight = insight_service.create_insight(db, task["user_id"],
                                                 payload, task["id"])
        db.update_expert_task(task["user_id"], task["id"], status="ready",
                              insight_id=insight["id"], event="ready",
                              event_detail=f"洞察 {insight['id']}（置信度 "
                                           f"{insight['confidence']}）")
        return {"task": db.get_expert_task(task["user_id"], task["id"]),
                "insight": insight, "skipped": False}
    except ValueError as e:
        # 输入问题（记录不存在/无可分析内容）：重试没有意义
        db.update_expert_task(task["user_id"], task["id"], status="failed",
                              error_code="INPUT_INVALID", error=str(e),
                              event="failed", event_detail=f"输入问题：{e}")
        return {"task": db.get_expert_task(task["user_id"], task["id"]),
                "insight": None, "error": str(e), "skipped": False}
    except Exception as e:  # noqa: BLE001 失败要留痕（任务日志），不向上扩散
        retryable = task["retry_count"] < task["max_retries"]
        if retryable:
            db.update_expert_task(task["user_id"], task["id"], status="pending",
                                  bump_retry=True, error=str(e),
                                  event="retry",
                                  event_detail=f"第 {task['retry_count'] + 1} 次重试：{e}")
        else:
            db.update_expert_task(task["user_id"], task["id"], status="failed",
                                  error_code="EXECUTION_ERROR", error=str(e),
                                  event="failed", event_detail=str(e))
        return {"task": db.get_expert_task(task["user_id"], task["id"]),
                "insight": None, "error": str(e), "retry": retryable,
                "skipped": False}


def run_pending(db, user_id: str | None = None,
                limit: int = MAX_RUN_PER_CYCLE) -> list[dict]:
    """执行待办任务（先入先出）。确定性分析很快，可同步调用。"""
    sql = "SELECT * FROM expert_tasks WHERE status='pending'"
    params: list = []
    if user_id:
        sql += " AND user_id=?"
        params.append(user_id)
    rows = db.conn.execute(sql + " ORDER BY created_at LIMIT ?", params + [limit]
                           ).fetchall()
    results = []
    for row in rows:
        task = db._task_row(row)
        results.append(run_task(db, task))
    return results


def on_event(db, user_id: str, trigger: str, event_refs: dict,
             run_inline: bool = True) -> list[dict]:
    """业务事件入口：给订阅该事件的顾问派发任务。

    任何失败都被吞掉并留痕——专家分析是增值功能，绝不能让它的异常
    阻塞产生事件的普通记录（2.0 §11.4）。
    """
    created = []
    try:
        for specialist in registry.SPECIALISTS:
            for task_type in registry.subscribed(specialist, trigger):
                task = enqueue(db, user_id, specialist, task_type, trigger,
                               event_refs)
                if task and task["status"] == "pending":
                    created.append(task)
    except Exception:  # noqa: BLE001
        return created
    if run_inline and created:
        try:
            run_pending(db, user_id)
        except Exception:  # noqa: BLE001
            pass
        # 返回执行后的最新状态（而非入队时的快照）
        created = [db.get_expert_task(user_id, t["id"]) or t for t in created]
    return created


def recover_stale(db, max_running_minutes: int = STALE_MINUTES) -> list[dict]:
    """启动恢复：崩溃残留的 running 任务 → 重试或失败。"""
    recovered = []
    for task in db.stale_running_expert_tasks(max_running_minutes):
        if task["retry_count"] < task["max_retries"]:
            db.update_expert_task(task["user_id"], task["id"], status="pending",
                                  bump_retry=True, event="recovered",
                                  event_detail="服务重启：任务中断，重新排队")
        else:
            db.update_expert_task(task["user_id"], task["id"], status="failed",
                                  error_code="INTERRUPTED",
                                  error="服务重启：任务中断且重试次数用尽",
                                  event="failed",
                                  event_detail="重启中断，重试用尽")
        recovered.append(db.get_expert_task(task["user_id"], task["id"]))
    return recovered
