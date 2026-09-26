"""Agent 对话循环（Phase 1 + R0 加固）

链路：用户输入 → ① 安全前置（确定性规则）
  → block：固定话术直接返回（不调 LLM），结构化记录 pain_flags
  → soft（否定/提问/病史/黄色）：注入安全提示后继续正常流程
  → 未建档：Onboarding 模式（update_profile / finish_onboarding）
  → 已建档：正常模式（load_knowledge / save_checkin / update_profile / get_plan /
                      get_review / get_adjustment_suggestions / apply_adjustment /
                      resolve_pain_flag）
  → 消息持久化到 messages 表

R0 加固（设计书 17.2）：
- R1：LLM 异常、工具参数 JSON 解析失败 → 降级回复，不打崩会话
- R2：上下文按字符预算截断（tool 调用与结果成对丢弃，避免孤儿消息）
- R3：输出侧正则兜底"X 天瘦 X 斤"类数字承诺
- D1 部分缓解：复盘数据异常时 system prompt 降级而不是崩溃（完整修复在 R2 阶段）
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from .db import Database
from .knowledge import LOAD_KNOWLEDGE_TOOL, KnowledgeBase
from .llm import LLMClient
from .onboarding import ONBOARDING_PROMPT, can_finish, missing_fields
from .plan import generate_plan, plan_to_text
from .profile import merge_patch, profile_summary
from .adjust import apply_adjustment, suggest_adjustments
from .review import review_context_text
from .safety import SafetyHit, check_red_flags, soft_note

MAX_TOOL_ROUNDS = 4
HISTORY_LIMIT = 20
MAX_CONTEXT_CHARS = 16000  # 约 8-10k token 的中文对话预算

_log = logging.getLogger("coach")
if not _log.handlers:
    _log_dir = Path(__file__).resolve().parent.parent / "data"
    _log_dir.mkdir(exist_ok=True)
    _log.addHandler(logging.FileHandler(_log_dir / "agent.log", encoding="utf-8"))
    _log.setLevel(logging.WARNING)

UPDATE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_profile",
        "description": "更新用户档案。用户提供个人信息、目标、伤病史时立即调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "object",
                    "description": "要合并的档案片段，如 {\"basic\": {\"age\": 25}}",
                }
            },
            "required": ["patch"],
        },
    },
}

FINISH_ONBOARDING_TOOL = {
    "type": "function",
    "function": {
        "name": "finish_onboarding",
        "description": "信息收集完成时调用，系统会校验并生成首份训练计划。",
        "parameters": {"type": "object", "properties": {}},
    },
}

SAVE_CHECKIN_TOOL = {
    "type": "function",
    "function": {
        "name": "save_checkin",
        "description": (
            "用户汇报训练/饮食/体重数据时调用，将打卡结构化落库。"
            "落库后再给用户自然语言的反馈。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["training", "diet", "body"],
                    "description": "training=训练打卡, diet=饮食记录, body=体重/体测",
                },
                "data": {
                    "type": "object",
                    "description": (
                        "training: {exercises:[{name,weight_kg,sets,reps,rpe}], note}；"
                        "diet: {meals:[{time,description}], hunger_level}；"
                        "body: {weight_kg, waist_cm}"
                    ),
                },
            },
            "required": ["type", "data"],
        },
    },
}

GET_PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "get_plan",
        "description": "查看用户当前生效的训练计划。",
        "parameters": {"type": "object", "properties": {}},
    },
}

GET_REVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "get_review",
        "description": (
            "获取用户的打卡数据分析（力量趋势/体重趋势/执行率/疲劳信号）。"
            "用户问进度、复盘、练得怎么样时调用。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

GET_ADJUSTMENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_adjustment_suggestions",
        "description": (
            "获取基于打卡数据的计划调整建议（规则引擎输出）。"
            "用户问'计划要不要变/怎么调整'或复盘时发现该调整时调用。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

APPLY_ADJUSTMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "apply_adjustment",
        "description": (
            "应用一项计划调整（生成新计划版本）。必须先经用户确认。"
            "action 只能是：increase_weight/hold_weight/decrease_weight/"
            "add_volume/deload/reduce_frequency"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "target": {"type": "string",
                           "description": "调整对象：动作名或'整体'或'计划频率'"},
                "reason": {"type": "string",
                           "description": "调整理由（会写入计划版本历史，可追溯）"},
            },
            "required": ["action", "target", "reason"],
        },
    },
}

RESOLVE_PAIN_FLAG_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_pain_flag",
        "description": (
            "用户确认此前的安全记录已处理（已就医/症状消失/确认无恙）时调用，"
            "关闭对应的安全跟进。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer",
                          "description": "要关闭的记录序号（不给则关闭全部待跟进）"},
                "note": {"type": "string", "description": "用户确认的原话摘要"},
            },
        },
    },
}

SYSTEM_TEMPLATE = """你是一位专业的私人健身教练 Agent——"独属于每个用户的教练"。

