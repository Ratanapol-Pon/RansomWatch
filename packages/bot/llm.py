from dataclasses import dataclass, field
from typing import Any, Protocol

from packages.shared.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] | None = None


class LLM(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse: ...


class OpenAILLM:
    def __init__(self, api_key: str, model: str, base_url: str = ""):
        from openai import OpenAI

        self.model = model
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        calls = [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=_parse_args(tc.function.arguments),
            )
            for tc in (msg.tool_calls or [])
        ]
        raw = msg.model_dump(exclude_none=True)
        raw["content"] = raw.get("content") or ""
        return LLMResponse(content=msg.content, tool_calls=calls, raw_message=raw)


def _parse_args(raw: str | None) -> dict[str, Any]:
    import json

    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_llm(settings: Settings) -> OpenAILLM | None:
    if not settings.llm_api_key or not settings.llm_model:
        return None
    return OpenAILLM(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )
