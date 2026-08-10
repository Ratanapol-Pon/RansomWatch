from packages.scraper.run import parse_period, safe_poll


def test_parse_period_months_and_days():
    assert parse_period("12m").days == 372
    assert parse_period("90d").days == 90


def test_parse_period_invalid():
    import pytest

    with pytest.raises(ValueError):
        parse_period("abc")


def test_safe_poll_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("API down")

    monkeypatch.setattr("packages.scraper.run.poll_once", boom)
    safe_poll()
