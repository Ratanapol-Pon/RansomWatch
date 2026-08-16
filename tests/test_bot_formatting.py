from datetime import UTC, datetime

from packages.bot.formatting import (
    TOR_SOURCE_NOTE,
    chunk_text,
    clearnet_source_url,
    display_source,
    incident_line,
    incident_list_text,
)
from packages.bot.permissions import ADMIN_ONLY_MESSAGE, is_admin
from tests.test_bot_stats import make_incident

NOW = datetime(2026, 8, 11, 5, 30, tzinfo=UTC)

# Real KT RESTAURANT incident values (2026-07-09, group majinahanashi).
KT_ONION = "http://lthicpjqc7gkn5eq3epxndc2uig3yngvcbdya4u3m3byjod5km4yuwqd.onion/#post/blog-3"
KT_CLEARNET = "https://www.ransomware.live/id/S1QgUkVTVEFVUkFOVEBtYWppbmFoYW5hc2hp"


def test_incident_line_contains_source_and_bangkok_time():
    i = make_incident(discovered_at=NOW, watchlist_hit=True)
    line = incident_line(i)
    assert "Victim Co" in line
    assert "lockbit" in line
    assert "2026-08-11 12:30 ICT" in line
    assert "https://example.com/v/1" in line
    assert "WATCHLIST" in line


def test_clearnet_source_url_victim_and_group_fallback():
    assert clearnet_source_url("KT RESTAURANT", "majinahanashi") == KT_CLEARNET
    assert clearnet_source_url(None, "lockbit") == "https://www.ransomware.live/group/lockbit"
    assert clearnet_source_url("Some Victim", None) is None
    assert clearnet_source_url("Some Victim", "unknown") is None


def test_display_source_replaces_onion_with_clearnet():
    i = make_incident(source_url=KT_ONION)
    i.victim_name = "KT RESTAURANT"
    i.group_name = "majinahanashi"
    out = display_source(i)
    assert out == f"{KT_CLEARNET} {TOR_SOURCE_NOTE}"
    assert ".onion" not in out


def test_display_source_onion_without_known_group():
    i = make_incident(source_url=KT_ONION)
    i.group_name = "unknown"
    out = display_source(i)
    assert ".onion" not in out
    assert TOR_SOURCE_NOTE in out


def test_display_source_clearnet_passthrough():
    i = make_incident(source_url="https://example.com/v/1")
    assert display_source(i) == "https://example.com/v/1"
    i.source_url = None
    assert display_source(i) == "no source url"


def test_incident_line_onion_shows_clearnet():
    i = make_incident(source_url=KT_ONION)
    i.victim_name = "KT RESTAURANT"
    i.group_name = "majinahanashi"
    line = incident_line(i)
    assert KT_CLEARNET in line
    assert TOR_SOURCE_NOTE in line
    assert ".onion" not in line


def test_incident_list_text_empty_message():
    assert incident_list_text([], "nothing here") == "nothing here"


def test_chunk_text_splits_long_text_on_blocks():
    text = "\n\n".join(f"block {i} " + "x" * 400 for i in range(10))
    chunks = chunk_text(text, limit=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks).count("block") == 10


def test_chunk_text_short_text_passthrough():
    assert chunk_text("hello") == ["hello"]


def test_is_admin():
    assert is_admin([1, 2, 3], 2) is True
    assert is_admin([1, 3], 2) is False
    assert is_admin([1, 2], None) is False
    assert ADMIN_ONLY_MESSAGE
