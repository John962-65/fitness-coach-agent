"""LLM 客户端封装（OpenAI 兼容协议）

- 支持任何 OpenAI 兼容接口（DeepSeek / 通义 / 月之暗面 / OpenAI 等）
- FAKE_LLM=1 时返回模拟响应，便于无 key 调试链路
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


class LLMClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")
        self.fake = os.getenv("FAKE_LLM", "0") == "1"

        self._client: Any = None
        if not self.fake:
            if not self.api_key:
                raise RuntimeError(
                    "未配置 LLM_API_KEY。请在 .env 中配置，或设 FAKE_LLM=1 使用模拟模式。"
                )
            from openai import OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

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

        resp = self._client.chat.completions.create(**kwargs)
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
                if no_injury:
                    calls = [{
                        "id": "fake_1",
                        "name": "update_profile",
                        "arguments": json.dumps(
                            {"patch": {"conditions": {
                                "injuries": [],
                                "health_screen": {"heart": "无", "pregnancy": "无",
                                                  "medication": "无", "clearance": "无"},
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
