import json
from typing import Any

from packages.bot.llm import LLM
from packages.bot.tools import TOOL_SCHEMAS, QueryProvider, dispatch_tool, result_to_json

SYSTEM_PROMPT = """You are the RansomWatch TH assistant. You answer questions about
ransomware incidents affecting organizations in Thailand.

STRICT RULES:
1. Answer ONLY using data returned by the provided tools. Every incident you
   mention MUST come from a tool result and MUST include its source_url as a
   citation.
2. If the tools return no data, say so explicitly (e.g. "No records found in
   the RansomWatch TH database."). Never invent incidents, victim names,
   groups, dates, or statistics.
3. Do not use outside knowledge to fill gaps. If asked about something not in
   the database, say you have no records.
4. Times are displayed in Asia/Bangkok (ICT).
5. Keep answers concise and factual. Do not speculate about impact, ransom
   amounts, or attribution beyond what the data shows.
"""

MAX_TOOL_ROUNDS = 4

NO_DATA_FALLBACK = (
    "I couldn't retrieve an answer from the database for that question. "
    "Please try rephrasing, or ask something narrower."
)

NOT_CONFIGURED_MESSAGE = (
    "The chatbot is not configured yet (missing LLM_API_KEY / LLM_MODEL). "
    "Ask an admin to set them, or use the slash commands."
)


def run_chat(
    question: str, llm: LLM | None, q: QueryProvider, max_rounds: int = MAX_TOOL_ROUNDS
) -> str:
    if llm is None:
        return NOT_CONFIGURED_MESSAGE

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for _ in range(max_rounds):
        response = llm.complete(messages, TOOL_SCHEMAS)
        if not response.tool_calls:
            return (response.content or "").strip() or NO_DATA_FALLBACK

        if response.raw_message is not None:
            messages.append(response.raw_message)
        else:
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
            )
        for tc in response.tool_calls:
            result = dispatch_tool(tc.name, tc.arguments, q)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_to_json(result),
                }
            )

    return NO_DATA_FALLBACK
