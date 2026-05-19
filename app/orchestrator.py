import json
import os
from typing import Any

import httpx
from openai import AsyncOpenAI

from app import mcp_client, registry


class MCPUnavailableError(Exception):
    pass


class MCPTimeoutError(Exception):
    pass

MODEL = "gpt-4o"
MAX_TURNS = 12

SYSTEM_PROMPT = """You are an assistant that helps an internal user query their Meta Ads account using the Meta Marketing API tools.

WORKFLOW:
1. If you do not yet know the user's ad account ID, call get_ad_accounts first. Account IDs from the API look like 'act_NNNNNN' or plain digit IDs. Always pass them as the tool expects.
2. NEVER use a campaign name, ad set name, or ad name as if it were an ID. Names contain words and dashes; IDs are numeric strings (e.g. '120244589433690035'). Always resolve a name to an ID by calling get_campaigns / get_adsets / get_ads first, then use the returned numeric ID in downstream calls.
3. To work with a named campaign, first list campaigns for the relevant account (get_campaigns with account_id), find the campaign whose name matches the user's request (substring, case-insensitive), then use its numeric ID for downstream calls.
4. For performance metrics, call get_insights with the correct level ('account', 'campaign', 'adset', or 'ad') and the numeric object_id, plus a date_preset.
5. For ad set drill-down, call get_adsets with the campaign_id. For ad-level drill-down, call get_ads with the adset_id or campaign_id.
6. When asked which ad / ad set has the best (or worst) CTR or any other metric, fetch insights at the appropriate level for ALL of them, then rank in your response.

DATE RANGE MAPPING:
Map natural language date phrases to Meta's date_preset values:
- 'today' -> 'today'
- 'yesterday' -> 'yesterday'
- 'last week' / 'past week' / 'last 7 days' -> 'last_7d'
- 'last month' / 'past month' / 'last 30 days' -> 'last_30d'
- 'last 2 months' / 'last 60 days' -> 'last_60d' if supported, otherwise 'last_90d'
- 'last 3 months' / 'last quarter' / 'last 90 days' -> 'last_90d'
- 'this month' -> 'this_month'
- 'last year' -> 'last_year'

FUZZY-MATCH HANDLING:
When the user names a campaign / ad set / ad, match against the actual names as a substring (case-insensitive). If exactly one entity contains the user's phrase as a substring, treat it as the match and proceed without asking. If multiple match, pick the one with most recent activity or list them briefly and continue with the best guess. Only ask for clarification if zero matches exist.

NOT-FOUND HANDLING:
If after substring matching no entity is found in the relevant account(s), respond clearly that the named entity was not found, and list the actual available names that the user could have meant. Do not invent data. Do not raise exceptions to the user — convert any tool error into a clear plain-text explanation.

OUT-OF-SCOPE HANDLING:
This prototype only retrieves and summarises existing Meta Ads data. If the user asks for things outside that scope — strategic advice, budget recommendations, future predictions, creative copywriting, market analysis, competitor data — respond clearly that the prototype cannot help with that, and list what you CAN answer:
- List ad accounts and campaigns
- Show performance metrics (impressions, clicks, CTR, spend, reach) for any date range
- Drill into ad sets and ads within a campaign
- Rank ads or ad sets by a metric
Do not invent advice or speculation.

RESPONSE STYLE:
Plain text. Include the concrete metric values returned by the tools (impressions, clicks, CTR, spend, reach) with their units. Never fabricate metrics, campaign names, ad names, or IDs. Only report what the tools return.
"""


def _build_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _tool_messages(tool_call: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result)[:32000],
    }


def _sanitize_history(history: list[dict] | None) -> list[dict[str, Any]]:
    if not history:
        return []
    cleaned: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


async def run_query(
    query: str,
    *,
    history: list[dict] | None = None,
    client: AsyncOpenAI | None = None,
) -> str:
    client = client or _build_client()
    tools = registry.get_openai_tools()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *_sanitize_history(history),
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
            except httpx.TimeoutException as exc:
                raise MCPTimeoutError(str(exc)) from exc
            except (httpx.ConnectError, httpx.RequestError) as exc:
                raise MCPUnavailableError(str(exc)) from exc
            except Exception as exc:
                result = {"error": str(exc)}
            messages.append(_tool_messages(tc, result))

    return "Exceeded max reasoning turns without a final answer."
