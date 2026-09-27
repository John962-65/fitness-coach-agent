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
from .exercises import library as exercise_lib
from .knowledge import LOAD_KNOWLEDGE_TOOL, KnowledgeBase
from .llm import LLMClient
from .onboarding import ONBOARDING_PROMPT, can_finish, missing_fields
from .plan import generate_plan, plan_to_text
from .profile import merge_patch, profile_summary
from .adjust import apply_adjustment, suggest_adjustments
from .review import e1rm, last_weight, review_context_text
from .safety import SafetyHit, check_red_flags, soft_note
from .validate import coerce_checkin

MAX_TOOL_ROUNDS = 6
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
            "动作名用用户原话即可，系统会自动归一。"
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
                    "properties": {
                        "exercises": {
                            "type": "array",
                            "description": "training 必填。每个动作一条",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "weight_kg": {"type": "number"},
                                    "sets": {"type": "integer"},
                                    "reps": {"type": ["integer", "string"],
                                             "description": "每组次数，如 5 或 '5'"},
                                    "rpe": {"type": "number",
                                            "description": "自感强度 6-10，可选"},
                                },
                                "required": ["name"],
                            },
                        },
                        "meals": {
                            "type": "array",
                            "description": "diet 用",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "time": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                        "hunger_level": {"type": "string"},
                        "weight_kg": {"type": "number",
                                      "description": "body 用：体重公斤数（纯数字）"},
                        "waist_cm": {"type": "number"},
                        "note": {"type": "string"},
                    },
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
            "应用一项计划调整（生成新计划版本）。"
            "只能应用 get_adjustment_suggestions 返回过、且用户已确认的建议，"
            "传入对应的 suggestion_id。未获取建议或未经用户确认不得调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "suggestion_id": {
                    "type": "string",
                    "description": "get_adjustment_suggestions 返回的建议 id，如 adj-1",
                },
            },
            "required": ["suggestion_id"],
        },
    },
}

RECORD_EXERCISE_FEEDBACK_TOOL = {
    "type": "function",
    "function": {
        "name": "record_exercise_feedback",
        "description": (
            "用户反馈动作感受时调用：发力感、偏好、不适、想避开。"
            "如'保加利亚分腿蹲找不到臀的感觉''杠铃卧推肩膀不舒服'。"
            "必须附用户原话作依据（evidence）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exercise": {"type": "string", "description": "动作名（用户叫法即可）"},
                "preference": {"type": "integer",
                               "description": "-2 讨厌 … +2 最爱，可选"},
                "feel": {"type": "integer",
                         "description": "目标肌群发力感 0-3，可选"},
                "discomfort": {"type": "string",
                               "description": "不适描述，如'肩前侧不适'，可选"},
                "status": {"type": "string", "enum": ["active", "avoid", "learning"],
                           "description": "avoid=用户明确不想练或说'先不练'；"
                                          "learning=动作不熟还在学。可选"},
                "evidence": {"type": "string", "description": "用户原话（必填）"},
            },
            "required": ["exercise", "evidence"],
        },
    },
}

ADD_COACH_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "add_coach_note",
        "description": (
            "记录值得记住的定性观察（教练笔记），如'周三常加班''硬拉时下背先酸'。"
            "必须附依据（用户原话或打卡内容）。可设过期天数。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "evidence": {"type": "string",
                             "description": "依据：用户原话或打卡内容（必填）"},
                "expires_days": {"type": "integer",
                                 "description": "可选，过期天数，不设则长期"},
            },
            "required": ["note", "evidence"],
        },
    },
}

