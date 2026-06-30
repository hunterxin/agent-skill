"""共享的 pytest fixture 以及伪造的 DeepSeek 客户端。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import pytest

from skill_agent.registry import SkillRegistry


# ----------------------------------------------------------------- fixtures

@pytest.fixture
def tmp_skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    return d


@pytest.fixture
def registry(tmp_skills_dir: Path) -> SkillRegistry:
    return SkillRegistry(tmp_skills_dir)


@pytest.fixture
def sample_skill(tmp_skills_dir: Path) -> Path:
    """在磁盘落一份合法的 SKILL.md，返回它所在目录。"""
    sk = tmp_skills_dir / "greet"
    sk.mkdir()
    (sk / "SKILL.md").write_text(
        "---\n"
        "name: greet\n"
        "description: Say hello in different languages\n"
        "---\n"
        "When asked to greet, output 'Hello, <name>!'.\n"
    )
    return sk


# ----------------------------------- 伪造的 DeepSeek / OpenAI 客户端 -----

class FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.type = "function"
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content: str = "", tool_calls=None):
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls or []


class FakeChoice:
    def __init__(self, message: FakeMessage):
        self.message = message


class FakeResponse:
    def __init__(self, message: FakeMessage):
        self.choices = [FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, parent: "ScriptedClient"):
        self._parent = parent

    def create(self, **kwargs: Any) -> FakeResponse:
        self._parent.calls.append(kwargs)
        if not self._parent._responses:
            raise AssertionError("ScriptedClient 预设的响应已耗尽")
        return self._parent._responses.pop(0)


class _FakeChat:
    def __init__(self, parent: "ScriptedClient"):
        self.completions = _FakeCompletions(parent)


class ScriptedClient:
    """`openai.OpenAI` 的极简替身，按队列返回预设响应。"""

    def __init__(self, responses: List[FakeResponse]):
        self._responses = list(responses)
        self.calls: List[dict] = []
        self.chat = _FakeChat(self)


@pytest.fixture
def scripted_client():
    return ScriptedClient
