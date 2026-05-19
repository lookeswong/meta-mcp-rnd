import json
import os
from itertools import count
from typing import Any

import httpx

_id_counter = count(1)


def _next_id() -> int:
    return next(_id_counter)


def _headers() -> dict[str, str]:
    token = os.environ.get("META_ACCESS_TOKEN", "")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-META-ACCESS-TOKEN": token,
    }


def _server_url() -> str:
    return os.environ.get("MCP_SERVER_URL", "http://localhost:8080/mcp")


def _parse_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("event:") or text.startswith("data:"):
        for line in text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise ValueError("SSE response with no data line")
    return json.loads(text)


async def _rpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": _next_id(), "method": method}
    if params is not None:
        body["params"] = params
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(_server_url(), headers=_headers(), json=body)
        resp.raise_for_status()
        data = _parse_response(resp.text)
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    return data.get("result", {})


async def list_tools() -> list[dict[str, Any]]:
    result = await _rpc("tools/list")
    return result.get("tools", [])


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _rpc("tools/call", {"name": name, "arguments": arguments or {}})
