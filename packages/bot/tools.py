import json
from typing import Any, Protocol

from packages.bot.brief import build_brief
from packages.bot.stats import count_by_day, count_by_group, in_period, period_days
from packages.shared.models import Incident
from packages.shared.timeutils import format_bangkok


class QueryProvider(Protocol):
    def latest(self, n: int = 5) -> list[Incident]: ...
    def search_victim(self, name: str) -> list[Incident]: ...
    def group_profile(self, name: str) -> tuple[str, list[Incident]]: ...
    def all_incidents(self) -> list[Incident]: ...


def incident_dict(i: Incident) -> dict[str, Any]:
    return {
        "victim_name": i.victim_name,
        "sector": i.sector,
        "group_name": i.group_name,
        "country": i.country,
        "discovered_at": format_bangkok(i.discovered_at) if i.discovered_at else None,
        "attack_date": i.attack_date.isoformat() if i.attack_date else None,
        "status": i.status,
        "watchlist_hit": i.watchlist_hit,
        "source": i.source,
        "source_url": i.source_url,
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_incidents",
            "description": "List the most recent ransomware victims in Thailand.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {
                        "type": "integer",
                        "description": "number of incidents, 1-25, default 5",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_victim",
            "description": "Search incidents by victim/company name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "company name to search"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group_profile",
            "description": "Get a ransomware group's known Thai victims.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "group name"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "Aggregate counts of Thai ransomware victims for a period.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["7d", "30d", "90d"],
                        "description": "lookback window, default 30d",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_brief",
            "description": (
                "Meeting-ready spoken-style brief (max 5 bullets) for a sector, "
                "group, or Thailand overall."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "sector or group name; empty for Thailand overall",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["7d", "30d", "90d"],
                        "description": "lookback window, default 90d",
                    },
                },
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}


def dispatch_tool(name: str, args: dict[str, Any], q: QueryProvider) -> dict[str, Any]:
    if name not in TOOL_NAMES:
        return {"error": f"unknown tool {name!r}"}
    try:
        if name == "get_latest_incidents":
            n = int(args.get("n") or 5)
            incidents = q.latest(n)
            return {"count": len(incidents), "incidents": [incident_dict(i) for i in incidents]}
        if name == "search_victim":
            incidents = q.search_victim(str(args.get("name") or ""))
            return {"count": len(incidents), "incidents": [incident_dict(i) for i in incidents]}
        if name == "get_group_profile":
            canonical, victims = q.group_profile(str(args.get("name") or ""))
            return {
                "group": canonical,
                "count": len(victims),
                "incidents": [incident_dict(i) for i in victims],
            }
        if name == "get_stats":
            days = period_days(str(args.get("period") or "30d"))
            scoped = in_period(q.all_incidents(), days)
            return {
                "period": f"{days}d",
                "total": len(scoped),
                "by_group": count_by_group(scoped),
                "by_day": [(d.isoformat(), c) for d, c in count_by_day(scoped, days)],
            }
        if name == "get_brief":
            period = str(args.get("period") or "90d")
            topic = str(args.get("topic") or "")
            bullets = build_brief(q.all_incidents(), topic, period)
            return {"topic": topic or "Thailand overall", "period": period, "bullets": bullets}
    except Exception as exc:  # tool errors must not crash the chat loop
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"error": f"unhandled tool {name!r}"}


def result_to_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, default=str)
