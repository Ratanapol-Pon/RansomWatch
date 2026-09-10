"""Bounded public feed requests; no article or onion-page crawling."""

import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from packages.shared.urls import clean_url

USER_AGENT = "RansomWatchTH/0.2 (+https://github.com/Ratanapol-Pon/RansomWatch)"
MAX_BYTES = 5_000_000


class FeedError(Exception):
    """Messages are safe for operational logs (no response bodies or credentials)."""

    def __init__(self, message: str, *, retry_at: datetime | None = None):
        super().__init__(message)
        self.retry_at = retry_at


def retry_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.isdigit():
            return datetime.now(UTC) + timedelta(seconds=int(value))
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None


class FeedHttp:
    def __init__(
        self, client: httpx.Client | None = None, *, sleep=time.sleep, clock=time.monotonic
    ):
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)
        self.owned = client is None
        self.sleep, self.clock = sleep, clock
        self.last_request: dict[str, float] = {}
        self.robots: dict[str, RobotFileParser | None] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        if self.owned:
            self.client.close()

    def _get(self, url: str, *, interval: float = 0) -> bytes:
        valid = clean_url(url)
        if not valid or clean_url(valid, onion_only=True):
            raise FeedError("feed URL must be a public HTTP(S) URL without credentials")
        origin = urlsplit(valid).netloc
        wait = interval - (self.clock() - self.last_request.get(origin, float("-inf")))
        if wait > 0:
            self.sleep(wait)
        self.last_request[origin] = self.clock()
        try:
            with self.client.stream("GET", valid, headers={"User-Agent": USER_AGENT}) as response:
                if response.status_code != 200:
                    raise FeedError(
                        f"HTTP {response.status_code}; retry on a later poll",
                        retry_at=retry_time(response.headers.get("retry-after")),
                    )
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise FeedError("feed exceeds 5 MB response limit")
                return bytes(data)
        except httpx.HTTPError as exc:
            raise FeedError(f"feed request failed: {type(exc).__name__}") from exc

    def get_json(self, url: str) -> bytes:
        return self._get(url)

    def get_rss(self, url: str) -> bytes:
        valid = clean_url(url)
        if not valid or clean_url(valid, onion_only=True):
            raise FeedError("RSS URL must be public HTTP(S)")
        parts = urlsplit(valid)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        if origin not in self.robots:
            parser = RobotFileParser()
            try:
                body = self._get(origin + "/robots.txt", interval=30)
            except FeedError as exc:
                if str(exc).startswith("HTTP 404;"):
                    self.robots[origin] = None
                else:
                    raise FeedError(
                        "cannot verify robots.txt permissions", retry_at=exc.retry_at
                    ) from exc
            else:
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
                self.robots[origin] = parser
        rules = self.robots[origin]
        if rules is not None and not rules.can_fetch(USER_AGENT, valid):
            raise FeedError("RSS access disallowed by robots.txt")
        delay = max(30, (rules.crawl_delay(USER_AGENT) or 0) if rules else 0)
        if delay > 60:
            raise FeedError("robots crawl delay exceeds worker request budget")
        return self._get(valid, interval=delay)
