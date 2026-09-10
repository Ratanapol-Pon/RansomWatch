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


def test_once_continues_intelligence_after_ransomware_failure(monkeypatch):
    from packages.scraper.run import main

    calls = []

    def broken():
        raise RuntimeError("source unavailable")

    monkeypatch.setattr("packages.scraper.run.poll_once", broken)
    monkeypatch.setattr(
        "packages.scraper.run.poll_intelligence", lambda source: calls.append(source) or True
    )
    assert main(["--once"]) == 1
    assert calls == ["all"]


def test_preview_does_not_call_ransomware_or_database(monkeypatch):
    from packages.scraper.run import main

    def forbidden():
        raise AssertionError("preview must not call the incident poller")

    calls = []
    monkeypatch.setattr("packages.scraper.run.poll_once", forbidden)
    monkeypatch.setattr(
        "packages.scraper.run.poll_intelligence",
        lambda source, preview: calls.append((source, preview)) or True,
    )
    assert main(["--preview", "--source", "thaicert"]) == 0
    assert calls == [("thaicert", True)]


def test_intelligence_failure_does_not_escape_scheduler(monkeypatch):
    from packages.scraper.run import safe_intel_poll

    def broken(*args):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("packages.scraper.run.poll_intelligence", broken)
    safe_intel_poll()
