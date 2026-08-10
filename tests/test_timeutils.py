from datetime import UTC, datetime, timedelta

from packages.shared.timeutils import ensure_utc, format_bangkok, to_bangkok


def test_naive_datetime_treated_as_utc():
    dt = datetime(2026, 8, 11, 1, 0, 0)
    assert ensure_utc(dt).utcoffset() == timedelta(0)
    assert to_bangkok(dt).hour == 8


def test_aware_datetime_converts():
    dt = datetime(2026, 8, 11, 0, 30, tzinfo=UTC)
    bkk = to_bangkok(dt)
    assert bkk.hour == 7 and bkk.minute == 30
    assert "07:30" in format_bangkok(dt)
