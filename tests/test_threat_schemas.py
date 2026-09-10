import pytest
from pydantic import ValidationError

from packages.shared.schemas import IncidentCreate, ThreatReportCreate
from packages.shared.urls import clean_url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://example.com",
        "http://actor.onion.evil.test/a",
        "http://user:password@actor.onion/a",
        "http://actor.onion:bad/a",
        "http://actor.onion/\nheader",
        "http://actor.onion\\@evil.test",
    ],
)
def test_dark_web_url_rejects_unsafe_or_non_onion_urls(url):
    with pytest.raises(ValidationError):
        IncidentCreate(victim_name="Example", dark_web_url=url)


def test_dark_web_url_optional_and_normalized():
    assert IncidentCreate(victim_name="Example").dark_web_url is None
    record = IncidentCreate(victim_name="Example", dark_web_url="HTTP://ACTOR.ONION/a#section")
    assert record.dark_web_url == "http://actor.onion/a"
    assert clean_url("https://example.com/report") == "https://example.com/report"


def test_advisory_needs_no_victim_and_does_not_assume_thailand():
    report = ThreatReportCreate(
        kind="advisory",
        title="Example advisory",
        source="cisa_kev",
        source_record_key="CVE-2026-12345",
        source_url="https://example.com/advisory",
        cve_ids=["CVE-2026-12345"],
    )
    assert report.country is None
    assert report.attack_types == []


def test_invalid_attack_category_is_rejected():
    with pytest.raises(ValidationError):
        IncidentCreate(victim_name="Example", attack_types=["invented"])
