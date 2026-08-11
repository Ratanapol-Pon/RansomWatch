from collections.abc import Iterable
from datetime import date, datetime, timedelta

from packages.shared.models import Incident
from packages.shared.timeutils import ensure_utc, to_bangkok, utcnow

PERIODS = {"7d": 7, "30d": 30, "90d": 90}


def period_days(period: str) -> int:
    days = PERIODS.get(period.strip().lower())
    if days is None:
        raise ValueError(f"unknown period {period!r}; use one of {sorted(PERIODS)}")
    return days


def in_period(
    incidents: Iterable[Incident], days: int, now: datetime | None = None
) -> list[Incident]:
    now = ensure_utc(now or utcnow())
    cutoff = now - timedelta(days=days)
    return [
        i
        for i in incidents
        if i.discovered_at is not None and ensure_utc(i.discovered_at) >= cutoff
    ]


def filter_topic(incidents: Iterable[Incident], topic: str | None) -> list[Incident]:
    topic = (topic or "").strip().lower()
    if not topic or topic in {"all", "thailand", "th"}:
        return list(incidents)
    return [
        i
        for i in incidents
        if topic in (i.sector or "").lower() or topic == (i.group_name or "").lower()
    ]


def count_by_group(incidents: Iterable[Incident]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for i in incidents:
        counts[i.group_name or "unknown"] = counts.get(i.group_name or "unknown", 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def count_by_day(
    incidents: Iterable[Incident], days: int, now: datetime | None = None
) -> list[tuple[date, int]]:
    now = ensure_utc(now or utcnow())
    start = to_bangkok(now).date() - timedelta(days=days - 1)
    counts: dict[date, int] = {start + timedelta(days=o): 0 for o in range(days)}
    for i in incidents:
        if i.discovered_at is None:
            continue
        d = to_bangkok(i.discovered_at).date()
        if d in counts:
            counts[d] += 1
    return sorted(counts.items())


def trend(current: int, previous: int) -> str:
    if previous == 0:
        return "no prior-period baseline" if current == 0 else "up from zero in the prior period"
    delta = (current - previous) / previous * 100
    direction = "up" if delta > 0 else "down" if delta < 0 else "flat vs"
    return f"{direction} {abs(delta):.0f}% vs the prior period" if delta else direction
