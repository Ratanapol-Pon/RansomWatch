import uuid
from datetime import UTC, datetime

from packages.scraper.pipeline import map_victim, match_watchlist


def make_entry(name, aliases=None, domains=None):
    e = type("W", (), {})()
    e.id = uuid.uuid4()
    e.name = name
    e.aliases = aliases or []
    e.domains = domains or []
    return e


def test_map_victim_ransomware_live_payload():
    payload = {
        "activity": "Agriculture and Food Production",
        "country": "TH",
        "description": "Some factual description",
        "discovered": "2026-08-10T13:52:29.308186+00:00",
        "group_name": "Panzer",
        "post_title": "The Minor Food Group",
        "post_url": "http://example.onion/company/th",
        "published": "2026-08-10T10:37:11+00:00",
        "website": "minorfood.com",
    }
    data = map_victim(payload)
    assert data["victim_name"] == "The Minor Food Group"
    assert data["normalized_name"] == "the minor food group"
    assert data["group_name"] == "panzer"
    assert data["domain"] == "minorfood.com"
    assert data["sector"] == "Agriculture and Food Production"
    assert data["attack_date"].isoformat() == "2026-08-10"
    assert data["source_url"].endswith("/company/th")
    assert data["raw"] is payload


def test_map_victim_rejects_missing_name():
    assert map_victim({"group_name": "x"}) is None


def test_match_watchlist_by_alias_substring():
    entries = [make_entry("Bangkok Airways PCL", aliases=["การบินกรุงเทพ"])]
    hits = match_watchlist("bangkok airways", None, entries)
    assert hits == entries


def test_match_watchlist_by_domain():
    entries = [make_entry("Some Company", domains=["siamoil.co.th"])]
    assert match_watchlist("siam oil product", "siamoil.co.th", entries) == entries
    assert match_watchlist("other corp", "other.com", entries) == []


def test_match_watchlist_case_insensitive():
    entries = [make_entry("SIAM OIL")]
    assert match_watchlist("siam oil product", None, entries) == entries


def test_utc_now_used_for_discovered():
    assert datetime.now(UTC).tzinfo == UTC
