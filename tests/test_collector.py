import httpx
import pytest

from packages.scraper.collectors.ransomware_live import (
    RansomwareLiveClient,
    RansomwareLiveError,
)


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    c = RansomwareLiveClient("https://api.example/v2", client=http)
    c._last_request_at = 0.0
    return c


def test_fetch_country_victims():
    def handler(request):
        assert request.url.path == "/v2/countryvictims/TH"
        return httpx.Response(200, json=[{"post_title": "A"}])

    client = make_client(handler)
    client._last_request_at = -999
    assert client.fetch_country_victims("TH") == [{"post_title": "A"}]


def test_recent_filters_country():
    def handler(request):
        return httpx.Response(
            200, json=[{"country": "TH", "post_title": "A"}, {"country": "US", "post_title": "B"}]
        )

    client = make_client(handler)
    client._last_request_at = -999
    assert client.fetch_recent_victims("TH") == [{"country": "TH", "post_title": "A"}]


def test_non_200_raises():
    def handler(request):
        return httpx.Response(302, headers={"Location": "/apidocs/"})

    client = make_client(handler)
    client._last_request_at = -999
    with pytest.raises(RansomwareLiveError):
        client.fetch_country_victims("TH")


def test_non_json_raises():
    def handler(request):
        return httpx.Response(200, text="<html>block page</html>")

    client = make_client(handler)
    client._last_request_at = -999
    with pytest.raises(RansomwareLiveError):
        client.fetch_recent_victims("TH")
