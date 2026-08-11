import json

from packages.bot.chatbot import (
    NO_DATA_FALLBACK,
    NOT_CONFIGURED_MESSAGE,
    SYSTEM_PROMPT,
    run_chat,
)
from packages.bot.llm import LLMResponse, ToolCall
from tests.test_bot_stats import make_incident
from tests.test_bot_tools import FakeQueries


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages_seen = []

    def complete(self, messages, tools):
        self.messages_seen.append(list(messages))
        assert tools, "tools must always be provided"
        return self.responses.pop(0)


def test_system_prompt_enforces_no_invention():
    assert "Never invent incidents" in SYSTEM_PROMPT
    assert "source_url" in SYSTEM_PROMPT
    assert "ONLY using data returned by the provided tools" in SYSTEM_PROMPT


def test_run_chat_tool_roundtrip_then_answer():
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[ToolCall(id="c1", name="get_latest_incidents", arguments={"n": 3})]
            ),
            LLMResponse(content="Latest: Victim Co — https://example.com/v/1"),
        ]
    )
    answer = run_chat("who got hit lately?", llm, FakeQueries())
    assert "Victim Co" in answer

    tool_messages = [m for m in llm.messages_seen[-1] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    payload = json.loads(tool_messages[0]["content"])
    assert payload["count"] == 1
    assert payload["incidents"][0]["source_url"] == "https://example.com/v/1"


def test_run_chat_no_records_flows_to_llm():
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[
                    ToolCall(id="c1", name="search_victim", arguments={"name": "Ghost Corp"})
                ]
            ),
            LLMResponse(content="No records found in the RansomWatch TH database."),
        ]
    )
    answer = run_chat("did Ghost Corp get hit?", llm, FakeQueries())
    assert "No records" in answer
    tool_msg = [m for m in llm.messages_seen[-1] if m.get("role") == "tool"][0]
    assert json.loads(tool_msg["content"]) == {"count": 0, "incidents": []}


def test_run_chat_without_llm_returns_not_configured():
    assert run_chat("anything", None, FakeQueries()) == NOT_CONFIGURED_MESSAGE


def test_run_chat_max_rounds_returns_fallback():
    llm = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=[ToolCall(id=f"c{i}", name="get_latest_incidents", arguments={})]
            )
            for i in range(10)
        ]
    )
    answer = run_chat("loop forever", llm, FakeQueries(), max_rounds=3)
    assert answer == NO_DATA_FALLBACK


def test_run_chat_empty_content_returns_fallback():
    llm = ScriptedLLM([LLMResponse(content=None)])
    assert run_chat("hi", llm, FakeQueries()) == NO_DATA_FALLBACK


def test_incident_fixture_has_no_invented_data_fields():
    i = make_incident()
    assert i.source_url == "https://example.com/v/1"
    assert i.country == "TH"
