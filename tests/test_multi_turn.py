from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app import orchestrator, registry


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("META_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("MCP_SERVER_URL", "http://test-mcp/mcp")


@pytest.fixture
def loaded_registry(monkeypatch):
    monkeypatch.setattr(registry, "_tools", [])


def _completion(content="ok", finish="stop"):
    msg = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)])


async def test_history_prepended_to_messages(loaded_registry):
    captured, snap = _snapshot_messages()
    client = MagicMock()
    client.chat.completions.create = snap

    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    await orchestrator.run_query("second question", history=history, client=client)

    sent = captured["messages"]
    assert sent[0]["role"] == "system"
    assert sent[1] == {"role": "user", "content": "first question"}
    assert sent[2] == {"role": "assistant", "content": "first answer"}
    assert sent[3] == {"role": "user", "content": "second question"}


def _snapshot_messages():
    captured = {}

    async def snap(*args, **kwargs):
        captured["messages"] = [dict(m) for m in kwargs["messages"]]
        return _completion("done")

    return captured, snap


async def test_malformed_history_dropped(loaded_registry):
    captured, snap = _snapshot_messages()
    client = MagicMock()
    client.chat.completions.create = snap

    history = [
        {"role": "user", "content": "good"},
        {"role": "system", "content": "blocked"},
        {"role": "user"},
        {"content": "no role"},
        "not a dict",
        {"role": "assistant", "content": 42},
        {"role": "assistant", "content": "also good"},
    ]
    await orchestrator.run_query("q", history=history, client=client)

    user_assistant = [m for m in captured["messages"] if m["role"] in {"user", "assistant"}]
    assert user_assistant == [
        {"role": "user", "content": "good"},
        {"role": "assistant", "content": "also good"},
        {"role": "user", "content": "q"},
    ]


async def test_no_history_kwarg_works(loaded_registry):
    captured, snap = _snapshot_messages()
    client = MagicMock()
    client.chat.completions.create = snap
    await orchestrator.run_query("hi", client=client)
    msgs = captured["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "hi"}


def test_api_accepts_query_with_history(monkeypatch):
    import main

    async def fake_run(query, *, history=None, client=None):
        return f"got query={query} history_len={len(history or [])}"

    monkeypatch.setattr(main.orchestrator, "run_query", fake_run)
    tc = TestClient(main.app)
    resp = tc.post(
        "/api/query",
        json={
            "query": "follow up",
            "history": [
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "reply"},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["response"] == "got query=follow up history_len=2"


def test_api_backwards_compatible_no_history(monkeypatch):
    import main

    async def fake_run(query, *, history=None, client=None):
        return f"len={len(history or [])}"

    monkeypatch.setattr(main.orchestrator, "run_query", fake_run)
    tc = TestClient(main.app)
    resp = tc.post("/api/query", json={"query": "hi"})
    assert resp.status_code == 200
    assert resp.json()["response"] == "len=0"
