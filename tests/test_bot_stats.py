from datetime import UTC, date, datetime, timedelta

import pytest

from packages.bot.stats import (
    count_by_day,
    count_by_group,
    filter_topic,
    in_period,
    period_days,
    trend,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def make_incident(**kw):
    i = type("I", (), {})()
    i.victim_name = kw.get("victim_name", "Victim Co")
    i.sector = kw.get("sector", "Manufacturing")
    i.group_name = kw.get("group_name", "lockbit")
    i.country = kw.get("country", "TH")
    i.discovered_at = kw.get("discovered_at", NOW)
    i.attack_date = kw.get("attack_date")
    i.status = kw.get("status", "unverified")
    i.watchlist_hit = kw.get("watchlist_hit", False)
    i.source = kw.get("source", "ransomware_live")
    i.source_url = kw.get("source_url", "https://example.com/v/1")
    return i


def test_period_days_valid_and_invalid():
    assert period_days("7d") == 7
    assert period_days(" 90D ") == 90
    with pytest.raises(ValueError):
        period_days("1y")


def test_in_period_filters_by_cutoff():
    recent = make_incident(discovered_at=NOW - timedelta(days=3))
    old = make_incident(discovered_at=NOW - timedelta(days=40))
    naive = make_incident(discovered_at=(NOW - timedelta(days=1)).replace(tzinfo=None))
    scoped = in_period([recent, old, naive], 7, NOW)
    assert recent in scoped and naive in scoped and old not in scoped


def test_filter_topic_matches_sector_substring_and_group():
    mfg = make_incident(sector="Manufacturing", group_name="lockbit")
    health = make_incident(sector="Healthcare", group_name="alphv")
    assert filter_topic([mfg, health], "manuf") == [mfg]
    assert filter_topic([mfg, health], "ALPHV") == [health]
    assert filter_topic([mfg, health], "") == [mfg, health]
    assert filter_topic([mfg, health], "thailand") == [mfg, health]
    assert filter_topic([mfg, health], "finance") == []


def test_count_by_group_sorted_desc():
    incidents = [
        make_incident(group_name="lockbit"),
        make_incident(group_name="lockbit"),
        make_incident(group_name="alphv"),
    ]
    assert count_by_group(incidents) == [("lockbit", 2), ("alphv", 1)]


def test_count_by_day_fills_zeros_and_uses_bangkok_dates():
    hit = make_incident(discovered_at=NOW - timedelta(days=1))
    daily = count_by_day([hit], 7, NOW)
    assert len(daily) == 7
    assert sum(c for _, c in daily) == 1
    assert daily[-1][1] == 0
    assert daily[0][0] == date(2026, 8, 5)


def test_trend():
    assert trend(10, 5) == "up 100% vs the prior period"
    assert trend(5, 10) == "down 50% vs the prior period"
    assert trend(5, 5) == "flat vs"
    assert trend(3, 0) == "up from zero in the prior period"
    assert trend(0, 0) == "no prior-period baseline"
