import json
import os
from typing import Any

from openai import AsyncOpenAI

from app import mcp_client, registry

MODEL = "gpt-4o"
MAX_TURNS = 8

SYSTEM_PROMPT = (
    "You are an assistant that helps an internal user query their Meta Ads account. "
    "Use the available tools to fetch real data from the Meta Marketing API. "
    "Prefer calling get_ad_accounts first to discover the user's ad account ID, "
    "then call other tools with that account ID as needed. "
    "Respond with concise plain text summarising the data. "
    "Do not fabricate metrics or campaign names — only report what tools return."
)


def _build_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _tool_messages(tool_call: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result)[:32000],
    }


async def run_query(query: str, *, client: AsyncOpenAI | None = None) -> str:
    client = client or _build_client()
    tools = registry.get_openai_tools()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    for _ in range(MAX_TURNS):
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
        )
        msg = resp.choices[0].message
        finish = resp.choices[0].finish_reason

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if finish == "stop" or not msg.tool_calls:
            return msg.content or ""

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                result = await mcp_client.call_tool(tc.function.name, args)
            except Exception as exc:
                result = {"error": str(exc)}
            messages.append(_tool_messages(tc, result))

    return "Exceeded max reasoning turns without a final answer."
