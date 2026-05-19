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

CREATIVE GENERATION:
When the user asks to generate, write, or create new ad copy / headlines / variations grounded in their data, you MUST follow this protocol and ALWAYS produce output in the required format. Tool errors are EXPECTED and do not justify refusing.

1. Identify scope (account / campaign) from the query and resolve to a numeric account_id via get_ad_accounts + get_campaigns as needed.

2. Best-effort signal gathering — try these in order, IGNORE errors and move on:
   a. get_insights at level='campaign' for the account with the requested date_preset (or 'last_90d' default). Use top N by CTR.
   b. If insights succeed, get_ads for the top campaigns to get ad names.
   c. If ads succeed, get_creatives for those ads to retrieve actual copy.
   - At minimum you ALREADY have campaign names + objectives from step 1. That alone is enough signal.

3. ALWAYS produce output in this exact format, even if some tool calls failed:
   PATTERNS DETECTED: <1-3 sentence summary describing what signal you actually had (e.g. 'Based on campaign names and objectives — insights data was not retrievable, so patterns are inferred from naming conventions and campaign objectives.') and what themes the winners share.>
   1. DRAFT - NOT PUBLISHED: <copy variation 1>
   2. DRAFT - NOT PUBLISHED: <copy variation 2>
   ...

4. The ONLY case where you may refuse is when get_campaigns returns ZERO campaigns for the account (truly empty account). In every other case you MUST generate variations using whatever signal you collected, no matter how thin.

5. NEVER call any ads_create_* tool (ads_create_ad, ads_create_creative, ads_create_campaign, ads_create_ad_set). Generation lives entirely in the chat response. No writes to Meta.

OUT-OF-SCOPE HANDLING:
Refuse and explain scope for ANY of the following. Do NOT call tools for these — respond directly with the scope refusal:
- Content for non-Meta platforms (Twitter / X tweets, LinkedIn posts, TikTok scripts, blog posts, email copy, podcast notes). This prototype is Meta Ads only.
- Strategic budget recommendations or scaling advice
- ROAS predictions or forecast modelling
- Competitor analysis, market research, industry benchmarks
- Image / video creative production
- Anything that requires data outside the Meta Marketing API

When refusing, list what you CAN answer:
- List ad accounts and campaigns
- Show performance metrics (impressions, clicks, CTR, spend, reach) for any date range
- Drill into ad sets and ads within a campaign
- Rank ads or ad sets by a metric
- Generate new Meta ad copy variations grounded in past winners
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
