import json

import httpx
import pytest
import respx

from app import mcp_client


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://test-mcp/mcp")
    monkeypatch.setenv("META_ACCESS_TOKEN", "TEST_TOKEN")


@pytest.mark.asyncio
@respx.mock
async def test_list_tools_returns_tools():
    route = respx.post("http://test-mcp/mcp").mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"tools": [{"name": "get_ad_accounts", "description": "x"}]},
            },
        )
    )
    tools = await mcp_client.list_tools()
    assert tools == [{"name": "get_ad_accounts", "description": "x"}]
    sent = route.calls.last.request
    body = json.loads(sent.content)
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "tools/list"
    assert sent.headers["X-META-ACCESS-TOKEN"] == "TEST_TOKEN"
    assert sent.headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_call_tool_passes_name_and_arguments():
    route = respx.post("http://test-mcp/mcp").mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )
    )
    result = await mcp_client.call_tool("get_ad_accounts", {"user_id": "me"})
    assert result == {"content": [{"type": "text", "text": "ok"}]}
    body = json.loads(route.calls.last.request.content)
    assert body["method"] == "tools/call"
    assert body["params"] == {"name": "get_ad_accounts", "arguments": {"user_id": "me"}}


@pytest.mark.asyncio
@respx.mock
async def test_rpc_error_raises():
    respx.post("http://test-mcp/mcp").mock(
        return_value=httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}},
        )
    )
    with pytest.raises(RuntimeError, match="MCP error"):
        await mcp_client.list_tools()


@pytest.mark.asyncio
@respx.mock
async def test_sse_response_parsed():
    sse_body = "event: message\ndata: " + json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    ) + "\n\n"
    respx.post("http://test-mcp/mcp").mock(
        return_value=httpx.Response(
            200,
            text=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    tools = await mcp_client.list_tools()
    assert tools == []