# 教练人格
- 专业但不讲术语，通俗但不失深度；关心用户，记得 TA 的情况和数据
- 不夸大承诺（禁止"X 天瘦 X 斤"），不做医疗诊断，超出边界引导就医
- 知识整理自公开健身内容（凯圣王/谭成义/陈石等博主体系），非官方立场

# 用户档案
{profile}

# 用户当前计划
{plan}

# 近期动态（打卡数据摘要，相关时引用）
{dynamic}

# 原则层（你的世界观，始终遵循）
{principles}

# 知识库索引（需要时用 load_knowledge 加载全文）
{knowledge_index}

# 工作方式
1. 识别意图：打卡汇报 / 知识提问 / 计划调整 / 身体不适 / 阶段复盘
2. 用户汇报训练、饮食、体重数据时，**先调用 save_checkin 落库**，再给人话反馈；
   汇报里夹杂感受或问题（如"卡住了""没进步"）也必须先落库，再分析
3. 回答专业知识前，从索引判断是否需要 load_knowledge；涉及饮食营养、动作技术、
   训练方法的具体问题，先 load_knowledge 加载对应文件再作答
4. 结合档案个性化回答——同一问题，不同档案答案不同
5. 用户提供新的个人信息（体重变化、伤病等）时调用 update_profile
6. 档案中有待跟进的安全记录时，自然地询问近况；用户确认无恙后调用 resolve_pain_flag 关闭
7. 调整计划只能通过 apply_adjustment 落库；工具返回成功前，绝不能说"计划已更新"
"""

# R3：输出侧数字承诺兜底（"30 天瘦 5 斤"类）
_PROMISE_RE = re.compile(
    r"[0-9一二两三四五六七八九十]+\s*(?:天|周|个?月|星期)\s*(?:内)?"
    r"[^，。！？!?\n]{0,8}(?:瘦|减|掉|增重|增肌|长)\s*\d+(?:\.\d+)?\s*(?:斤|公斤|千克|kg)"
)


def _sanitize_output(reply: str) -> str:
    """输出侧兜底：替换具体数字承诺（prompt 禁令的代码防线）"""
    if _PROMISE_RE.search(reply):
        _log.warning("输出命中数字承诺，已替换: %s", reply[:80])
        reply = _PROMISE_RE.sub("（进度因人而异，这里不做数字承诺）", reply)
    return reply


class CoachAgent:
    def __init__(self, user_id: str = "default", db_path=None) -> None:
        self.user_id = user_id
        self.db = Database(db_path) if db_path else Database()
        self.llm = LLMClient()
        self.kb = KnowledgeBase()
        self.profile = self.db.get_profile(user_id)
        self.messages: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ] + self.db.recent_messages(user_id, HISTORY_LIMIT)

    def _build_system_prompt(self) -> str:
        plan = self.db.get_active_plan(self.user_id)
        try:
            dynamic = review_context_text(self.db, self.user_id, plan)
        except Exception:
            _log.exception("复盘上下文构建失败，降级为空动态")
            dynamic = "（打卡数据读取异常，复盘暂缺）"
        return SYSTEM_TEMPLATE.format(
            profile=profile_summary(self.profile),
            plan=plan_to_text(plan) if plan else "（尚未生成，完成建档后生成）",
            dynamic=dynamic,
            principles=self.kb.l1_principles,
            knowledge_index=self.kb.l2_index,
        )

    def _refresh_system_prompt(self) -> None:
        self.messages[0] = {"role": "system", "content": self._build_system_prompt()}

    # ---- 主入口 ----
    def chat(self, user_input: str) -> str:
        # ① 安全前置（确定性规则，先于一切）
        hit = check_red_flags(user_input)
        if hit is not None and hit.mode == "block":
            self._record_pain_flag(user_input, hit)
            reply = hit.response
            self.db.add_message(self.user_id, "user", user_input)
            self.db.add_message(self.user_id, "assistant", reply)
            self.messages.append({"role": "user", "content": user_input})
            self.messages.append({"role": "assistant", "content": reply})
            return reply

        self.messages.append({"role": "user", "content": user_input})
        self.db.add_message(self.user_id, "user", user_input)

        if hit is not None:  # soft：记录（黄色档不记录）+ 注入安全提示
            if hit.tier != "yellow":
                self._record_pain_flag(user_input, hit)
            self.messages.append({"role": "system", "content": soft_note(hit)})

        mode = "normal" if self.profile.get("onboarding_done") else "onboarding"
        try:
            reply = self._loop(mode=mode)
        except Exception:
            _log.exception("对话循环异常")
            reply = "（教练这边出了点小状况，刚才那句没接住——换个说法再说一次？）"
        reply = _sanitize_output(reply)

        self.messages.append({"role": "assistant", "content": reply})
        self.db.add_message(self.user_id, "assistant", reply)
        return reply

    def _record_pain_flag(self, text: str, hit: SafetyHit) -> None:
        flags = self.profile.setdefault("conditions", {}).setdefault(
            "pain_flags", [])
        flags.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "text": text[:50],
            "kw": hit.keyword,
            "tier": hit.tier,
            "mode": hit.mode,
            "status": "open",
        })
        self.db.save_profile(self.user_id, self.profile)

    # ---- 对话-工具循环 ----
    def _loop(self, mode: str) -> str:
        if mode == "onboarding":
            tools = [UPDATE_PROFILE_TOOL, FINISH_ONBOARDING_TOOL]
            self.messages[0] = {
                "role": "system",
                "content": ONBOARDING_PROMPT.format(
                    missing="、".join(missing_fields(self.profile)) or "（已齐）"
                ),
            }
        else:
            tools = [
                LOAD_KNOWLEDGE_TOOL,
                SAVE_CHECKIN_TOOL,
                UPDATE_PROFILE_TOOL,
                GET_PLAN_TOOL,
                GET_REVIEW_TOOL,
                GET_ADJUSTMENTS_TOOL,
                APPLY_ADJUSTMENT_TOOL,
                RESOLVE_PAIN_FLAG_TOOL,
            ]
            self._refresh_system_prompt()

        for _ in range(MAX_TOOL_ROUNDS):
            self._trim_messages()
            result = self.llm.chat(self.messages, tools=tools)
            if not result["tool_calls"]:
                reply = result["content"]
                self.messages.append({"role": "assistant", "content": reply})
                return reply
            for tc in result["tool_calls"]:
                tool_result = self._handle_tool(tc, mode)
                self._append_tool_exchange(tc, tool_result)

        return "（思考超时，请换个方式描述你的问题）"

    def _trim_messages(self) -> None:
        """上下文预算控制：从最旧开始整条丢弃（tool 调用与其结果成对）。

        messages[0] 是 system prompt，永不丢弃。
        """
        msgs = self.messages

        def _size() -> int:
            return sum(len(m.get("content") or "") for m in msgs)

        while _size() > MAX_CONTEXT_CHARS and len(msgs) > 6:
            drop = 1
            if msgs[1].get("tool_calls"):
                while 1 + drop < len(msgs) and msgs[1 + drop].get("role") == "tool":
                    drop += 1
            del msgs[1:1 + drop]

    # ---- 工具处理 ----
    def _handle_tool(self, tc: dict, mode: str) -> str:
        name = tc["name"]
        try:
            args = json.loads(tc["arguments"] or "{}")
        except json.JSONDecodeError:
            _log.warning("工具参数 JSON 解析失败: %s %s", name, tc["arguments"][:100])
            return "工具参数解析失败（JSON 格式错误），请重新组织参数再调用一次。"

        if name == "load_knowledge":
            return self.kb.load(args.get("path", ""))

        if name == "update_profile":
            self.profile = merge_patch(self.profile, args.get("patch", {}))
            self.db.save_profile(self.user_id, self.profile)
            if mode == "onboarding":
                return "已保存。仍缺：" + (
                    "、".join(missing_fields(self.profile)) or "无，可以 finish_onboarding"
                )
            return "档案已更新。"

        if name == "finish_onboarding":
            ok, why = can_finish(self.profile)
            if not ok:
                return f"信息不足，不能结束建档。{why}。请继续询问用户。"
            self.profile["onboarding_done"] = True
            self.db.save_profile(self.user_id, self.profile)
            plan = generate_plan(self.profile)
            self.db.create_plan(self.user_id, plan)
            return "建档完成！已生成首份计划：\n" + plan_to_text(plan)

        if name == "save_checkin":
            self.db.add_checkin(
                self.user_id, args.get("type", "training"), args.get("data", {})
            )
            return "打卡已记录。"

        if name == "get_plan":
            plan = self.db.get_active_plan(self.user_id)
            return plan_to_text(plan) if plan else "当前没有生效的计划。"

        if name == "get_review":
            plan = self.db.get_active_plan(self.user_id)
            return review_context_text(self.db, self.user_id, plan)

        if name == "get_adjustment_suggestions":
            plan = self.db.get_active_plan(self.user_id)
            sugs = suggest_adjustments(self.db, self.user_id, plan)
            if not sugs:
                return "当前数据下没有需要调整的信号（或打卡数据不足）。"
            lines = ["规则引擎建议："]
            for s in sugs:
                lines.append(f"- [{s['action']}] {s['target']}：{s['reason']}")
            lines.append("请先向用户解释建议，用户确认后再调用 apply_adjustment。")
            return "\n".join(lines)

        if name == "apply_adjustment":
            plan = self.db.get_active_plan(self.user_id)
            if not plan:
                return "当前没有生效的计划。"
            try:
                new_plan = apply_adjustment(
                    plan, args.get("action", ""), args.get("target", ""),
                    args.get("reason", ""))
            except ValueError as e:
                return str(e)
            self.db.create_plan(self.user_id, new_plan)
            self._refresh_system_prompt()
            return f"计划已更新（新版本）。调整理由：{args.get('reason')}"

        if name == "resolve_pain_flag":
            flags = self.profile.get("conditions", {}).get("pain_flags", [])
            idx = args.get("index")
            closed = 0
            for i, f in enumerate(flags):
                if not (isinstance(f, dict) and f.get("status") == "open"):
                    continue
                if idx is not None and i != idx:
                    continue
                f["status"] = "resolved"
                f["resolved_at"] = datetime.now().isoformat(timespec="seconds")
                f["note"] = args.get("note", "")
                closed += 1
            if closed:
                self.db.save_profile(self.user_id, self.profile)
                self._refresh_system_prompt()
            return (f"已关闭 {closed} 条安全跟进记录。"
                    if closed else "没有待跟进的安全记录。")

        return f"未知工具：{name}"

    def _append_tool_exchange(self, tc: dict, result: str) -> None:
        self.messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }],
        })
        self.messages.append(
            {"role": "tool", "tool_call_id": tc["id"], "content": result}
        )
