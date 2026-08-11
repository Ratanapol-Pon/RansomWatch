from datetime import datetime

from packages.bot.stats import count_by_group, filter_topic, in_period, period_days, trend
from packages.shared.models import Incident
from packages.shared.timeutils import format_bangkok, utcnow


def _incident_ref(i: Incident) -> str:
    when = format_bangkok(i.discovered_at) if i.discovered_at else "unknown time"
    url = i.source_url or "no source url"
    return f"{i.victim_name} hit by {i.group_name or 'unknown'} ({when}) — {url}"


def build_brief(
    incidents: list[Incident],
    topic: str | None,
    period: str,
    now: datetime | None = None,
) -> list[str]:
    now = now or utcnow()
    days = period_days(period)
    scoped = filter_topic(in_period(incidents, days, now), topic)
    label = (topic or "").strip() or "Thailand overall"

    if not scoped:
        return [
            f"No recorded ransomware victims for {label} in the last {days} days in our database."
        ]

    previous = filter_topic(in_period(incidents, days * 2, now), topic)
    prev_only = len(previous) - len(scoped)

    bullets = [
        f"{len(scoped)} ransomware victim(s) recorded for {label} in the last {days} days.",
    ]

    top = count_by_group(scoped)[:3]
    bullets.append("Most active groups: " + ", ".join(f"{g} ({c})" for g, c in top) + ".")

    watchlist = [i for i in scoped if i.watchlist_hit]
    recent = sorted(scoped, key=lambda i: i.discovered_at or now, reverse=True)
    picks: list[Incident] = []
    for cand in [*watchlist, *recent]:
        if cand not in picks:
            picks.append(cand)
        if len(picks) == 2:
            break
    for i in picks:
        tag = "WATCHLIST: " if i.watchlist_hit else "Notable: "
        bullets.append(tag + _incident_ref(i) + ".")

    bullets.append(f"Trend: activity is {trend(len(scoped), prev_only)}.")

    return bullets[:5]
