from typing import Any

from app import mcp_client

_tools: list[dict[str, Any]] = []


async def load() -> None:
    global _tools
    _tools = await mcp_client.list_tools()


def get_raw_tools() -> list[dict[str, Any]]:
    return _tools


def get_openai_tools() -> list[dict[str, Any]]:
    openai_tools: list[dict[str, Any]] = []
    for tool in _tools:
        schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": (tool.get("description") or "").strip()[:1024],
                    "parameters": schema,
                },
            }
        )
    return openai_tools
