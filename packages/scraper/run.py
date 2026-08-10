import argparse
import logging
import re
import sys
from datetime import datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from packages.scraper.collectors.ransomware_live import RansomwareLiveClient
from packages.scraper.pipeline import _parse_dt, ingest_payloads
from packages.shared.config import get_settings
from packages.shared.db import get_session
from packages.shared.timeutils import utcnow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = 15


def make_client() -> RansomwareLiveClient:
    return RansomwareLiveClient(get_settings().ransomware_live_base)


def parse_period(period: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([md])", period.strip().lower())
    if not m:
        raise ValueError(f"invalid period {period!r}: use e.g. 12m or 90d")
    n, unit = int(m.group(1)), m.group(2)
    if unit == "d":
        return timedelta(days=n)
    return timedelta(days=n * 31)


def poll_once(client: RansomwareLiveClient | None = None) -> None:
    client = client or make_client()
    country = client.fetch_country_victims("TH")
    recent = client.fetch_recent_victims("TH")
    with get_session() as session:
        r1 = ingest_payloads(session, country, source="ransomware_live")
        r2 = ingest_payloads(session, recent, source="ransomware_live")
    logger.info(
        "poll done: country=%d/%d new, recent=%d/%d new",
        r1.inserted,
        len(country),
        r2.inserted,
        len(recent),
    )


def backfill(period: str, client: RansomwareLiveClient | None = None) -> None:
    client = client or make_client()
    cutoff = utcnow() - parse_period(period)
    victims = client.fetch_country_victims("TH")
    logger.info("fetched %d TH victims; cutoff %s", len(victims), cutoff.date().isoformat())

    def in_window(p: dict) -> bool:
        ts = _parse_dt(p.get("published")) or _parse_dt(p.get("discovered"))
        return ts is None or ts >= cutoff

    windowed = [p for p in victims if in_window(p)]
    with get_session() as session:
        result = ingest_payloads(session, windowed, source="ransomware_live")
    logger.info(
        "backfill %s done: %d in window, %d inserted, %d merged, %d skipped, %d watchlist hits",
        period,
        len(windowed),
        result.inserted,
        result.merged,
        result.skipped,
        result.watchlist_hits,
    )


def safe_poll() -> None:
    try:
        poll_once()
    except Exception:
        logger.exception("poll cycle failed; scheduler continues")


def run_scheduler() -> None:
    scheduler = BlockingScheduler()
    scheduler.add_job(
        safe_poll,
        "interval",
        minutes=POLL_INTERVAL_MINUTES,
        next_run_time=datetime.now(),
        misfire_grace_time=300,
    )
    logger.info("scheduler started: polling every %d minutes", POLL_INTERVAL_MINUTES)
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ransomwatch-scraper")
    parser.add_argument("--once", action="store_true", help="run a single poll cycle")
    parser.add_argument("--backfill", metavar="PERIOD", help="e.g. 12m or 90d")
    args = parser.parse_args(argv)

    if args.backfill:
        backfill(args.backfill)
    elif args.once:
        poll_once()
    else:
        run_scheduler()
    return 0


if __name__ == "__main__":
    sys.exit(main())
