import argparse
import json
import logging
import re
import sys
from datetime import timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from packages.scraper.collectors.ransomware_live import RansomwareLiveClient
from packages.scraper.pipeline import _parse_dt, ingest_payloads, upgrade_legacy_incidents
from packages.scraper.sources import health_summary, poll_intelligence
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
        result = ingest_payloads(session, windowed, source="ransomware_live", alert_eligible=False)
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


def safe_intel_poll(source: str = "all") -> None:
    try:
        poll_intelligence(source)
    except Exception as exc:
        logger.error("intelligence poll failed; scheduler continues: %s", type(exc).__name__)


def run_scheduler(source: str = "all") -> None:
    scheduler = BlockingScheduler()
    if source in ("all", "ransomware_live"):
        scheduler.add_job(
            safe_poll,
            "interval",
            minutes=POLL_INTERVAL_MINUTES,
            next_run_time=utcnow(),
            misfire_grace_time=300,
            max_instances=1,
            coalesce=True,
        )
    if source != "ransomware_live":
        scheduler.add_job(
            safe_intel_poll,
            "interval",
            args=[source],
            minutes=get_settings().intel_poll_minutes,
            next_run_time=utcnow(),
            misfire_grace_time=300,
            max_instances=1,
            coalesce=True,
        )
    logger.info(
        "scheduler started: ransomware=%dm, intelligence=%dm",
        POLL_INTERVAL_MINUTES,
        get_settings().intel_poll_minutes,
    )
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ransomwatch-scraper")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--once", action="store_true", help="poll selected sources once")
    actions.add_argument("--backfill", metavar="PERIOD", help="ransomware history, e.g. 12m or 90d")
    actions.add_argument(
        "--upgrade-legacy", action="store_true", help="enrich legacy rows in place without alerts"
    )
    actions.add_argument(
        "--source-health", action="store_true", help="show intelligence feed health"
    )
    actions.add_argument(
        "--preview", action="store_true", help="fetch intelligence without DB writes"
    )
    parser.add_argument(
        "--source",
        default="all",
        choices=["all", "ransomware_live", "cisa_kev", "thaicert", "news"],
    )
    args = parser.parse_args(argv)

    if args.preview:
        if args.source == "ransomware_live":
            parser.error("--preview supports intelligence feeds only")
        return 0 if poll_intelligence(args.source, preview=True) else 1
    if args.source_health:
        print(json.dumps(health_summary(), indent=2))
    elif args.upgrade_legacy:
        with get_session() as session:
            count = upgrade_legacy_incidents(session)
        logger.info("legacy upgrade done: %d rows enriched", count)
    elif args.backfill:
        if args.source not in ("all", "ransomware_live"):
            parser.error("--backfill applies to ransomware_live only")
        backfill(args.backfill)
    elif args.once:
        ok = True
        if args.source in ("all", "ransomware_live"):
            try:
                poll_once()
            except Exception as exc:
                logger.error("ransomware poll failed: %s", type(exc).__name__)
                ok = False
        if args.source != "ransomware_live":
            ok = poll_intelligence(args.source) and ok
        return 0 if ok else 1
    else:
        run_scheduler(args.source)
    return 0


if __name__ == "__main__":
    sys.exit(main())
