"""Agent 主循环的测试，使用脚本化的伪 DeepSeek 客户端。"""

from __future__ import annotations

import json

import pytest

from skill_agent.llm import Agent
from tests.conftest import FakeMessage, FakeResponse, FakeToolCall


def test_create_skill_via_tool_call(registry, scripted_client):
    """模型先发出 create_skill 工具调用，再用自然语言回复。"""
    responses = [
        FakeResponse(FakeMessage(
            tool_calls=[FakeToolCall(
                id="t1",
                name="create_skill",
                arguments=json.dumps({
                    "name": "lint-fix",
                    "description": "Fix lint errors",
                    "body": "Run ruff check --fix",
                }),
            )]
        )),
        FakeResponse(FakeMessage(content='{"message": "已创建 skill `lint-fix`。"}')),
    ]
    client = scripted_client(responses)
    agent = Agent(client=client, registry=registry, model="deepseek-chat")

    reply = agent.run_once("帮我创建一个修 lint 的 skill")

    assert json.loads(reply)["message"] == "已创建 skill `lint-fix`。"
    assert (registry.root / "lint-fix" / "SKILL.md").exists()
    # 第一条消息一定是 system。
    sys_msg = client.calls[0]["messages"][0]
    assert sys_msg["role"] == "system"
    assert all(
        call["response_format"] == {"type": "json_object"}
        for call in client.calls
    )
    # 第二次 LLM 调用必须带上工具结果。
    second = client.calls[1]["messages"]
    assert any(
        m.get("role") == "tool" and m.get("tool_call_id") == "t1"
        for m in second
    )


def test_load_skill_then_reply(registry, sample_skill, scripted_client):
    registry.refresh()
    responses = [
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall(
            "t1", "load_skill", json.dumps({"name": "greet"})
        )])),
        FakeResponse(FakeMessage(content='{"message": "Hello, World!"}')),
    ]
    client = scripted_client(responses)
    agent = Agent(client=client, registry=registry, model="deepseek-chat")

    reply = agent.run_once("用 greet 跟世界打个招呼")
    assert json.loads(reply)["message"] == "Hello, World!"
    # 工具结果中应包含 skill 的 body。
    second = client.calls[1]["messages"]
    tool_msg = next(m for m in second if m.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert "Hello, <name>!" in payload["body"]


def test_max_iters_guards_infinite_loop(registry, scripted_client):
    """模型一直返回工具调用时，应在 max_iters 处用 RuntimeError 终止，而不是无限循环。"""
    loop_resp = FakeResponse(FakeMessage(tool_calls=[FakeToolCall(
        "tx", "list_skills", "{}"
    )]))
    client = scripted_client([loop_resp] * 50)
    agent = Agent(
        client=client, registry=registry, model="deepseek-chat", max_iters=5
    )
    with pytest.raises(RuntimeError, match="max_iters"):
        agent.run_once("loop forever")


def test_unknown_tool_returns_error_to_model(registry, scripted_client):
    responses = [
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall(
            "t1", "does_not_exist", "{}"
        )])),
        FakeResponse(FakeMessage(content='{"message": "recovered"}')),
    ]
    client = scripted_client(responses)
    agent = Agent(client=client, registry=registry, model="deepseek-chat")
    reply = agent.run_once("try unknown")
    assert json.loads(reply)["message"] == "recovered"
    tool_msg = next(
        m for m in client.calls[1]["messages"] if m.get("role") == "tool"
    )
    assert "未知工具" in tool_msg["content"]


def test_call_skill_depth_limit(registry, sample_skill, scripted_client):
    """子 agent 再调一次 call_skill 时应触发深度上限。"""
    registry.refresh()
    responses = [
        # 1) 外层 agent（depth=0）→ call_skill greet
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall(
            "t1", "call_skill", json.dumps({"name": "greet", "input": "go"})
        )])),
        # 2) 子 agent（depth=1）→ 再次 call_skill greet（depth 会变 2）
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall(
            "t2", "call_skill", json.dumps({"name": "greet", "input": "again"})
        )])),
        # 3) 子 agent 收到“深度上限”的 tool 结果后给出收尾回复
        FakeResponse(FakeMessage(content='{"message": "子 agent 已停止：到达深度上限"}')),
        # 4) 外层 agent 收到子 agent 回复后给出最终文本
        FakeResponse(FakeMessage(content='{"message": "outer done"}')),
    ]
    client = scripted_client(responses)
    agent = Agent(
        client=client,
        registry=registry,
        model="deepseek-chat",
        max_call_skill_depth=2,
    )
    reply = agent.run_once("try recursive")
    assert json.loads(reply)["message"] == "outer done"

    # 在所有 LLM 调用中扫描 tool 消息，至少应有一条提到了深度上限。
    saw_limit = False
    for call in client.calls:
        for m in call["messages"]:
            if m.get("role") == "tool" and ("深度" in m.get("content", "") or "上限" in m.get("content", "")):
                saw_limit = True
    assert saw_limit, "应至少有一条 tool 消息提到深度上限"


def test_final_reply_is_normalized_json_object(registry, scripted_client):
    client = scripted_client([
        FakeResponse(FakeMessage(content='{\n  "message": "ok",\n  "data": {"count": 1}\n}')),
    ])
    agent = Agent(client=client, registry=registry, model="deepseek-chat")

    reply = agent.run_once("return json")

    assert reply == '{"message": "ok", "data": {"count": 1}}'
    assert client.calls[0]["response_format"] == {"type": "json_object"}


def test_debug_prints_messages_before_and_after_model_call(registry, scripted_client, capsys):
    client = scripted_client([
        FakeResponse(FakeMessage(tool_calls=[FakeToolCall(
            "t1", "list_skills", "{}"
        )])),
        FakeResponse(FakeMessage(content='{"message": "ok"}')),
    ])
    agent = Agent(client=client, registry=registry, model="deepseek-chat", debug=True)

    agent.run_once("return json")

    out = capsys.readouterr().out
    assert "=== LLM call #1 request messages ===" in out
    assert "=== LLM call #1 response messages ===" in out
    assert "=== LLM call #2 request messages ===" in out
    assert "=== LLM call #2 response messages ===" in out
    assert '"role": "user"' in out
    assert '"content": "return json"' in out
    assert '"role": "assistant"' in out
    assert '\\"message\\": \\"ok\\"' in out


def test_final_reply_rejects_non_json(registry, scripted_client):
    client = scripted_client([
        FakeResponse(FakeMessage(content="not json")),
    ])
    agent = Agent(client=client, registry=registry, model="deepseek-chat")

    with pytest.raises(ValueError, match="不是合法 JSON"):
        agent.run_once("return invalid")


def test_final_reply_rejects_json_array(registry, scripted_client):
    client = scripted_client([
        FakeResponse(FakeMessage(content='["not", "object"]')),
    ])
    agent = Agent(client=client, registry=registry, model="deepseek-chat")

    with pytest.raises(ValueError, match="JSON 对象"):
        agent.run_once("return array")
