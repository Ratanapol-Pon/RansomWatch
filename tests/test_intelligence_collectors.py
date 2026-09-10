import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from packages.scraper.collectors.cisa_kev import parse_kev
from packages.scraper.collectors.feed_http import FeedError, FeedHttp
from packages.scraper.collectors.news_rss import classify, parse_rss


def kev(**overrides):
    row = {
        "cveID": "CVE-2026-12345",
        "vendorProject": "Example",
        "product": "Gateway",
        "vulnerabilityName": "Example vulnerability",
        "dateAdded": "2026-09-10",
        "shortDescription": "Example publicly reported exploitation.",
        "knownRansomwareCampaignUse": "Unknown",
        **overrides,
    }
    return json.dumps({"count": 1, "vulnerabilities": [row]}).encode()


def rss(items: str) -> bytes:
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>'
        f"{items}</channel></rss>"
    ).encode()


def test_kev_is_exploitation_advisory_without_victim_or_country():
    result = parse_kev(kev())
    report = result.reports[0]
    assert report.source_record_key == "CVE-2026-12345"
    assert report.attack_types == ["exploitation"]
    assert report.country is None
    assert report.kind == "advisory" and report.needs_review is False
    assert report.published_at == datetime(2026, 9, 10, tzinfo=UTC)
    assert report.raw["knownRansomwareCampaignUse"] == "Unknown"


@pytest.mark.parametrize(
    "body", [b"<html>blocked</html>", b"[]", b"{}", b'{"vulnerabilities": [], "count": 0}']
)
def test_kev_schema_errors_are_not_silent_empty_success(body):
    with pytest.raises(FeedError):
        parse_kev(body)


def test_kev_partial_invalid_rows_are_reported():
    document = json.loads(kev())
    document["vulnerabilities"].append({"cveID": "bad"})
    document["count"] = 2
    result = parse_kev(json.dumps(document).encode())
    assert result.fetched == 2 and result.rejected == 1
    assert len(result.reports) == 1


def test_rss_classifies_thai_english_and_preserves_dark_link():
    body = rss("""<item><guid>article-1</guid><title>มัลแวร์และ Phishing</title>
        <link>https://example.test/news/1</link>
        <pubDate>Thu, 10 Sep 2026 15:00:00 +0700</pubDate>
        <description><![CDATA[<p>CVE-2026-12345 reported</p>
        <script>unsafe()</script>]]></description>
        </item><item><title>Data breach</title><link>http://actor.onion/post/1</link></item>""")
    result = parse_rss(body, source="thaicert", feed_url="https://example.test/feed")
    first, second = result.reports
    assert first.attack_types == ["phishing", "malware"]
    assert first.cve_ids == ["CVE-2026-12345"]
    assert first.country is None and first.needs_review is True
    assert first.kind == "news" and first.confidence == "reported"
    assert first.published_at == datetime(2026, 9, 10, 8, tzinfo=UTC)
    assert "unsafe" not in first.description
    assert second.dark_web_url == "http://actor.onion/post/1"


def test_non_cyber_rss_items_are_filtered_and_bad_entries_rejected():
    result = parse_rss(
        rss("""
        <item><title>Company picnic</title><link>https://example.test/1</link></item>
        <item><title>Phishing news</title></item>
    """),
        source="news_test",
        feed_url="https://example.test/feed",
    )
    assert result.filtered == 1 and result.rejected == 1


def test_rss_guid_dedup_key_ignores_title_edits():
    def parse(title):
        return parse_rss(
            rss(
                f"<item><guid>123</guid><title>{title}</title><link>https://example.test/1</link></item>"
            ),
            source="thaicert",
            feed_url="https://example.test/feed",
        ).reports[0]

    assert parse("Phishing news").source_record_key == parse("Phishing update").source_record_key


@pytest.mark.parametrize("body", [b"<html>not a feed</html>", rss(""), b"<rss><channel><item>"])
def test_broken_rss_and_empty_feeds_fail_loudly(body):
    with pytest.raises(FeedError):
        parse_rss(body, source="thaicert", feed_url="https://example.test/feed")


def test_atom_is_supported():
    body = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>News</title>
      <entry><id>abc</id><title>DDoS report</title><link href="https://example.test/a"/>
      <updated>2026-09-10T08:00:00Z</updated></entry></feed>"""
    assert parse_rss(body, source="news", feed_url="https://example.test/feed").reports[
        0
    ].attack_types == ["ddos"]


def test_classification_does_not_treat_every_cve_as_exploitation():
    assert classify("New vulnerability CVE-2026-12345") == ([], ["CVE-2026-12345"])


def test_robots_disallow_prevents_feed_request():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /feed")

    with FeedHttp(httpx.Client(transport=httpx.MockTransport(handler))) as http:
        with pytest.raises(FeedError, match="disallowed"):
            http.get_rss("https://example.test/feed")
    assert requests == ["/robots.txt"]


def test_robots_politeness_and_cache():
    requests, sleeps = [], []

    def handler(request):
        requests.append(request.url.path)
        return httpx.Response(
            200, text="User-agent: *\nAllow: /" if request.url.path == "/robots.txt" else "feed"
        )

    with FeedHttp(
        httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append, clock=lambda: 0
    ) as http:
        http.get_rss("https://example.test/feed")
        http.get_rss("https://example.test/feed2")
    assert requests.count("/robots.txt") == 1
    assert sleeps == [30, 30]


def test_rate_limit_carries_retry_after_without_sleeping():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(429, headers={"Retry-After": "3600"})
        )
    )
    with FeedHttp(client) as http:
        with pytest.raises(FeedError) as caught:
            http.get_json("https://example.test/kev.json")
    assert caught.value.retry_at > datetime.now(UTC) + timedelta(minutes=59)


def test_fetch_response_size_is_bounded(monkeypatch):
    monkeypatch.setattr("packages.scraper.collectors.feed_http.MAX_BYTES", 20)
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 21))
    )
    with FeedHttp(client) as http:
        with pytest.raises(FeedError, match="limit"):
            http.get_json("https://example.test/feed")
