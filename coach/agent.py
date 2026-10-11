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

import copy
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import Database, KD_VERDICTS, NOTE_TYPES
from .goals import SUPPORTED_GOALS, bump_goal_version, goal_label, goal_metrics, goal_transition_preview
from .budget import BudgetExceeded
from .claims import claim_store
from .cards import card_for_exercise, card_for_topic, serve_card
from .exercises import library as exercise_lib
from .knowledge import LOAD_KNOWLEDGE_TOOL, KnowledgeBase
from .llm import LLMClient
from .onboarding import (ONBOARDING_PROMPT, answers_health_question,
                         answers_injury_question, can_finish, missing_fields)
from .plan import generate_plan, plan_to_text, regenerate_plan_preserve
from .medical import training_permission
from .profile import HOLD_FIELDS, ensure_flag_ids, merge_patch, open_pain_flags, profile_summary
from .adjust import apply_adjustment, suggest_adjustments
from .review import build_summary, e1rm, last_weight, review_context_text
from .safety import SafetyHit, check_red_flags, soft_note
from .validate import coerce_checkin

MAX_TOOL_ROUNDS = 6
HISTORY_LIMIT = 20
# 对话历史的字符预算（约 8-10k token 中文）；system prompt 单独计算、不占此预算，
# 否则约 1.1 万字的 system 会把对话记忆挤到只剩几千字（与"记得你"的目标相反）
MAX_CONTEXT_CHARS = 16000
MAX_SYSTEM_CHARS = 20000  # system prompt 自身的预算上限（超出只告警不截断）
# 两步确认：建议生成后必须等用户下一轮说话才能 apply；超过 N 轮未确认自动过期
PENDING_EXPIRE_TURNS = 10
PENDING_EXPIRE_DAYS = 7

_log = logging.getLogger("coach")
if not _log.handlers:
    _log_dir = Path(os.getenv("COACH_LOG_DIR", str(Path(__file__).resolve().parent.parent / "data")))
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log.addHandler(logging.FileHandler(_log_dir / "agent.log", encoding="utf-8"))
    _log.setLevel(logging.WARNING)

UPDATE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_profile",
        "description": (
            "更新用户档案。用户提供个人信息、目标、伤病史时立即调用。"
            "注意：改写已确认的目标/训练频率/单次时长/场地/训练年限时，"
            "系统不会立即生效，而是暂存为待确认变更——先向用户澄清"
            "（是更正还是情况变化），确认后用 confirm_profile_change 落库。"
            "目标仅支持：减脂/增肌/力量/健康/塑形；用户只是了解其他目标的可能性时"
            "先讨论、不要提交 goal patch，明确决定变更时才提交"
            "（系统会给出取舍与过渡预览并要求确认）。"
        ),
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

CONFIRM_PROFILE_CHANGE_TOOL = {
    "type": "function",
    "function": {
        "name": "confirm_profile_change",
        "description": (
            "用户对暂存的档案变更做出答复后调用（change_id 见 update_profile "
            "返回的【需确认】提示）。accept=true：用户确认改为新值，落库并留档"
            "原值；accept=false：用户否认，保留原值。目标（goal）变更会同时"
            "作废旧目标下的待执行调整建议。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "change_id": {"type": "string"},
                "accept": {"type": "boolean",
                           "description": "true=用户确认改新值；false=用户否认，保留原值"},
            },
            "required": ["change_id", "accept"],
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
            "用户只说做了什么、没报重量组次时也要先落库"
            "（缺失字段留空即可），再在回复里追问补数据。"
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

GET_CHECKINS_TOOL = {
    "type": "function", "function": {
        "name": "get_checkins", "description": "读取最近打卡的记录ID、修订版本和完整数据；纠错前先调用。",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
}

CORRECT_CHECKIN_TOOL = {
    "type": "function", "function": {
        "name": "correct_checkin",
        "description": "用户明确指出打卡记错时修订原记录。先get_checkins；保留原值/日期，不能替别人改。训练记录传exercise_index定位一项动作，patch只包含纠正字段。",
        "parameters": {"type": "object", "properties": {
            "checkin_id": {"type": "integer"}, "expected_revision": {"type": "integer"},
            "exercise_index": {"type": "integer", "description": "训练记录里要改的动作下标，从0开始"},
            "patch": {"type": "object", "description": "如 {weight_kg:60} 或 {reps:8}；不能改ID、类型、训练日期"},
            "reason": {"type": "string"}, "evidence": {"type": "string", "description": "本轮用户原话的原样摘录"},
        }, "required": ["checkin_id", "expected_revision", "patch", "reason", "evidence"]},
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
            "打卡数据很少时也要调用，由规则引擎基于现有数据给候选，"
            "不要以'数据不足'为由跳过。"
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
                               "description": "不适描述；用户明确表示该不适消失时传空字符串清除，可选"},
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
            "必须附依据（用户原话或打卡内容），并标注来源性质 note_type："
            "fact=用户明确说过的自身情况；preference=用户表达的喜好或讨厌；"
            "observation=你从打卡数据里看出的规律；inference=你的推断。拿不准就选 inference。"
            "临时情况设 expires_days（到期不再当作当前情况）；长期情况可设 review_days（到期提醒复核）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "note": {"type": "string"},
                "evidence": {"type": "string",
                             "description": "依据：用户原话或打卡内容（必填）"},
                "note_type": {"type": "string",
                              "enum": ["fact", "preference", "observation", "inference"],
                              "description": "来源性质，拿不准选 inference"},
                "expires_days": {"type": "integer",
                                 "description": "可选，适用期限天数，不设则长期"},
                "review_days": {"type": "integer",
                                "description": "可选，复核时点天数：到期后先向用户确认仍适用"},
            },
            "required": ["note", "evidence"],
        },
    },
}

GET_EXERCISE_COACHING_TOOL = {
    "type": "function",
    "function": {
        "name": "get_exercise_coaching",
        "description": (
            "获取某个动作的教学要点：准备姿势、发力提示、常见错误、自检方法等"
            "（来自动作库与已审核的博主观点条目，带视频出处）。"
            "用户问某个动作怎么练、找不到发力感、动作细节或纠错时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "exercise": {"type": "string",
                             "description": "动作名（用户叫法即可，系统会自动归一）"},
            },
            "required": ["exercise"],
        },
    },
}

GET_COACHING_CARD_TOOL = {
    "type": "function",
    "function": {
        "name": "get_coaching_card",
        "description": (
            "获取某类训练/营养主题的已审核教练卡（发起人签核的完整表达，含适用条件、"
            "限制与分歧说明，带视频出处）。用户问蛋白质怎么吃、热量/减脂原理、睡眠恢复、"
            "训练强度(RPE/RM)、进阶加重、计划安排、恢复疲劳等一般性主题时调用；"
            "具体动作技术用 get_exercise_coaching。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "description": "主题关键词（如：蛋白质、热量、睡眠、恢复、加重、分化安排）"},
            },
            "required": ["topic"],
        },
    },
}