CLOSE_COACH_NOTE_TOOL = {
    "type": "function",
    "function": {
        "name": "close_coach_note",
        "description": "某条教练笔记不再适用时调用关闭（如'最近不加班了'）。",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer"},
            },
            "required": ["note_id"],
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

# 动作反馈（用户对具体动作的感受，回应时参考）
{exercise_feedback}

# 教练笔记（你的定性观察，相关时自然使用）
{coach_notes}

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
7. 用户问进度/复盘/练得怎么样时调用 get_review；问"计划要不要调整/怎么调"时**必须**
   调用 get_adjustment_suggestions——注入的近期动态只是提示，不能代替规则引擎
8. 调整计划只能通过 apply_adjustment 落库（传 get_adjustment_suggestions 返回的
   suggestion_id，且须用户确认）；工具返回成功前，绝不能说"计划已更新"
9. 用户反馈动作感受（发力感/偏好/不适/想避开）时调用 record_exercise_feedback，
   必须附用户原话
10. 值得记住的定性观察（如"周三常加班""硬拉时下背先酸"）用 add_coach_note 记录，
    必须附依据；观察失效时用 close_coach_note 关闭
11. **博主点名纪律**：知识索引每条标了 [来源:xxx]。只有 transcript/article（一手）
    来源才能说"某博主讲过……"；general/third_party_distill 来源的内容，用教练自己
    的话讲，可泛称"整理自公开健身内容"，**不要把具体说法安在凯圣王/谭成义/陈石名下**
"""

# R3：输出侧数字承诺兜底（"30 天瘦 5 斤"类）
_PROMISE_RE = re.compile(
    r"[0-9一二两三四五六七八九十]+\s*(?:天|周|个?月|星期)\s*(?:内)?"
    r"[^，。！？!?\n]{0,8}(?:瘦|减|掉|增重|增肌|长)\s*\d+(?:\.\d+)?\s*(?:斤|公斤|千克|kg)"
)

# 安全跟进的确定性自动关闭（S3 残留：LLM 不主动调 resolve_pain_flag）。
# 只在"医疗来源 + 明确无恙结论"同时出现、且整句不是疑问时才关——方向从紧。
_MED_SOURCE_RE = re.compile(r"医院|医生|心电图|体检|检查过|拍片|核磁|CT")
_MED_CLEAR_RE = re.compile(r"没事|无碍|没有问题|没问题|正常|休息[好一]+段|可以.*再练")
_MED_QUESTION_RE = re.compile(r"[？?]|吗[。！.？]?$|要不要|是不是该")

# A6 输出侧护栏：未落库却声称计划已改
_PLAN_CLAIM_STRONG = re.compile(r"计划[^。！？\n]{0,6}已(?:经)?(?:更新|调整|生效|改好)")
_PLAN_CLAIM_SOFT = re.compile(r"(?:已落库|已更新|已调整|已生效|改好了|加好了|调好了|搞定)")


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
        self._turn_tools: set[str] = set()
        self._turn_tool_results: list[str] = []
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
            exercise_feedback=self._exercise_feedback_text(),
            coach_notes=self._coach_notes_text(),
            plan=plan_to_text(plan) if plan else "（尚未生成，完成建档后生成）",
            dynamic=dynamic,
            principles=self.kb.l1_principles,
            knowledge_index=self.kb.l2_index,
        )

    def _exercise_feedback_text(self) -> str:
        rows = self.db.exercise_feedback_rows(self.user_id)
        if not rows:
            return "（暂无）"
        lines = []
        for r in rows:
            info = exercise_lib.get(r["exercise_id"]) or {}
            name = info.get("name") or r["exercise_id"]
            parts = []
            if r.get("status"):
                parts.append({"active": "在练", "avoid": "避开", "learning": "学习中"}
                             .get(r["status"], r["status"]))
            if r.get("feel") is not None:
                parts.append(f"发力感 {r['feel']}/3")
            if r.get("preference") is not None:
                parts.append(f"偏好 {r['preference']:+d}")
            if r.get("discomfort"):
                parts.append(f"不适：{r['discomfort']}")
            if r.get("best_e1rm"):
                parts.append(f"最佳 e1RM {r['best_e1rm']}kg")
            lines.append(f"- {name}：{'，'.join(parts)}"[:120])
        return "\n".join(lines)

    def _coach_notes_text(self) -> str:
        notes = self.db.open_coach_notes(self.user_id)
        if not notes:
            return "（暂无）"
        return "\n".join(
            f"- [{n['id']}] {n['note']}（依据：{str(n['evidence'])[:40]}）"
            for n in notes
        )

    def _refresh_system_prompt(self) -> None:
        self.messages[0] = {"role": "system", "content": self._build_system_prompt()}

    def _finalize_onboarding(self) -> str:
        """收尾建档（幂等）：档案齐→生成计划→定级回写（G3）。可被
        finish_onboarding 工具或"档案齐了"的兜底路径调用，重复调用不产生新版本。"""
        if self.profile.get("onboarding_done"):
            plan = self.db.get_active_plan(self.user_id)
            if plan:
                return "建档已完成，当前计划：\n" + plan_to_text(plan)
        self.profile["onboarding_done"] = True
        plan = generate_plan(self.profile,
                             exercise_states=self.db.all_exercise_states(self.user_id))
        # G3：定级是系统字段，由代码回写，保证档案与计划一致
        self.profile.setdefault("experience", {})["level"] = plan["level"]
        self.db.save_profile(self.user_id, self.profile)
        self.db.create_plan(self.user_id, plan)
        self._refresh_system_prompt()
        return "建档完成！已生成首份计划：\n" + plan_to_text(plan)

    # ---- 主入口 ----
    def chat(self, user_input: str) -> str:
        self._turn_tools = set()
        self._turn_tool_results = []
        self._plan_before = self._plan_snapshot()
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
        reply = self._guard_plan_claim(reply)
        reply = self._maybe_auto_resolve_flags(user_input, reply)

        self.messages.append({"role": "assistant", "content": reply})
        self.db.add_message(self.user_id, "assistant", reply)
        return reply

    def _maybe_auto_resolve_flags(self, user_input: str, reply: str) -> str:
        """用户带回医疗方"无恙"结论且本轮没调 resolve_pain_flag 时，
        代码直接关闭安全记录（S3 确定性兜底；话术明确告知用户）。"""
        flags = self.profile.get("conditions", {}).get("pain_flags", [])
        open_flags = [f for f in flags
                      if isinstance(f, dict) and f.get("status") == "open"]
        if not open_flags or "resolve_pain_flag" in self._turn_tools:
            return reply
        if not (_MED_SOURCE_RE.search(user_input)
                and _MED_CLEAR_RE.search(user_input)
                and not _MED_QUESTION_RE.search(user_input)):
            return reply
        now = datetime.now().isoformat(timespec="seconds")
        for f in open_flags:
            f["status"] = "resolved"
            f["resolved_at"] = now
            f["note"] = f"自动关闭依据（用户原话）：{user_input[:80]}"
        self.db.save_profile(self.user_id, self.profile)
        self._refresh_system_prompt()
        _log.warning("安全记录已按用户带回的医疗结论自动关闭: %s", user_input[:50])
        return reply + (
            "\n\n（我已把你带回的医生结论记录在案，之前的安全跟进已关闭。"
            "如果症状再有反复，随时告诉我，我们立刻重新记录。）")

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

    def _plan_snapshot(self) -> str:
        plan = self.db.get_active_plan(self.user_id)
        return json.dumps(plan, ensure_ascii=False, sort_keys=True)

    def _guard_plan_claim(self, reply: str) -> str:
        """叙述-执行一致性护栏（A6 输出侧兜底）：
        回复声称计划已改，但本轮计划内容其实没变 → 追加更正。
        强计划声称一律拦；软完成声称（已落库/搞定）仅在还有待执行建议时拦，
        避免误伤"档案已更新""打卡已落库"这类与计划无关的措辞。"""
        if self._plan_snapshot() != self._plan_before:
            return reply  # 计划确实变了（apply_adjustment 生效），放行
        strong = _PLAN_CLAIM_STRONG.search(reply)
        soft = (_PLAN_CLAIM_SOFT.search(reply)
                and self.profile.get("pending_adjustments")
                and re.search(r"(计划|方案|重量|下次|加重|减重|组数|容量|\d+\s*kg)", reply))
        if not (strong or soft):
            return reply
        _log.warning("未落库的计划更新声称: %s", reply[:60])
        return reply + (
            "\n\n（更正在此：以上是调整**建议**的说明，还没有写进你的计划"
            "——确认要执行的话说一声，我立刻应用。）"
        )

    def _log_unmatched_exercise(self, raw_name: str) -> None:
        """未识别动作队列（设计书 20.4：不静默丢弃，由发起人补别名）"""
        path = self.db.path.parent / "unmatched_exercises.jsonl"
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "at": datetime.now().isoformat(timespec="seconds"),
                    "user_id": self.user_id, "raw": raw_name,
                }, ensure_ascii=False) + "\n")
        except OSError:
            _log.warning("未识别动作队列写入失败: %s", raw_name)

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
                RECORD_EXERCISE_FEEDBACK_TOOL,
                ADD_COACH_NOTE_TOOL,
                CLOSE_COACH_NOTE_TOOL,
            ]
            self._refresh_system_prompt()

        for round_i in range(MAX_TOOL_ROUNDS):
            self._trim_messages()
            # 最后一轮强制纯文本回复，保证用户一定能拿到话（不再有"思考超时"）
            result = self.llm.chat(
                self.messages,
                tools=tools if round_i < MAX_TOOL_ROUNDS - 1 else None)
            if not result["tool_calls"]:
                reply = result["content"]
                self.messages.append({"role": "assistant", "content": reply})
                return reply
            for tc in result["tool_calls"]:
                self._turn_tools.add(tc["name"])
                tool_result = self._handle_tool(tc, mode)
                self._append_tool_exchange(tc, tool_result)

        return "（刚才那轮处理卡住了，换个说法再说一次？）"

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
            result = self.kb.load(args.get("path", ""))
            # 9.4 检索质量保障：加载日志，事后审计"找得准不准"
            try:
                last_user = next(
                    (m["content"] for m in reversed(self.messages)
                     if m.get("role") == "user"), "")
                with (self.db.path.parent / "knowledge_loads.jsonl").open(
                        "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "at": datetime.now().isoformat(timespec="seconds"),
                        "user_id": self.user_id,
                        "path": args.get("path", ""),
                        "question": last_user[:60],
                    }, ensure_ascii=False) + "\n")
            except OSError:
                pass
            return result

        if name == "update_profile":
            patch = args.get("patch", {})
            self.profile, report = merge_patch(self.profile, patch)
            # G2 兜底：没附原话时，用触发本条的用户消息回填（用户原话本就是最好的依据）
            cond_patch = patch.get("conditions", {}) if isinstance(patch, dict) else {}
            if isinstance(cond_patch, dict) and (
                    "injuries" in cond_patch or "health_screen" in cond_patch):
                c = self.profile.setdefault("conditions", {})
                last_user = next(
                    (m["content"] for m in reversed(self.messages)
                     if m.get("role") == "user"), "")
                if "injuries" in cond_patch \
                        and not (c.get("injuries_evidence") or "").strip():
                    c["injuries_evidence"] = last_user[:80]
                if "health_screen" in cond_patch \
                        and not (c.get("health_screen_evidence") or "").strip():
                    c["health_screen_evidence"] = last_user[:80]
            self.db.save_profile(self.user_id, self.profile)
            notes = []
            if report["dropped"]:
                notes.append("已拒绝字段（系统字段或不在档案 Schema）："
                             + "、".join(report["dropped"]))
            notes += report["warnings"]
            suffix = ("；" + "；".join(notes)) if notes else ""
            if mode == "onboarding":
                still = missing_fields(self.profile)
                if not still and can_finish(self.profile)[0]:
                    # 兜底：档案齐了就直接由代码收尾，不等 LLM（它有时会漏调）
                    return self._finalize_onboarding()
                return "已保存" + suffix + "。仍缺：" + (
                    "、".join(still) or "无，可以 finish_onboarding"
                )
            return "档案已更新" + suffix + "。"

        if name == "finish_onboarding":
            ok, why = can_finish(self.profile)
            if not ok:
                return f"信息不足，不能结束建档。{why}。请继续询问用户。"
            return self._finalize_onboarding()

        if name == "save_checkin":
            ctype = args.get("type", "training")
            data, warnings = coerce_checkin(ctype, args.get("data", {}))
            notes = list(warnings)
            if ctype == "training":
                for ex in data.get("exercises", []):
                    raw_name = ex.get("name", "")
                    ex_id, official, _via = exercise_lib.normalize(raw_name)
                    if ex_id:
                        ex["exercise_id"] = ex_id
                        if official != raw_name:
                            ex["name_raw"] = raw_name
                        ex["name"] = official
                        self.db.update_exercise_state(
                            self.user_id, ex_id,
                            ex.get("weight_kg"), ex.get("rpe"),
                            e1rm(ex.get("weight_kg"), ex.get("reps")))
                    else:
                        self._log_unmatched_exercise(raw_name)
                        notes.append(
                            f"未识别动作「{raw_name}」：已按原名记录并进入待补队列")
            self.db.add_checkin(self.user_id, ctype, data)
            suffix = ("；" + "；".join(notes)) if notes else ""
            return "打卡已记录" + suffix + "。"

        if name == "get_plan":
            plan = self.db.get_active_plan(self.user_id)
            return plan_to_text(plan) if plan else "当前没有生效的计划。"

        if name == "get_review":
            plan = self.db.get_active_plan(self.user_id)
            return review_context_text(self.db, self.user_id, plan)

        if name == "get_adjustment_suggestions":
            plan = self.db.get_active_plan(self.user_id)
            sugs = suggest_adjustments(self.db, self.user_id, plan)
            # A6 两步确认：建议带 id 落 pending，apply 只接受 pending 里的 id
            pending = [{"id": f"adj-{i + 1}", **s} for i, s in enumerate(sugs)]
            self.profile["pending_adjustments"] = pending
            self.db.save_profile(self.user_id, self.profile)
            if not sugs:
                return "当前数据下没有需要调整的信号（或打卡数据不足）。"
            lines = ["规则引擎建议："]
            for s in pending:
                lines.append(f"- [{s['id']}] {s['action']}｜{s['target']}：{s['reason']}")
            lines.append("请先向用户解释建议；用户确认后调用 "
                         "apply_adjustment(suggestion_id=对应id)。")
            return "\n".join(lines)

        if name == "apply_adjustment":
            plan = self.db.get_active_plan(self.user_id)
            if not plan:
                return "当前没有生效的计划。"
            sid = args.get("suggestion_id", "")
            pending = self.profile.get("pending_adjustments") or []
            sug = next((s for s in pending if s.get("id") == sid), None)
            if not sug:
                return (
                    f"没有待执行的建议「{sid}」。请先用 get_adjustment_suggestions "
                    "获取建议并向用户确认，再传入对应的 suggestion_id。"
                )
            lw = None
            if sug["action"] in ("increase_weight", "decrease_weight"):
                lw = last_weight(
                    self.db.list_checkins(self.user_id, 200), sug["target"])
            try:
                new_plan = apply_adjustment(
                    plan, sug["action"], sug["target"], sug["reason"],
                    last_weight=lw)
            except ValueError as e:
                return str(e)
            self.db.create_plan(self.user_id, new_plan)
            pending.remove(sug)
            self.db.save_profile(self.user_id, self.profile)
            self._refresh_system_prompt()
            return (f"计划已更新（新版本）：{sug['action']}｜{sug['target']}。"
                    f"调整理由：{sug['reason']}")

        if name == "record_exercise_feedback":
            ex_input = args.get("exercise", "")
            ex_id, official, _via = exercise_lib.normalize(ex_input)
            if not ex_id:
                self._log_unmatched_exercise(ex_input)
                return (f"未识别动作「{ex_input}」，已进待补队列；"
                        "反馈未保存。可请用户换个说法或稍后再记。")
            evidence = (args.get("evidence") or "").strip()
            if not evidence:
                return "缺 evidence：动作反馈必须附用户原话作依据，未保存。"
            self.db.record_exercise_feedback(
                self.user_id, ex_id,
                preference=args.get("preference"),
                feel=args.get("feel"),
                discomfort=args.get("discomfort"),
                status=args.get("status"),
                evidence=evidence,
            )
            self._refresh_system_prompt()
            return f"已记录「{official}」的动作反馈。"

        if name == "add_coach_note":
            note = (args.get("note") or "").strip()
            evidence = (args.get("evidence") or "").strip()
            if not note or not evidence:
                return "教练笔记必须同时给 note 和 evidence（依据），未保存。"
            note_id = self.db.add_coach_note(
                self.user_id, note, evidence, args.get("expires_days"))
            self._refresh_system_prompt()
            return f"教练笔记已记录（#{note_id}）。"

        if name == "close_coach_note":
            note_id = args.get("note_id")
            if self.db.close_coach_note(self.user_id, note_id):
                self._refresh_system_prompt()
                return f"教练笔记 #{note_id} 已关闭。"
            return f"没有找到 open 状态的教练笔记 #{note_id}。"

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
        self._turn_tool_results.append(result)
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
