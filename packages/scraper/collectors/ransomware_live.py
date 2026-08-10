import logging
import time

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "RansomWatchTH/0.1 (+https://github.com/Ratanapol-Pon/RansomWatch)"
MIN_REQUEST_INTERVAL = 62.0


class RansomwareLiveError(Exception):
    pass


class RansomwareLiveClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30.0,
            follow_redirects=False,
        )
        self._last_request_at = 0.0

    def _get(self, path: str, retries: int = 2) -> list[dict]:
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - self._last_request_at)
        if wait > 0:
            logger.info("rate-limit politeness: sleeping %.1fs", wait)
            time.sleep(wait)
        self._last_request_at = time.monotonic()
        resp = self._client.get(f"{self.base_url}{path}")
        if resp.status_code in (429, 500, 502, 503) and retries > 0:
            logger.warning(
                "GET %s -> HTTP %d; backing off %.0fs (%d retries left)",
                path,
                resp.status_code,
                MIN_REQUEST_INTERVAL,
                retries,
            )
            time.sleep(MIN_REQUEST_INTERVAL)
            self._last_request_at = time.monotonic()
            return self._get(path, retries - 1)
        if resp.status_code != 200:
            raise RansomwareLiveError(f"GET {path} -> HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise RansomwareLiveError(f"GET {path} returned non-JSON body") from exc
        if not isinstance(data, list):
            raise RansomwareLiveError(f"GET {path} returned unexpected payload type")
        return data

    def fetch_country_victims(self, country: str = "TH") -> list[dict]:
        return self._get(f"/countryvictims/{country}")

    def fetch_recent_victims(self, country: str = "TH") -> list[dict]:
        data = self._get("/recentvictims")
        return [v for v in data if str(v.get("country") or "").upper() == country]