RECORD_KNOWLEDGE_DISCUSSION_TOOL = {
    "type": "function",
    "function": {
        "name": "record_knowledge_discussion",
        "description": (
            "用户分享健身观点/文章/视频结论并讨论后调用：把这次讨论存为私人记录，"
            "日后可回顾与复盘。必须附用户原话或对来源的描述。"
            "verdict 为讨论结论：consistent=与现有知识一致；conditional_useful=特定条件下有用；"
            "diverging=与现有知识有分歧；insufficient_evidence=证据不足待核；not_suitable=不适合此人。"
            "记录讨论不等于批准该知识用于处方；要据此调整计划须走常规建议-确认流程。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string",
                           "description": "用户原话或对来源的描述（必填）"},
                "topic": {"type": "string", "description": "讨论主题（必填）"},
                "verdict": {"type": "string",
                            "enum": ["consistent", "conditional_useful", "diverging",
                                     "insufficient_evidence", "not_suitable"]},
                "claimed_conditions": {"type": "string",
                                       "description": "该观点声称的适用条件"},
                "relation": {"type": "string",
                             "description": "与现有知识及个人情况的关系"},
                "followup": {"type": "string", "description": "后续待办"},
            },
            "required": ["source", "topic", "verdict"],
        },
    },
}

CLOSE_KNOWLEDGE_DISCUSSION_TOOL = {
    "type": "function",
    "function": {
        "name": "close_knowledge_discussion",
        "description": "某条讨论记录不再需要回顾时关闭（如用户已放弃该想法）。",
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
            },
            "required": ["item_id"],
        },
    },
}

GET_PRE_TRAINING_BRIEF_TOOL = {
    "type": "function",
    "function": {
        "name": "get_pre_training_brief",
        "description": (
            "训练开始前调用（26.5）：汇总已知约束（安全记录、过期待确认的笔记、"
            "进行中的尝试、疲劳信号）、本周计划与时间预算，决定照常、临时调整或暂停。"
            "只问当天必需的问题（当天状态/可用时间/部位感受），不重问建档已确认的信息。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

START_PERSONAL_TRIAL_TOOL = {
    "type": "function",
    "function": {
        "name": "start_personal_trial",
        "description": (
            "与用户约定一次小幅、可回退的个人尝试（26.3C）时调用。五要素缺一不可："
            "改变了什么（单一因素）、为什么尝试、观察什么、何时复盘、何时停止。"
            "涉及药物/极端手段/疼痛下硬练的内容不属于可自主尝试范围。"
            "同一时间只允许一个进行中的尝试；结果只作为带混杂因素的个人观察，仅适用于本人。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "change_desc": {"type": "string", "description": "改变了什么（单一因素）"},
                "reason": {"type": "string", "description": "为什么尝试（附依据）"},
                "observe": {"type": "string", "description": "观察什么（感受/执行/恢复/进展）"},
                "review_days": {"type": "integer", "description": "复盘时点（天数）"},
                "stop_rule": {"type": "string", "description": "何时停止（必填）"},
            },
            "required": ["change_desc", "reason", "observe", "stop_rule"],
        },
    },
}

END_PERSONAL_TRIAL_TOOL = {
    "type": "function",
    "function": {
        "name": "end_personal_trial",
        "description": (
            "尝试到复盘时点或提前停止时调用：记录观察结果与决定（keep 保持/stop 停止/"
            "adjust 调整后继续）。结果为带混杂因素的个人观察，仅适用于本人。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "trial_id": {"type": "integer"},
                "outcome": {"type": "string", "description": "观察结果（必填）"},
                "decision": {"type": "string",
                             "enum": ["keep", "stop", "adjust"],
                             "description": "保持/停止/调整后继续"},
            },
            "required": ["trial_id", "outcome", "decision"],
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
            "用户明确确认此前的安全记录已处理（已就医/症状消失/确认无恙）后调用，"
            "关闭对应的那一条安全跟进。必须先向用户确认、得到明确答复才允许调用；"
            "一次只关闭与用户结论对应的一条（传 flag_id），不得批量关闭。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "flag_id": {"type": "string",
                            "description": "提示中显示的稳定安全记录 ID，一次只关闭一条"},
                "note": {"type": "string", "description": "用户确认的原话摘要"},
            },
        },
    },
}

# C3 知识讨论：记录 ≠ 批准；C4 个人尝试：药物/极端手段不作为自主试验
_TRIAL_FORBIDDEN = re.compile(r"类固醇|禁药|药物辅助|激素替代|脱水剂|断食")

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

# 用户分享过的观点与讨论结论（私人讨论记录，不是已审核知识；引用时说明性质，不得据此直接改处方）
{knowledge_discussions}

# 有边界的个人尝试（结果为带混杂因素的个人观察，仅适用于本人，不是公共结论）
{personal_trials}

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
   汇报里夹杂感受或问题（如"卡住了""没进步"）也必须先落库，再分析；
   只报了"做了什么"没报重量组次时，同样先落库（缺失字段留空），
   再在回复里追问数字——不要因为数据不全就跳过落库
3. 回答专业知识前，从索引判断是否需要 load_knowledge；涉及饮食营养、动作技术、
   训练方法的具体问题，先 load_knowledge 加载对应文件再作答
4. 结合档案个性化回答——同一问题，不同档案答案不同
5. 用户提供新的个人信息（体重变化、伤病等）时调用 update_profile
6. 档案中有待跟进的安全记录时，自然地询问近况；**必须等用户明确确认**
   （已就医无恙/症状消失）后才调用 resolve_pain_flag，且只关闭与用户结论
   对应的那一条（传 flag_id）——用户没确认就不关，一次也不许多关
7. 用户问进度/复盘/练得怎么样时调用 get_review；问"计划要不要调整/怎么调"时**必须**
   调用 get_adjustment_suggestions——注入的近期动态只是提示，不能代替规则引擎；
   即使打卡数据很少也要先调用，让规则引擎基于现有数据给候选，
   数据不足时在回复中如实说明局限，不要跳过工具凭感觉给结论
8. 调整计划只能通过 apply_adjustment 落库（传 get_adjustment_suggestions 返回的
   suggestion_id，且须用户确认）；工具返回成功前，绝不能说"计划已更新"。
   涉及整体重排（伤病/场地/天数/动作 avoid 变化）时，系统会生成重排建议，
   同样走"先解释、用户下一轮确认、再 apply"的流程
9. 用户反馈动作感受（发力感/偏好/不适/想避开）时调用 record_exercise_feedback，
   必须附用户原话
10. 值得记住的定性观察（如"周三常加班""硬拉时下背先酸"）用 add_coach_note 记录，
    必须附依据并标注来源性质（用户明说=fact、喜好=preference、数据看出=observation、
    你的推断=inference，拿不准选 inference）；临时情况设 expires_days，长期情况可设
    review_days 到期复核；观察失效或被用户更正时用 close_coach_note 关闭
11. 用户问某个动作怎么练、找不到发力感或要做动作技术纠错时，先调用 get_exercise_coaching
    获取该动作的教学要点（返回若含【已审核教练卡】段落，以该段落为该动作的准绳表达，
    可照引并说明出处）；用户问蛋白质、热量减脂、睡眠恢复、进阶加重、计划安排等
    一般训练营养主题时，先调用 get_coaching_card 获取对应的已审核教练卡。
    没有素材/卡片覆盖的动作用教练自己的话讲
