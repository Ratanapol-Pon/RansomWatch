from datetime import UTC, datetime, timedelta

from packages.bot.brief import build_brief
from tests.test_bot_stats import make_incident

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def test_brief_empty_returns_no_records_message():
    bullets = build_brief([], "manufacturing", "90d", NOW)
    assert bullets == [
        "No recorded ransomware victims for manufacturing in the last 90 days in our database."
    ]


def test_brief_max_five_bullets_all_claims_sourced():
    incidents = [
        make_incident(
            victim_name=f"Co {i}",
            discovered_at=NOW - timedelta(days=i),
            source_url=f"https://example.com/v/{i}",
        )
        for i in range(6)
    ]
    bullets = build_brief(incidents, "", "90d", NOW)
    assert len(bullets) <= 5
    joined = "\n".join(bullets)
    assert "6 ransomware victim(s)" in bullets[0]
    assert "lockbit (6)" in joined
    assert "https://example.com/v/" in joined
    assert bullets[-1].startswith("Trend:")


def test_brief_watchlist_incident_prioritized_and_flagged():
    normal = make_incident(victim_name="Normal Co", discovered_at=NOW - timedelta(days=1))
    watched = make_incident(
        victim_name="Watched Co",
        discovered_at=NOW - timedelta(days=30),
        watchlist_hit=True,
        source_url="https://example.com/watched",
    )
    bullets = build_brief([normal, watched], "", "90d", NOW)
    watchlist_bullets = [b for b in bullets if b.startswith("WATCHLIST:")]
    assert len(watchlist_bullets) == 1
    assert "Watched Co" in watchlist_bullets[0]
    assert "https://example.com/watched" in watchlist_bullets[0]


def test_brief_topic_scoping():
    mfg = make_incident(sector="Manufacturing")
    health = make_incident(sector="Healthcare")
    bullets = build_brief([mfg, health], "healthcare", "90d", NOW)
    assert "1 ransomware victim(s)" in bullets[0]
    assert "healthcare" in bullets[0]
