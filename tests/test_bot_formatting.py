from datetime import UTC, datetime

from packages.bot.formatting import chunk_text, incident_line, incident_list_text
from packages.bot.permissions import ADMIN_ONLY_MESSAGE, is_admin
from tests.test_bot_stats import make_incident

NOW = datetime(2026, 8, 11, 5, 30, tzinfo=UTC)


def test_incident_line_contains_source_and_bangkok_time():
    i = make_incident(discovered_at=NOW, watchlist_hit=True)
    line = incident_line(i)
    assert "Victim Co" in line
    assert "lockbit" in line
    assert "2026-08-11 12:30 ICT" in line
    assert "https://example.com/v/1" in line
    assert "WATCHLIST" in line


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
