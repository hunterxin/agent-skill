"""Agent 主循环：通过 function calling 驱动 DeepSeek。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..prompts import render_subagent_prompt, render_system_prompt
from ..registry import SkillRegistry
from ..tools import TOOLS_SCHEMA, ToolDispatcher


class Agent:
    """围绕 chat.completions 兼容客户端的 function-calling 主循环。"""

    def __init__(
        self,
        client,
        registry: SkillRegistry,
        model: str,
        allowed_roots: Optional[List[Path]] = None,
        max_iters: int = 25,
        max_call_skill_depth: int = 3,
        debug: bool = False,
        _depth: int = 0,
    ):
        self.client = client
        self.registry = registry
        self.model = model
        self.allowed_roots = allowed_roots or [Path.cwd(), registry.root]
        self.max_iters = max_iters
        self.max_call_skill_depth = max_call_skill_depth
        self.debug = debug
        self._depth = _depth

    @staticmethod
    def _normalize_final_json(content: Optional[str]) -> str:
        """校验并规范化模型最终回复，确保对外只返回 JSON 对象字符串。"""
        raw = (content or "").strip()
        if not raw:
            raise ValueError("模型最终回复为空；期望 JSON 对象字符串")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"模型最终回复不是合法 JSON：{e}") from e

        if not isinstance(payload, dict):
            raise ValueError("模型最终回复必须是 JSON 对象")

        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _debug_print_messages(title: str, messages: List[Dict[str, Any]]) -> None:
        print(f"=== {title} ===")
        print(json.dumps(messages, ensure_ascii=False, indent=2))
        print(f"=== end {title} ===")

    # ---------------------------------------------------------------- 对外

    def run_once(self, user_input: str) -> str:
        """一次性调用：构造 system prompt，跑主循环，返回最终 assistant 文本。"""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": render_system_prompt(self.registry.catalog_for_prompt())},
            {"role": "user", "content": user_input},
        ]
        return self._loop(messages)

    def run_chat(self, history: List[Dict[str, Any]], user_input: str) -> str:
        """多轮对话：history 由调用方维护（不含 system 与当前这轮 user）。"""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": render_system_prompt(self.registry.catalog_for_prompt())},
            *history,
            {"role": "user", "content": user_input},
        ]
        reply = self._loop(messages)
        # 调用方负责把 user_input 和 reply 追加到自己的 history。
        return reply

    # ---------------------------------------------------------------- 内部

    def _loop(self, messages: List[Dict[str, Any]]) -> str:
        dispatcher = ToolDispatcher(
            registry=self.registry,
            allowed_roots=self.allowed_roots,
            call_skill_fn=self._call_skill,
        )
        for call_index in range(1, self.max_iters + 1):
            if self.debug:
                self._debug_print_messages(f"LLM call #{call_index} request messages", messages)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                response_format={"type": "json_object"},
            )
            choice = resp.choices[0]
            msg = choice.message

            tool_calls = getattr(msg, "tool_calls", None) or []

            # 追加 assistant 这一轮 —— 在 tool 消息之前必须先放它。
            assistant_turn: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if tool_calls:
                assistant_turn["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_turn)
            if self.debug:
                self._debug_print_messages(f"LLM call #{call_index} response messages", messages)

            if not tool_calls:
                return self._normalize_final_json(msg.content)

            for tc in tool_calls:
                result = dispatcher.dispatch(tc.function.name, tc.function.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        raise RuntimeError(f"agent 中止：达到 max_iters={self.max_iters}")

    def _call_skill(self, name: str, user_input: str) -> str:
        if self._depth + 1 >= self.max_call_skill_depth:
            return (
                f"call_skill 递归深度达到上限 ({self.max_call_skill_depth})；"
                "拒绝继续递归。"
            )
        skill = self.registry.load_full(name)
        sub_system = render_subagent_prompt(skill.name, skill.description, skill.body)
        sub_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": sub_system},
            {"role": "user", "content": user_input},
        ]
        sub = Agent(
            client=self.client,
            registry=self.registry,
            model=self.model,
            allowed_roots=self.allowed_roots,
            max_iters=self.max_iters,
            max_call_skill_depth=self.max_call_skill_depth,
            debug=self.debug,
            _depth=self._depth + 1,
        )
        return sub._loop(sub_messages)