12. **博主点名纪律**：知识索引每条标了 [来源:xxx]。只有 transcript/article（一手）
    来源才能说"某博主讲过……"；general/third_party_distill 来源的内容，用教练自己
    的话讲，可泛称"整理自公开健身内容"，**不要把具体说法安在凯圣王/谭成义/陈石名下**
13. 用户说打卡记错（重量/次数/体重等），先 get_checkins 读取 ID 与 revision，
    再 correct_checkin 修订指定记录；这不是新一次训练，不能用 save_checkin 重复记账。
    纠错要附本轮原话。修订后旧调整建议作废；不要声称已经自动改变训练计划。
14. 单次可用时间变化写 resources.session_minutes；单纯喜欢/讨厌也要记录 preference，
    不必等到疼痛才调整。收到重排建议后解释时间取舍和选择理由，确认后再执行。
"""

# R3：输出侧数字承诺兜底（"30 天瘦 5 斤"类）
_PROMISE_RE = re.compile(
    r"[0-9一二两三四五六七八九十]+\s*(?:天|周|个?月|星期)\s*(?:内)?"
    r"[^，。！？!?\n]{0,8}(?:瘦|减|掉|增重|增肌|长)\s*\d+(?:\.\d+)?\s*(?:斤|公斤|千克|kg)"
)

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
        if ensure_flag_ids(self.profile):
            self.db.save_profile(user_id, self.profile)
        self._turn_tools: set[str] = set()
        self._turn_tool_results: list[str] = []
        self._turn_no: int = 0  # 仅供本地诊断；确认/过期使用持久化用户消息
        self.messages: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ] + self.db.recent_messages(user_id, HISTORY_LIMIT)

    def _build_system_prompt(self) -> str:
        plan = self._enforce_medical_permission()
        try:
            dynamic = review_context_text(self.db, self.user_id, plan)
        except Exception:
            _log.exception("复盘上下文构建失败，降级为空动态")
            dynamic = "（打卡数据读取异常，复盘暂缺）"
        return SYSTEM_TEMPLATE.format(
            profile=profile_summary(self.profile),
            exercise_feedback=self._exercise_feedback_text(),
            coach_notes=self._coach_notes_text(),
            knowledge_discussions=self._knowledge_discussions_text(),
            personal_trials=self._personal_trials_text(),
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

    _NOTE_TYPE_LABEL = {"fact": "用户明说", "preference": "用户偏好",
                        "observation": "数据观察", "inference": "教练推测"}

    def _coach_notes_text(self) -> str:
        notes = self.db.open_coach_notes(self.user_id)
        lines = []
        for n in notes:
            tag = self._NOTE_TYPE_LABEL.get(n.get("note_type") or "inference", "教练推测")
            due = "；⚠️ 已到复核时点，先向用户确认仍然适用" if n.get("due_review") else ""
            lines.append(f"- [{n['id']}|{tag}] {n['note']}"
                         f"（依据：{str(n['evidence'])[:40]}{due}）")
        stale = self.db.notes_for_reconfirm(self.user_id)
        if stale:
            lines.append("以下笔记已过适用期，不要当作当前情况使用；向用户确认后："
                         "仍适用就重新记录，不适用就 close_coach_note：")
            lines += [f"- [{n['id']}] {n['note']}（依据：{str(n['evidence'])[:40]}）"
                      for n in stale]
        return "\n".join(lines) if lines else "（暂无）"

    def _knowledge_discussions_text(self) -> str:
        rows = self.db.open_knowledge_discussions(self.user_id)
        if not rows:
            return "（暂无）"
        lines = ["以下为私人讨论记录，不是已审核知识；引用时说明性质，"
                 "要据此调整计划必须走常规建议-确认流程："]
        for r in rows:
            v = {"consistent": "与现有知识一致", "conditional_useful": "特定条件下有用",
                 "diverging": "与现有知识有分歧", "insufficient_evidence": "证据不足待核",
                 "not_suitable": "不适合此人"}.get(r["verdict"], r["verdict"])
            lines.append(f"- [{r['id']}|{v}] {r['topic']}：{str(r['source'])[:60]}"
                         + (f"（声称条件：{str(r['claimed_conditions'])[:40]}）"
                            if r.get("claimed_conditions") else "")
                         + (f"（待办：{r['followup']}）" if r.get("followup") else "")
                         + (f"（关联已审核卡：{r['related_card']}）"
                            if r.get("related_card") else ""))
        return "\n".join(lines)

    def _personal_trials_text(self) -> str:
        trials = self.db.personal_trials(self.user_id)
        if not trials:
            return "（暂无）"
        lines = ["以下为有边界的个人尝试记录（26.3C）：结果为带混杂因素的个人观察，"
                 "仅适用于本人，不是公共结论："]
        for t in trials:
            if t["status"] == "active":
                due = ("；⚠️ 复盘时点已到：与用户回顾并决定保持/调整/停止"
                       if t.get("due_review") else "")
                lines.append(f"- [尝试#{t['id']}|进行中] {t['change_desc']}"
                             f"（观察：{t['observe']}；停止条件：{t['stop_rule']}{due}）")
            else:
                lines.append(f"- [尝试#{t['id']}|已结束] {t['change_desc']} → {t['outcome']}"
                             f"（决定：{t['decision']}）")
        return "\n".join(lines)

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
        self._turn_no += 1
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

        if hit is not None:  # soft：按语境分级留痕 + 注入安全提示
            # 否定语境（"我没有胸闷"）不留记录——建档问答里必然出现，
            # 留了会污染每轮 prompt 和首份计划的注意项；
            # 提问/病史语境记 status=noted（已提醒，不进入待跟进）；
            # 黄色档不记录。
            if hit.tier != "yellow" and hit.reason != "negated":
                self._record_pain_flag(user_input, hit)
            self.messages.append({"role": "system", "content": soft_note(hit)})

        mode = "normal" if self.profile.get("onboarding_done") else "onboarding"
        try:
            reply = self._loop(mode=mode)
        except BudgetExceeded:
            raise
        except Exception:
            _log.exception("对话循环异常")
            reply = "（教练这边出了点小状况，刚才那句没接住——换个说法再说一次？）"
        reply = _sanitize_output(reply)
        reply = self._guard_plan_claim(reply)

        self.messages.append({"role": "assistant", "content": reply})
        self.db.add_message(self.user_id, "assistant", reply)
        return reply

    def _record_pain_flag(self, text: str, hit: SafetyHit) -> None:
        flags = self.profile.setdefault("conditions", {}).setdefault(
            "pain_flags", [])
        # block → open（待跟进）；soft（提问/病史）→ noted（已提醒，不跟进）
        status = "open" if hit.mode == "block" else "noted"
        flags.append({
            "flag_id": "flag-" + uuid.uuid4().hex,
            "at": datetime.now().isoformat(timespec="seconds"),
            "text": text[:50],
            "kw": hit.keyword,
            "tier": hit.tier,
            "mode": hit.mode,
            "status": status,
        })
        self.db.save_profile(self.user_id, self.profile)

    def _plan_snapshot(self) -> str:
        plan = self.db.get_active_plan(self.user_id)
        return json.dumps(plan, ensure_ascii=False, sort_keys=True)

    def _commit_plan(self, plan: dict, expected_plan_id: int) -> None:
        updated = copy.deepcopy(self.profile)
        # 每条建议都属于旧计划版本，计划改变后不得继续执行。
        updated["pending_adjustments"] = []
        self.db.create_plan(self.user_id, plan, profile=updated,
                            expected_plan_id=expected_plan_id)
        self.profile = updated

    def _enforce_medical_permission(self) -> dict | None:
        """新增限制立即停用旧处方；解除限制不自动恢复强度。"""
        record = self.db.get_active_plan_record(self.user_id)
        if not record:
            return None
        plan = record["content"]
        permission = training_permission(self.profile)
        if permission.allows_prescription:
            return plan
        if (plan.get("medical_status") == permission.status
                and plan.get("medical_evidence") == permission.evidence
                and not plan.get("schedule")):
            return plan
        restricted = generate_plan(self.profile)
        restricted["resume_plan_id"] = plan.get("resume_plan_id", record["id"])
        restricted["adjust_reason"] = permission.reason
        restricted["adjust_action"] = "medical_suspend"
        self._commit_plan(restricted, record["id"])
        return restricted

    def _new_suggestion(self, suggestion: dict, source: str, record: dict) -> dict:
        return {
            **suggestion, "id": "adj-" + uuid.uuid4().hex,
            "user_id": self.user_id, "source": source,
            "plan_id": record["id"], "plan_version": record["version"],
            "created_message_id": self.db.latest_user_message_id(self.user_id),
            "expires_at": (datetime.now(timezone.utc)
                           + timedelta(days=PENDING_EXPIRE_DAYS)).isoformat(),
        }

    def _pending_error(self, suggestion: dict, record: dict | None) -> str | None:
        # 遗留建议没有可靠的版本/消息依据，不能猜测它原来针对哪一版计划。
        if (suggestion.get("user_id") != self.user_id
                or suggestion.get("source") not in ("rule", "regenerate")
                or not record
                or suggestion.get("plan_id") != record["id"]
                or suggestion.get("plan_version") != record["version"]):
            return "建议对应的计划版本已失效或缺少版本依据，已作废，请重新获取建议"
        mid = suggestion.get("created_message_id")
        if not isinstance(mid, int) or mid < 0:
            return "建议缺少用户消息依据，已作废，请重新获取建议"
        try:
            expired = datetime.fromisoformat(suggestion["expires_at"]) <= datetime.now(timezone.utc)
        except (KeyError, TypeError, ValueError):
            return "建议缺少有效期依据，已作废，请重新获取建议"
        if expired or self.db.user_messages_after(self.user_id, mid) > PENDING_EXPIRE_TURNS:
            return "建议已过期，已作废，请重新获取建议"
        return None

    def _live_pending(self, record: dict) -> list[dict]:
        return [s for s in self.profile.get("pending_adjustments", [])
                if isinstance(s, dict) and not self._pending_error(s, record)]

    def _void_suggestions_citing(self, note_text: str) -> list[dict]:
        """失效传播（C1）：笔记关闭后，理由里引用该笔记的待确认建议一并作废。"""
        if not note_text:
            return []
        pending = self.profile.get("pending_adjustments") or []
        key = note_text[:12]
        kept, dropped = [], []
        for s in pending:
            (dropped if key in str(s.get("reason", "")) else kept).append(s)
        if dropped:
            self.profile["pending_adjustments"] = kept
            self.db.save_profile(self.user_id, self.profile)
        return dropped

    def _offer_regenerate(self, reason: str) -> str:
        """重排与规则建议共享身份/版本机制，但刷新规则不能覆盖重排。"""
        if not self.profile.get("onboarding_done"):
            return ""
        record = self.db.get_active_plan_record(self.user_id)
        if not record:
            return ""
        pending = self._live_pending(record)
        existing = next((s for s in pending if s["action"] == "regenerate_plan"), None)
        if existing and existing["reason"] == reason:
            self.profile["pending_adjustments"] = pending
            self.db.save_profile(self.user_id, self.profile)
            return f"（已有待确认重排建议 [{existing['id']}]，无需重复生成）"
        if existing:
            pending.remove(existing)
            reason = existing["reason"] + "；" + reason
        sug = self._new_suggestion({"action": "regenerate_plan", "target": "整体计划",
                                    "reason": reason}, "regenerate", record)
        pending.append(sug)
        self.profile["pending_adjustments"] = pending
        self.db.save_profile(self.user_id, self.profile)
        return (
            f"[{sug['id']}] regenerate_plan｜整体计划：检测到计划需要重排（{reason}）。"
            "请说明原因，等用户下一轮确认后再调用 apply_adjustment 执行；"
            "重排将遵守最新健康限制并保留兼容的处方重量。"
        )

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
        if ensure_flag_ids(self.profile):
            self.db.save_profile(self.user_id, self.profile)
        if mode == "onboarding":
            # 安全跟进不分模式：建档中被拦截的用户带回医生结论时也要能关闭
            tools = [UPDATE_PROFILE_TOOL, CONFIRM_PROFILE_CHANGE_TOOL,
                     FINISH_ONBOARDING_TOOL,
                     RESOLVE_PAIN_FLAG_TOOL]
            prompt = ONBOARDING_PROMPT.format(
                missing="、".join(missing_fields(self.profile)) or "（已齐）"
            )
            flags = open_pain_flags(self.profile)
            if flags:
                listing = "；".join(
                    f"[{f['flag_id']}] {f.get('kw', '?')}·{str(f.get('at', ''))[:10]}"
                    for f in flags)
                prompt += (
                    f"\n\n# ⚠️ 待跟进安全记录（{len(flags)} 条）\n{listing}\n"
                    "本轮先自然地问一句近况；用户明确表示已就医无恙或症状消失后，"
                    "调用 resolve_pain_flag 关闭对应那条（传 flag_id），"
                    "关闭后再继续建档流程。"
                )
            self.messages[0] = {"role": "system", "content": prompt}
        else:
            tools = [
                LOAD_KNOWLEDGE_TOOL,
                SAVE_CHECKIN_TOOL,
                GET_CHECKINS_TOOL,
                CORRECT_CHECKIN_TOOL,
                UPDATE_PROFILE_TOOL,
                CONFIRM_PROFILE_CHANGE_TOOL,
                GET_PLAN_TOOL,
                GET_REVIEW_TOOL,
                GET_ADJUSTMENTS_TOOL,
                APPLY_ADJUSTMENT_TOOL,
                RESOLVE_PAIN_FLAG_TOOL,
                RECORD_EXERCISE_FEEDBACK_TOOL,
                ADD_COACH_NOTE_TOOL,
                CLOSE_COACH_NOTE_TOOL,
                GET_EXERCISE_COACHING_TOOL,
                GET_COACHING_CARD_TOOL,
                RECORD_KNOWLEDGE_DISCUSSION_TOOL,
                CLOSE_KNOWLEDGE_DISCUSSION_TOOL,
                GET_PRE_TRAINING_BRIEF_TOOL,
                START_PERSONAL_TRIAL_TOOL,
                END_PERSONAL_TRIAL_TOOL,
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

        messages[0] 是 system prompt，永不丢弃，也**不占对话预算**——
        system（原则层+索引+计划+笔记）单独计算上限，16000 字符全部留给
        对话历史（否则 system 约 1.1 万字，对话记忆只剩几千字，和
        "记得你"的目标相反）。
        """
        msgs = self.messages
        if len(msgs[0].get("content") or "") > MAX_SYSTEM_CHARS:
            _log.warning("system prompt 超预算: %d 字符",
                         len(msgs[0]["content"]))

        def _size() -> int:
            return sum(len(m.get("content") or "") for m in msgs[1:])

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
            previous_health = copy.deepcopy(self.profile.get("conditions", {}).get("health_screen"))
            previous_resources = copy.deepcopy(self.profile.get("resources", {}))
            patch = args.get("patch", {})
            # G2 门槛（2026-09-29 收紧）：伤病史/健康筛查必须有真凭实据——
            # LLM 自附 *_evidence，或本轮用户原话能判定为真的在回答该问题；
            # 否则从 patch 中剔除该项（拒收），由 LLM 继续追问。
            # （原实现无条件用本轮用户消息回填，"别问了直接开始"也能过门槛）
            rejected: list[str] = []
            cond_patch = patch.get("conditions", {}) if isinstance(patch, dict) else {}
            if isinstance(cond_patch, dict) and (
                    "injuries" in cond_patch or "health_screen" in cond_patch):
                c = self.profile.get("conditions", {})
                last_user = next(
                    (m["content"] for m in reversed(self.messages)
                     if m.get("role") == "user"), "")
                if "injuries" in cond_patch \
                        and not (cond_patch.get("injuries_evidence") or "").strip() \
                        and not (c.get("injuries_evidence") or "").strip():
                    if answers_injury_question(last_user):
                        cond_patch["injuries_evidence"] = last_user[:80]
                    else:
                        cond_patch.pop("injuries", None)
                        cond_patch.pop("injuries_evidence", None)
                        rejected.append("伤病史")
                if "health_screen" in cond_patch \
                        and not (cond_patch.get("health_screen_evidence") or "").strip() \
                        and not (c.get("health_screen_evidence") or "").strip():
                    if answers_health_question(last_user):
                        cond_patch["health_screen_evidence"] = last_user[:80]
                    else:
                        cond_patch.pop("health_screen", None)
                        cond_patch.pop("health_screen_evidence", None)
                        rejected.append("健康筛查")
            # C2（26.4）：不支持的目标不接收——不把力量模板换个名字冒充专项计划
            gpatch = patch.get("goal") if isinstance(patch, dict) else None
            if isinstance(gpatch, dict) and gpatch.get("primary") not in (None, "") \
                    and gpatch["primary"] not in SUPPORTED_GOALS:
                rejected.append(
                    f"目标「{gpatch['primary']}」暂不在支持范围（减脂/增肌/力量/健康/塑形）——"
                    "如实告知用户当前能力边界，不要换个名字冒充专项计划")
                gpatch.pop("primary", None)
            self.profile, report = merge_patch(self.profile, patch,
                                               hold_fields=HOLD_FIELDS)
            self.db.save_profile(self.user_id, self.profile)
            notes = []
            if rejected:
                notes.append(
                    "【未保存】" + "、".join(rejected)
                    + "：必须以用户原话为依据（用户亲口回答过才算数），"
                      "本轮用户发言不构成有效回答。请直接向用户询问该项，"
                      "得到明确答复后再记录（并在 patch 里附上用户原话作 evidence）")
            if report["dropped"]:
                notes.append("已拒绝字段（系统字段或不在档案 Schema）："
                             + "、".join(report["dropped"]))
            notes += report["warnings"]
            if report.get("held"):
                # C1 收尾（26.2/26.4）：已确认信息被改写 → 暂存待确认，不静默生效
                entry = {
                    "id": "prf-" + uuid.uuid4().hex,
                    "changes": report["held"],
                    "created_message_id": self.db.latest_user_message_id(self.user_id),
                    "expires_at": (datetime.now(timezone.utc)
                                   + timedelta(days=PENDING_EXPIRE_DAYS)).isoformat(),
                }
                self.profile.setdefault("pending_profile_changes", []).append(entry)
                self.db.save_profile(self.user_id, self.profile)
                desc = "；".join(f"{h['field']}：{h['old']} → {h['new']}"
                                 for h in report["held"])
                notes.append(
                    f"【需确认，尚未生效】检测到已确认信息被改写：{desc}。"
                    "先向用户澄清这是更正还是情况变化；用户确认后调用 "
                    f"confirm_profile_change(change_id=\"{entry['id']}\", accept=true) "
                    "落库（原值自动留档），用户否认则 accept=false 保留原值。")
                gp = next((h for h in report["held"] if h["field"] == "goal.primary"), None)
                if gp:
                    preview = goal_transition_preview(gp["old"], gp["new"])
                    if preview:
                        notes.append(preview + "\n（把以上取舍与过渡预览转述给用户，再请其确认）")
            suffix = ("；" + "；".join(notes)) if notes else ""
            if mode == "onboarding":
                still = missing_fields(self.profile)
                if not still and can_finish(self.profile)[0]:
                    # 兜底：档案齐了就直接由代码收尾，不等 LLM（它有时会漏调）
                    return self._finalize_onboarding()
                return "已保存" + suffix + "。仍缺：" + (
                    "、".join(still) or "无，可以 finish_onboarding"
                )
            # 医疗约束收紧立即停用旧处方；放行恢复仍需用户确认重排。
            health_changed = self.profile.get("conditions", {}).get("health_screen") != previous_health
            plan_affecting = []
            if health_changed:
                self.profile["pending_adjustments"] = []
                self.db.save_profile(self.user_id, self.profile)
                self._enforce_medical_permission()
                permission = training_permission(self.profile)
                self._refresh_system_prompt()
                if not permission.allows_prescription:
                    return "档案已更新" + suffix + "。原训练处方已暂停：" + permission.reason
                plan_affecting.append("健康筛查或医嘱已更新，请确认新的训练计划")
            if isinstance(patch, dict):
                cond = patch.get("conditions") or {}
                res = patch.get("resources") or {}
                if "injuries" in cond and "伤病史" not in rejected:
                    plan_affecting.append("伤病有更新")
                current_resources = self.profile.get("resources", {})
                for key, label in (("location", "训练场地变了"), ("days_per_week", "每周训练天数变了"),
                                   ("session_minutes", "单次训练时间变了")):
                    if current_resources.get(key) != previous_resources.get(key):
                        plan_affecting.append(label)
            result = "档案已更新" + suffix + "。"
            if plan_affecting:
                extra = self._offer_regenerate("、".join(plan_affecting))
                if extra:
                    result += "\n" + extra
            return result

        if name == "confirm_profile_change":
            cid = args.get("change_id", "")
            pending = self.profile.get("pending_profile_changes") or []
            entry = next((e for e in pending if isinstance(e, dict) and e.get("id") == cid), None)
            if not entry:
                return f"没有待确认的档案变更「{cid}」。"
            try:
                expired = datetime.fromisoformat(entry["expires_at"]) <= datetime.now(timezone.utc)
            except (KeyError, TypeError, ValueError):
                expired = True
            pending.remove(entry)
            self.profile["pending_profile_changes"] = pending
            if expired:
                self.db.save_profile(self.user_id, self.profile)
                return "该档案变更已过期，未生效；请与用户重新确认后再次提交。"
            desc = "；".join(f"{h['field']}：{h['old']} → {h['new']}" for h in entry["changes"])
            if not args.get("accept"):
                self.db.save_profile(self.user_id, self.profile)
                return f"已保留原值（{desc.replace(' → ', ' 维持 ')}）。"
            patch: dict = {}
            goal_changed = False
            plan_affecting = []
            for h in entry["changes"]:
                section, key = h["field"].split(".", 1)
                patch.setdefault(section, {})[key] = h["new"]
                if section == "goal":
                    goal_changed = True
                    plan_affecting.append("目标已变更")
                elif section == "resources":
                    plan_affecting.append({"location": "训练场地变了",
                                           "days_per_week": "每周训练天数变了",
                                           "session_minutes": "单次训练时间变了"}.get(key, key + "已变更"))
                elif h["field"] == "experience.training_years":
                    plan_affecting.append("训练年限已更新")
            self.profile, _ = merge_patch(self.profile, patch)  # _history 记录旧值
            ver = None
            np = next((h["new"] for h in entry["changes"] if h["field"] == "goal.primary"), None)
            if goal_changed:
                # 26.4：目标变更后旧目标下的待执行建议失效，计划按新目标重新协商
                self.profile["pending_adjustments"] = []
                # C2：目标版本绑定 + 评价指标一致切换
                ver = bump_goal_version(self.profile)
                if np:
                    self.profile.setdefault("goal", {})["evaluation"] = goal_metrics(np)
                    self.profile["goal"]["confirmed_at"] = datetime.now().isoformat(
                        timespec="seconds")
            self.db.save_profile(self.user_id, self.profile)
            self._refresh_system_prompt()
            msg = f"档案已更新并留档原值：{desc}。"
            if goal_changed:
                msg += (f"目标版本已升级为 v{ver}"
                        + (f"，评价指标同步切换为「{self.profile['goal'].get('evaluation', '')}」"
                           if self.profile["goal"].get("evaluation") else "")
                        + "；旧目标下的待执行调整建议已作废；")
            if plan_affecting and self.profile.get("onboarding_done"):
                if ver and np:
                    extra = self._offer_regenerate(
                        f"目标已切换为{goal_label(np)}（目标版本 v{ver}），"
                        "按新目标与评价指标重排计划")
                else:
                    extra = self._offer_regenerate(
                        "、".join(plan_affecting) + "，建议按最新情况重排计划")
                if extra:
                    msg += extra
            return msg

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
                    # 动作 ID 是系统判定，不能信任模型附带的字段。
                    ex["exercise_id"] = None
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

        if name == "get_checkins":
            limit = max(1, min(int(args.get("limit", 10)), 20))
            return json.dumps(self.db.list_checkins(self.user_id, limit), ensure_ascii=False)

        if name == "correct_checkin":
            try:
                return self._correct_checkin(args)
            except (ValueError, TypeError, IndexError) as e:
                return f"打卡未修改：{e}"

        if name == "get_plan":
            plan = self._enforce_medical_permission()
            return plan_to_text(plan) if plan else "当前没有生效的计划。"

        if name == "get_review":
            plan = self._enforce_medical_permission()
            return review_context_text(self.db, self.user_id, plan)

        if name == "get_adjustment_suggestions":
            plan = self._enforce_medical_permission()
            record = self.db.get_active_plan_record(self.user_id)
            if not record:
                return "当前没有生效的计划。"
            if not training_permission(self.profile).allows_prescription:
                return "训练处方已暂停，不能建议加重或增加训练量；请先确认医疗许可。"
            existing = self._live_pending(record)
            if plan.get("medical_status", "allowed") != "allowed" and not any(
                    s["source"] == "regenerate" for s in existing):
                self._offer_regenerate("医疗许可已更新，恢复训练计划需确认")
                existing = self._live_pending(record)
            pending = [s for s in existing if s["source"] == "regenerate"]
            if plan.get("medical_status", "allowed") == "allowed":
                for s in suggest_adjustments(self.db, self.user_id, plan):
                    # 同一版计划、同一证据的重复查询保持身份与确认时点。
                    previous = next((p for p in existing if p["source"] == "rule"
                                     and all(p.get(k) == v for k, v in s.items())), None)
                    pending.append(previous or self._new_suggestion(s, "rule", record))
            self.profile["pending_adjustments"] = pending
            self.db.save_profile(self.user_id, self.profile)
            if not pending:
                return "当前数据下没有需要调整的信号（或打卡数据不足）。"
            lines = ["待确认调整建议："]
            for s in pending:
                lines.append(f"- [{s['id']}] {s['action']}｜{s['target']}：{s['reason']}")
            lines.append("请先向用户解释建议；用户下一轮确认后再调用 "
                         "apply_adjustment(suggestion_id=对应id)。")
            return "\n".join(lines)

        if name == "apply_adjustment":
            plan = self._enforce_medical_permission()
            record = self.db.get_active_plan_record(self.user_id)
            if not plan or not record:
                return "当前没有生效的计划。"
            if not training_permission(self.profile).allows_prescription:
                return "当前医疗许可不足，训练处方已暂停，不能执行训练调整。"
            sid = args.get("suggestion_id", "")
            pending = self.profile.get("pending_adjustments") or []
            sug = next((s for s in pending if s.get("id") == sid), None)
            if not sug:
                return f"没有待执行的建议「{sid}」，请重新获取建议并向用户确认。"
            error = self._pending_error(sug, record)
            if error:
                pending.remove(sug)
                self.db.save_profile(self.user_id, self.profile)
                return error
            if self.db.latest_user_message_id(self.user_id) <= sug["created_message_id"]:
                return "建议是本轮刚生成的，现在不能执行；请等用户下一轮明确确认。"
            if sug["action"] != "regenerate_plan" and (
                    plan.get("medical_status", "allowed") != "allowed"
                    or any(s["action"] == "regenerate_plan" for s in self._live_pending(record))):
                return "计划条件已有变化，请先确认重排，再获取适用于新计划的调整建议。"
            try:
                if sug["action"] == "regenerate_plan":
                    previous = plan
                    if plan.get("resume_plan_id"):
                        previous = self.db.get_plan_content(self.user_id, plan["resume_plan_id"]) or plan
                    new_plan = regenerate_plan_preserve(
                        self.profile, exercise_states=self.db.all_exercise_states(self.user_id),
                        old_plan=previous, reason=sug["reason"])
                else:
                    lw = None
                    if sug["action"] in ("increase_weight", "decrease_weight"):
                        lw = last_weight(self.db.list_checkins(self.user_id, 200), sug["target"])
                    new_plan = apply_adjustment(
                        plan, sug["action"], sug["target"], sug["reason"], last_weight=lw)
                self._commit_plan(new_plan, record["id"])
            except ValueError as e:
                return str(e)
            self._refresh_system_prompt()
            label = "新版本，整体重排" if sug["action"] == "regenerate_plan" else "新版本"
            return (f"计划已更新（{label}）：{sug['action']}｜{sug['target']}。"
                    f"调整理由：{sug['reason']}。旧版本建议已失效。")

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
            result = f"已记录「{official}」的动作反馈。"
            # 闭环：avoid / 报不适 → 当前计划可能还排着这个动作，生成重排建议
            if (args.get("status") == "avoid" or "preference" in args
                    or "feel" in args or "discomfort" in args):
                extra = self._offer_regenerate(
                    f"你对「{official}」的偏好或感受有更新，需要重新评估动作选择")
                if extra:
                    result += "\n" + extra
            return result

        if name == "get_exercise_coaching":
            ex_input = args.get("exercise", "")
            ex_id, official, _via = exercise_lib.normalize(ex_input)
            if not ex_id:
                self._log_unmatched_exercise(ex_input)
                return (f"未识别动作「{ex_input}」，已进待补队列。"
                        "可按通用知识回答，并请用户换个说法。")
            ex = exercise_lib.get(ex_id) or {}
            coaching = claim_store.format_coaching(ex)
            refs = ex.get("knowledge_refs") or []
            parts = [f"【{official}】教学要点（动作库 + 已审核博主素材）"]
            ex_card = card_for_exercise(ex_id)
            if ex_card:
                # 已批准核心卡优先：卡片是发起人审过的完整表达（§12），底层条目仍为 draft
                parts.append(serve_card(ex_card))
            elif coaching:
                parts.append(coaching)
            else:
                parts.append("（该动作暂无已审核的博主教学素材——"
                             "用教练自己的话按通用知识讲解，不要点名博主）")
            if refs:
                parts.append("关联知识文件（可用 load_knowledge 加载）："
                             + "、".join(refs))
            return "\n".join(parts)

        if name == "get_coaching_card":
            topic = (args.get("topic") or "").strip()
            card = card_for_topic(topic)
            if not card:
                return ("（暂无覆盖该主题的已审核教练卡——"
                        "用教练自己的话按通用知识回答，不要点名博主）")
            return serve_card(card)

        if name == "add_coach_note":
            note = (args.get("note") or "").strip()
            evidence = (args.get("evidence") or "").strip()
            note_type = (args.get("note_type") or "inference").strip()
            if note_type not in NOTE_TYPES:
                return ("note_type 必须是 fact/preference/observation/inference 之一"
                        "（用户明说=fact、喜好=preference、数据看出=observation、"
                        "你的推断=inference），未保存。")
            if not note or not evidence:
                return "教练笔记必须同时给 note 和 evidence（依据），未保存。"
            note_id = self.db.add_coach_note(
                self.user_id, note, evidence, args.get("expires_days"),
                note_type=note_type, review_days=args.get("review_days"))
            self._refresh_system_prompt()
            return f"教练笔记已记录（#{note_id}，{note_type}）。"

        if name == "close_coach_note":
            note_id = args.get("note_id")
            target = next((n for n in self.db.open_coach_notes(self.user_id)
                           if n["id"] == note_id), None)
            if self.db.close_coach_note(self.user_id, note_id):
                dropped = self._void_suggestions_citing((target or {}).get("note", ""))
                self._refresh_system_prompt()
                msg = f"教练笔记 #{note_id} 已关闭。"
                if dropped:
                    msg += ("\n（依赖该笔记依据的待确认建议已一并作废："
                            + "、".join(s["id"] for s in dropped)
                            + "；如仍需调整请基于最新情况重新获取建议。）")
                return msg
            return f"没有找到 open 状态的教练笔记 #{note_id}。"

        if name == "record_knowledge_discussion":
            source = (args.get("source") or "").strip()
            topic = (args.get("topic") or "").strip()
            verdict = (args.get("verdict") or "").strip()
            if not source or not topic:
                return "必须附用户原话或来源描述（source）与讨论主题（topic），未保存。"
            if verdict not in KD_VERDICTS:
                return ("verdict 必须是 consistent/conditional_useful/diverging/"
                        "insufficient_evidence/not_suitable 之一，未保存。")
            # C3 收尾：自动比对已审核卡——只提示身份，不因讨论修改卡片
            related = card_for_topic(topic)
            related_card = related["card_id"] if related else ""
            item_id = self.db.add_knowledge_discussion(
                self.user_id, source, topic,
                (args.get("claimed_conditions") or "").strip(), verdict,
                (args.get("relation") or "").strip(),
                (args.get("followup") or "").strip(), related_card=related_card)
            self._refresh_system_prompt()
            msg = (f"讨论已记录（#{item_id}）。这是私人讨论记录，不代表知识被批准；"
                   "如用户想据此调整计划，走常规建议-确认流程。")
            if related:
                msg += (f"\n（系统比对：该主题与已审核教练卡「{related['card_id']}」相关，"
                        "卡正文用 get_coaching_card 查询；讨论结论与卡一致与否都如实保留，"
                        "卡片不因讨论修改。）")
            return msg

        if name == "close_knowledge_discussion":
            item_id = args.get("item_id")
            if self.db.close_knowledge_discussion(self.user_id, item_id):
                self._refresh_system_prompt()
                return f"讨论记录 #{item_id} 已关闭。"
            return f"没有找到 active 状态的讨论记录 #{item_id}。"

        if name == "get_pre_training_brief":
            plan = self._enforce_medical_permission()
            permission = training_permission(self.profile)
            if not permission.allows_prescription:
                return ("【训练前简报】当前医疗状态：训练处方已暂停（" + permission.reason
                        + "）。训练前先与用户确认医疗状态；拿到明确许可前不安排训练，"
                          "恢复训练需走确认流程。")
            lines = ["【训练前简报】以下为已知约束，不要重问建档已确认的信息："]
            flags = open_pain_flags(self.profile)
            if flags:
                listing = "；".join(f"[{f.get('flag_id', '?')}] {f.get('kw', '?')}"
                                    for f in flags)
                lines.append(f"⚠️ 待跟进安全记录：{listing}——训练前先确认这些部位现状；"
                             "未缓解则避开相关动作或建议暂停")
            stale = self.db.notes_for_reconfirm(self.user_id)
            if stale:
                lines.append("已过适用期的笔记（先向用户确认是否仍适用）："
                             + "；".join(f"#{n['id']} {n['note']}" for n in stale))
            for t in self.db.personal_trials(self.user_id):
                if t["status"] == "active":
                    due = ("复盘时点已到，训练后与用户回顾"
                           if t.get("due_review") else "训练中留意")
                    lines.append(f"进行中的尝试 #{t['id']}：{t['change_desc']}"
                                 f"（观察：{t['observe']}）——{due}")
            s = build_summary(self.db, self.user_id, plan)
            if s["total_checkins"]:
                if s.get("days_since_last") is not None and s["days_since_last"] >= 7:
                    lines.append(f"距上次训练已 {s['days_since_last']} 天："
                                 "按复训处理，第一组次减量")
                rising = [n for n, d in s.get("rpe_drifts", {}).items() if d == "rising"]
                if rising:
                    lines.append(f"⚠️ RPE 漂移上升：{'、'.join(rising)}——"
                                 "今天不加重，优先动作质量")
            schedule = (plan or {}).get("schedule") or []
            if schedule:
                lines.append("本周计划：" + "；".join(
                    f"{d.get('day', '?')} {d.get('focus', '')}".strip()
                    for d in schedule) + "——问用户今天练哪次/什么时间可用")
            minutes = (self.profile.get("resources") or {}).get("session_minutes")
            if minutes:
                lines.append(f"已知时间预算：每次约 {minutes} 分钟；时间不足时按预算给取舍"
                             "（照常/减组/换重点），不擅自砍掉整个训练")
            lines.append("只问当天必需的问题（当天状态/可用时间/目标部位感受）；"
                         "疼痛或红旗按安全流程处理")
            return "\n".join(lines)

        if name == "start_personal_trial":
            change = (args.get("change_desc") or "").strip()
            reason = (args.get("reason") or "").strip()
            observe = (args.get("observe") or "").strip()
            stop_rule = (args.get("stop_rule") or "").strip()
            if not (change and reason and observe and stop_rule):
                return ("开始尝试必须同时说明：改变了什么、为什么尝试、观察什么、何时停止"
                        "（26.3C 缺一不可），未保存。")
            if _TRIAL_FORBIDDEN.search(change + "；" + reason):
                return ("这不属于可自主尝试的范围（26.3C）：涉及药物或极端手段的内容不做试验，"
                        "疼痛下也不硬练；如涉及健康问题请建议咨询专业人员。")
            try:
                trial_id = self.db.start_personal_trial(
                    self.user_id, change, reason, observe, stop_rule,
                    args.get("review_days"))
            except ValueError as e:
                return str(e)
            self._refresh_system_prompt()
            return (f"尝试已登记（#{trial_id}）：{change}。到复盘时点与用户回顾「{observe}」；"
                    "结果只作为带混杂因素的个人观察，仅适用于本人，不推广为公共结论。")

        if name == "end_personal_trial":
            trial_id = args.get("trial_id")
            outcome = (args.get("outcome") or "").strip()
            decision = (args.get("decision") or "adjust").strip()
            if not outcome:
                return "结束尝试必须记录观察结果（outcome）。"
            try:
                ok = self.db.end_personal_trial(self.user_id, trial_id, outcome, decision)
            except ValueError as e:
                return str(e)
            if not ok:
                return f"没有找到 active 状态的尝试 #{trial_id}。"
            self._refresh_system_prompt()
            return (f"尝试 #{trial_id} 已结束：{outcome}（决定：{decision}）。"
                    "这是带混杂因素的个人观察，仅适用于本人。")

        if name == "resolve_pain_flag":
            if ensure_flag_ids(self.profile):
                self.db.save_profile(self.user_id, self.profile)
            flags = self.profile.get("conditions", {}).get("pain_flags", [])
            open_list = [f for f in flags if isinstance(f, dict) and f.get("status") == "open"]
            if not open_list:
                return "没有待跟进的安全记录。"
            flag_id = args.get("flag_id")
            if flag_id is not None:
                target = next((f for f in open_list if f["flag_id"] == flag_id), None)
            elif args.get("index") is not None:
                # 兼容旧调用，只解释原始数组索引；新提示和工具只提供稳定 ID。
                idx = args["index"]
                target = flags[idx] if isinstance(idx, int) and 0 <= idx < len(flags) else None
                if target not in open_list:
                    target = None
            elif len(open_list) == 1:
                target = open_list[0]
            else:
                listing = "；".join(f"[{f['flag_id']}] {f.get('kw', '?')}" for f in open_list)
                return (f"有 {len(open_list)} 条待跟进的安全记录：{listing}。"
                        "请确认具体哪一条，再传 flag_id（不得批量关闭，也不要用显示 index）。")
            if target is None:
                return "指定的 ID/序号不是待跟进的安全记录，未做任何修改。"
            target["status"] = "resolved"
            target["resolved_at"] = datetime.now().isoformat(timespec="seconds")
            target["note"] = args.get("note", "")
            self.db.save_profile(self.user_id, self.profile)
            self._refresh_system_prompt()
            return f"已关闭 1 条安全跟进记录（{target.get('kw', '?')}）。"

        return f"未知工具：{name}"

    def _correct_checkin(self, args: dict) -> str:
        evidence = str(args.get("evidence") or "").strip()
        last_user = next((m["content"] for m in reversed(self.messages) if m.get("role") == "user"), "")
        if not evidence or evidence not in last_user:
            raise ValueError("必须附本轮用户的真实原话，不能代造纠错依据")
        old = self.db.get_checkin(self.user_id, args["checkin_id"])
        if not old:
            raise ValueError("记录不存在，请先 get_checkins 确认记录ID")
        patch = args.get("patch")
        if not isinstance(patch, dict) or not patch:
            raise ValueError("patch 必须包含要纠正的字段")
        data = copy.deepcopy(old["data"])
        allowed = {"body": {"weight_kg", "waist_cm", "note"},
                   "diet": {"meals", "hunger_level", "note"},
                   "training": {"name", "weight_kg", "sets", "reps", "rpe"}}
        if set(patch) - allowed.get(old["type"], set()):
            raise ValueError("不能修改记录ID、类型、日期或未知字段")
        if old["type"] == "training":
            idx = args.get("exercise_index")
            exs = data.get("exercises") or []
            if not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < len(exs):
                raise ValueError("请指定要纠正的 exercise_index")
            exs[idx].update(patch)
        else:
            data.update(patch)
        data, warnings = coerce_checkin(old["type"], data)
        if warnings:
            raise ValueError("；".join(warnings))
        for ex in data.get("exercises", []) if old["type"] == "training" else []:
            raw = ex.get("name", "")
            eid, official, _ = exercise_lib.normalize(raw)
            ex["exercise_id"] = eid
            if eid:
                ex["name"] = official
                if official != raw:
                    ex["name_raw"] = raw
            else:
                self._log_unmatched_exercise(raw)
        row = self.db.revise_checkin(self.user_id, old["id"], args["expected_revision"], data,
                                     str(args.get("reason") or ""), evidence)
        self.profile = self.db.get_profile(self.user_id)
        self._refresh_system_prompt()
        return (f"打卡 #{row['id']} 已修订为版本 {row['revision']}；原日期和修订历史保留，"
                "力量趋势与最佳值已重算，旧调整建议已作废。"
                "已生效的计划没有自动改动，如曾依据错误数据加重，需要重新评估。")

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
