"""工具注册表：聚合 Python 实现以及 OpenAI tools schema。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from . import bash_tool, fs_tools, skill_tools


# 每个工具的 OpenAI / DeepSeek function-calling schema。
TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出所有可用的 skill（名称 + 简介）。需要刷新 catalog 时使用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "读取某个 skill 的完整 SKILL.md 正文以及捆绑脚本路径。在按 skill 的指令执行前必须先调用一次。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_skill",
            "description": "在磁盘上创建一个新的 skill。除非用户明确要求创建，否则调用前先与用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "kebab-case 标识符"},
                    "description": {"type": "string", "description": "一行简介"},
                    "body": {"type": "string", "description": "SKILL.md 正文 / 指令"},
                    "scripts": {
                        "type": "object",
                        "description": "可选的捆绑脚本：{文件名: 内容}",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["name", "description", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_skill",
            "description": "更新一个已存在的 skill。只传你想改的字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "body": {"type": "string"},
                    "scripts": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_skill",
            "description": "软删除一个 skill（移到 .trash/ 目录）。删除前先与用户确认。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_skill",
            "description": "把一个 skill 作为子 agent 调用。skill 正文会成为子 agent 的 system prompt，`input` 作为它的 user message。返回子 agent 的最终回复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "input": {"type": "string"},
                },
                "required": ["name", "input"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取 UTF-8 文本文件。只允许读 cwd 或 skills 目录下的路径。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入 UTF-8 文本文件（自动创建上级目录）。路径限制与 read_file 相同。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "执行 bash 命令。返回 {exit_code, stdout, stderr, timed_out}。用于运行 skill 捆绑的脚本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "number", "default": 60},
                },
                "required": ["command"],
            },
        },
    },
]


class ToolDispatcher:
    """把工具名字绑到对应的可调用对象上，并附带 registry 与允许的根目录。"""

    def __init__(
        self,
        registry,
        allowed_roots: List[Path],
        call_skill_fn: Callable[[str, str], str],
    ):
        self.registry = registry
        self.allowed_roots = allowed_roots
        self._call_skill_fn = call_skill_fn

    def dispatch(self, name: str, arguments_json: str) -> Any:
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as e:
            return {"error": f"参数 JSON 不合法：{e}"}
        if not isinstance(args, dict):
            return {"error": "参数必须是一个 JSON 对象"}

        try:
            if name == "list_skills":
                return skill_tools.list_skills(self.registry)
            if name == "load_skill":
                return skill_tools.load_skill(self.registry, **args)
            if name == "create_skill":
                return skill_tools.create_skill(self.registry, **args)
            if name == "update_skill":
                return skill_tools.update_skill(self.registry, **args)
            if name == "delete_skill":
                return skill_tools.delete_skill(self.registry, **args)
            if name == "call_skill":
                reply = self._call_skill_fn(args["name"], args["input"])
                return {"reply": reply}
            if name == "read_file":
                return {"content": fs_tools.read_file(args["path"], self.allowed_roots)}
            if name == "write_file":
                path = fs_tools.write_file(
                    args["path"], args["content"], self.allowed_roots
                )
                return {"ok": True, "path": path}
            if name == "run_bash":
                return bash_tool.run_bash(
                    args["command"],
                    cwd=args.get("cwd"),
                    timeout=float(args.get("timeout", 60)),
                )
        except Exception as e:  # noqa: BLE001 —— 当作 tool 错误返回给模型
            return {"error": f"{type(e).__name__}: {e}"}

        return {"error": f"未知工具: {name}"}
