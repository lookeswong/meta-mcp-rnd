import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import orchestrator, registry


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


@pytest.fixture
def loaded_registry(monkeypatch):
    monkeypatch.setattr(
        registry,
        "_tools",
        [
            {
                "name": "get_ad_accounts",
                "description": "Get ad accounts",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ],
    )


def _completion(content: str | None = None, tool_calls: list | None = None, finish: str = "stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


def _tool_call(call_id: str, name: str, args: dict):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


@pytest.mark.asyncio
async def test_run_query_no_tool_call_returns_text(loaded_registry):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_completion(content="Hello world", finish="stop")
    )
    result = await orchestrator.run_query("hi", client=client)
    assert result == "Hello world"
    assert client.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_run_query_executes_tool_then_returns_final(loaded_registry, monkeypatch):
    tool_call_obj = _tool_call("call_1", "get_ad_accounts", {"user_id": "me"})

    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            _completion(content=None, tool_calls=[tool_call_obj], finish="tool_calls"),
            _completion(content="You have 1 ad account: Acme.", finish="stop"),
        ]
    )

    mock_call = AsyncMock(return_value={"accounts": [{"id": "act_1", "name": "Acme"}]})
    monkeypatch.setattr(orchestrator.mcp_client, "call_tool", mock_call)

    result = await orchestrator.run_query("list my ad accounts", client=client)

    assert result == "You have 1 ad account: Acme."
    assert client.chat.completions.create.call_count == 2
    mock_call.assert_awaited_once_with("get_ad_accounts", {"user_id": "me"})

    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msg = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_msg) == 1
    assert tool_msg[0]["tool_call_id"] == "call_1"
    assert "act_1" in tool_msg[0]["content"]


@pytest.mark.asyncio
async def test_run_query_tool_error_fed_back(loaded_registry, monkeypatch):
    tool_call_obj = _tool_call("call_1", "get_ad_accounts", {})

    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[
            _completion(content=None, tool_calls=[tool_call_obj], finish="tool_calls"),
            _completion(content="Sorry, the data service is down.", finish="stop"),
        ]
    )

    monkeypatch.setattr(
        orchestrator.mcp_client,
        "call_tool",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = await orchestrator.run_query("list accounts", client=client)
    assert "data service is down" in result
    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msg = next(m for m in second_call_messages if m.get("role") == "tool")
    assert "boom" in tool_msg["content"]
