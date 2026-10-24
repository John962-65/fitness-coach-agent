"""LLM 客户端封装（OpenAI 兼容协议）

- 支持任何 OpenAI 兼容接口（DeepSeek / 通义 / 月之暗面 / OpenAI 等）
- FAKE_LLM=1 时返回模拟响应，便于无 key 调试链路
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .budget import RequestBudget

_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}


def _drop_unusable_proxy_env() -> list[str]:
    """剔除 SDK 的 HTTP 客户端无法使用的代理变量，返回被移除的名字。

    代理软件常导出 ALL_PROXY=socks://…，httpx2 对未知 scheme 在构造
    客户端时即抛 ValueError；socks5/socks5h 还要求安装 socksio。
    只移除用不了的项，http/https 代理原样保留。
    """
    allowed = set(_PROXY_SCHEMES)
    try:
        import socksio  # noqa: F401
    except ImportError:
        allowed -= {"socks5", "socks5h"}
    removed: list[str] = []
    for var in ("ALL_PROXY", "all_proxy",
                "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        url = os.environ.get(var)
        if url is None:
            continue
        scheme = url.split("://", 1)[0].lower() if "://" in url else ""
        if scheme not in allowed:
            del os.environ[var]
            removed.append(var)
    return removed


class LLMClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")
        self.fake = os.getenv("FAKE_LLM", "0") == "1"

        self._client: Any = None
        self.budget = None
        if not self.fake:
            if not self.api_key:
                raise RuntimeError(
                    "未配置 LLM_API_KEY。请在 .env 中配置，或设 FAKE_LLM=1 使用模拟模式。"
                )
            from openai import OpenAI

            if os.getenv("LLM_BUDGET_PATH"):
                self.budget = RequestBudget(Path(os.environ["LLM_BUDGET_PATH"]),
                                            int(os.environ["LLM_MAX_REQUESTS"]))
            _drop_unusable_proxy_env()
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key,
                                  max_retries=0, timeout=60.0)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict:
        """发送对话请求，返回 {'content': str, 'tool_calls': [...]}"""
        if self.fake:
            return self._fake_chat(messages, tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        ticket = self.budget.reserve() if self.budget else None
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception:
            if ticket is not None:
                self.budget.finish(ticket, failed=True)
            raise
        if ticket is not None:
            usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
            self.budget.finish(ticket, usage=usage)
        msg = resp.choices[0].message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                )
        return {"content": msg.content or "", "tool_calls": tool_calls}

    # ---- 模拟模式：无 API key 时验证链路 ----
    def _fake_chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m["role"] == "user"),
            default=len(messages),
        )
        last_user = messages[last_user_idx]["content"] if messages else ""
        # 只统计本轮用户消息之后的工具调用（每轮允许新工具调用）
        called_tool = any(
            m["role"] == "tool" for m in messages[last_user_idx + 1:]
        )
        names = {t["function"]["name"] for t in tools} if tools else set()

        if not called_tool:
            # 打卡：含 kg 数字的训练汇报（优先于档案提取，避免误吞重量数据）
            if "save_checkin" in names and re.search(r"\d+\s*(kg|公斤)", last_user):
                m = re.search(r"(\D+?)(\d+)\s*(?:kg|公斤)", last_user)
                data = {"raw": last_user}
                if m:
                    data = {
                        "exercises": [{
                            "name": m.group(1).strip("，。, ")[:10] or "未知动作",
                            "weight_kg": float(m.group(2)),
                        }],
                        "raw": last_user,
                    }
                return self._call("save_checkin", {"type": "training", "data": data})

            # Onboarding：提取档案信息
            if "update_profile" in names:
                patch = self._extract_profile_patch(last_user)
                if patch:
                    return self._call("update_profile", {"patch": patch})
                no_injury = "伤" in last_user and any(
                    neg in last_user for neg in ["没有", "无", "没"]
                )
                # 模拟器也不能把“没有伤病”扩写成全部健康筛查阴性。
                screen = {}
                if re.search(r"(?:没有|无)(?:任何)?(?:心血管|心脏|高血压)", last_user):
                    screen["heart"] = "无"
                if re.search(r"(?:没有|无|未)(?:怀孕|备孕)", last_user):
                    screen["pregnancy"] = "无"
                if "不适用怀孕" in last_user:
                    screen["pregnancy"] = "不适用"
                if re.search(r"(?:没有|无|没)(?:长期)?(?:用药|吃药|服药)", last_user):
                    screen["medication"] = "无"
                if re.search(r"医生(?:没有|没)(?:嘱咐过)?限制运动", last_user):
                    screen["clearance"] = "无"
                if no_injury:
                    calls = [{
                        "id": "fake_1",
                        "name": "update_profile",
                        "arguments": json.dumps(
                            {"patch": {"conditions": {
                                "injuries": [],
                                "injuries_evidence": last_user[:80],
                                **({"health_screen": screen, "health_screen_evidence": last_user}
                                   if screen else {}),
                            }}}
                        ),
                    }]
                    if "finish_onboarding" in names:
                        calls.append({
                            "id": "fake_2",
                            "name": "finish_onboarding",
                            "arguments": "{}",
                        })
                    return {"content": "", "tool_calls": calls}
                if screen:
                    return self._call("update_profile", {"patch": {"conditions": {
                        "health_screen": screen, "health_screen_evidence": last_user}}})
                if "finish_onboarding" in names:
                    return {"content": "好的，请告诉我你的年龄、身高、体重？", "tool_calls": []}

            # 知识加载
            if "load_knowledge" in names and any(
                kw in last_user
                for kw in ["深蹲", "卧推", "硬拉", "减脂", "增肌", "平台期"]
            ):
                target = "30_nutrition/slow_cut_protocol.md"
                if "深蹲" in last_user:
                    target = "20_exercises/leg/squat_technique.md"
                elif "卧推" in last_user:
                    target = "20_exercises/chest/bench_press_technique.md"
                elif "硬拉" in last_user:
                    target = "20_exercises/leg/deadlift_variations.md"
                elif "平台期" in last_user:
                    target = "80_troubleshooting/fat_loss_plateau.md"
                return self._call("load_knowledge", {"path": target})

            # M2：协商改分化 → 提交待确认提案（FAKE 场景，E2E 用）
            if "propose_change" in names:
                structure = None
                for word, value in (("上下肢", "upper_lower"), ("全身", "full_body"),
                                     ("推拉腿", "ppl")):
                    if word in last_user and "改" in last_user:
                        structure = value
                        break
                if structure:
                    return self._call("propose_change", {
                        "target": "approach",
                        "operations": [{"op": "set_dimension",
                                        "dimension": "structure",
                                        "value": {"value": structure,
                                                  "note": "与用户协商"}}],
                        "reason": f"用户想把训练结构改为{structure}"})

            # M2：专业问题 → 咨询专家（确定性路由同后端）
            if "consult_specialists" in names:
                from .agents import route_question
                if route_question(last_user):
                    return self._call("consult_specialists", {"question": last_user})

        if called_tool:
            tool_texts = [m.get("content") for m in messages[last_user_idx + 1:]
                          if m.get("role") == "tool"]
            joined = "\n".join(str(t) for t in tool_texts)
            if '"consulted"' in joined:
                labels = []
                for m in re.findall(r'"label":\s*"([^"]+)"', joined):
                    if m not in labels:
                        labels.append(m)
                return {"content": "[FAKE_LLM] 已咨询专家：" + "、".join(labels)
                        + "。候选方案与适用条件已注入，分歧并列由用户选择。",
                        "tool_calls": []}

        return {
            "content": f"[FAKE_LLM] 收到：{last_user}（已结合档案与知识库生成回复）",
            "tool_calls": [],
        }

    @staticmethod
    def _call(name: str, args: dict) -> dict:
        return {
            "content": "",
            "tool_calls": [
                {"id": "fake_1", "name": name, "arguments": json.dumps(args)}
            ],
        }

    @staticmethod
    def _extract_profile_patch(text: str) -> dict:
        """从自然语言提取档案字段（仅模拟模式用）"""
        basic: dict[str, Any] = {}
        m = re.search(r"(\d{1,2})\s*岁", text)
        if m:
            basic["age"] = int(m.group(1))
        m = re.search(r"(\d{3})\s*(?:cm|厘米)", text)
        if m:
            basic["height_cm"] = int(m.group(1))
        m = re.search(r"(\d{2,3})\s*(?:kg|公斤|千克)", text)
        if m:
            basic["weight_kg"] = int(m.group(1))
        if "男" in text:
            basic["gender"] = "男"
        elif "女" in text:
            basic["gender"] = "女"

        patch: dict[str, Any] = {}
        if basic:
            patch["basic"] = basic
        if "减脂" in text or "减肥" in text:
            patch["goal"] = {"primary": "fat_loss"}
        elif "增肌" in text:
            patch["goal"] = {"primary": "muscle_gain"}
        m = re.search(r"练?\s*(\d)\s*天", text)
        if m:
            patch["resources"] = {"days_per_week": int(m.group(1))}
        return patch
