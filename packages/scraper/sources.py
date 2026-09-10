import hashlib
import json
import logging
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select, text

from packages.scraper.collectors.cisa_kev import Collection, collect_kev
from packages.scraper.collectors.feed_http import FeedError, FeedHttp
from packages.scraper.collectors.news_rss import collect_rss
from packages.scraper.reports import ingest_reports
from packages.shared.config import get_settings
from packages.shared.db import get_session
from packages.shared.models import SourceHealth
from packages.shared.timeutils import utcnow

logger = logging.getLogger(__name__)


def run_source(source: str, collect: Callable[[], Collection]) -> bool:
    """One source failure cannot roll back or prevent collection from another source."""
    now = utcnow()
    try:
        with get_session() as session:
            health = session.get(SourceHealth, source)
            if health and health.next_retry_at and health.next_retry_at > now:
                logger.warning("source %s deferred until %s", source, health.next_retry_at)
                return False
        result = collect()
        with get_session() as session:
            saved = ingest_reports(session, result.reports, now)
            session.execute(text("select pg_advisory_xact_lock(742901, 3)"))
            health = session.get(SourceHealth, source)
            if health is None:
                health = SourceHealth(source=source)
                session.add(health)
            health.status = "degraded" if result.rejected else "ok"
            health.last_attempt_at = now
            health.last_success_at = now
            health.next_retry_at = None
            health.consecutive_failures = 0
            health.fetched, health.rejected = result.fetched, result.rejected
            health.filtered = result.filtered
            health.inserted, health.updated = saved.inserted, saved.updated
            health.last_error = (
                f"{result.rejected} malformed records rejected" if result.rejected else None
            )
        logger.info(
            "source %s: fetched=%d inserted=%d updated=%d filtered=%d rejected=%d",
            source,
            result.fetched,
            saved.inserted,
            saved.updated,
            result.filtered,
            result.rejected,
        )
        return result.rejected == 0
    except Exception as exc:
        error = str(exc) if isinstance(exc, FeedError) else type(exc).__name__
        logger.error("source %s failed: %s", source, error)
        try:
            with get_session() as session:
                session.execute(text("select pg_advisory_xact_lock(742901, 3)"))
                health = session.get(SourceHealth, source)
                if health is None:
                    health = SourceHealth(source=source, consecutive_failures=0)
                    session.add(health)
                health.consecutive_failures += 1
                health.status, health.last_error = "error", error
                health.last_attempt_at = now
                health.fetched = health.inserted = health.updated = 0
                health.filtered = health.rejected = 0
                minutes = min(360, 15 * 2 ** min(health.consecutive_failures - 1, 5))
                health.next_retry_at = now + timedelta(minutes=minutes)
                if isinstance(exc, FeedError) and exc.retry_at:
                    health.next_retry_at = max(health.next_retry_at, exc.retry_at)
        except Exception:
            logger.error("source %s: could not persist health; check database/migrations", source)
        return False


def preview_source(source: str, collect: Callable[[], Collection]) -> bool:
    try:
        result = collect()
        print(
            json.dumps(
                {
                    "source": source,
                    "fetched": result.fetched,
                    "accepted": len(result.reports),
                    "filtered": result.filtered,
                    "rejected": result.rejected,
                    "sample": [
                        {
                            "title": r.title,
                            "source_url": r.source_url,
                            "attack_types": r.attack_types,
                        }
                        for r in result.reports[:3]
                    ],
                },
                ensure_ascii=True,
            )
        )
        return result.rejected == 0
    except Exception as exc:
        logger.error(
            "source %s preview failed: %s",
            source,
            str(exc) if isinstance(exc, FeedError) else type(exc).__name__,
        )
        return False


def poll_intelligence(source: str = "all", *, preview: bool = False) -> bool:
    settings = get_settings()
    results = []
    run = preview_source if preview else run_source
    with FeedHttp() as http:
        if source in ("all", "cisa_kev") and settings.cisa_kev_enabled:
            results.append(run("cisa_kev", lambda: collect_kev(settings.cisa_kev_url, http)))
        if source in ("all", "thaicert") and settings.thaicert_enabled:
            results.append(
                run("thaicert", lambda: collect_rss(settings.thaicert_feed_url, "thaicert", http))
            )
        if source in ("all", "news"):
            for url in dict.fromkeys(settings.news_rss_urls):
                name = "news_" + hashlib.sha256(url.encode()).hexdigest()[:12]
                results.append(run(name, lambda url=url, name=name: collect_rss(url, name, http)))
    return all(results)


def health_summary() -> list[dict]:
    now = utcnow()
    stale_after = timedelta(minutes=get_settings().intel_poll_minutes * 2)
    with get_session() as session:
        rows = session.scalars(select(SourceHealth).order_by(SourceHealth.source)).all()
        return [
            {
                "source": row.source,
                "status": row.status,
                "stale": row.last_success_at is None or now - row.last_success_at > stale_after,
                "last_attempt_at": row.last_attempt_at.isoformat(),
                "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
                "consecutive_failures": row.consecutive_failures,
                "fetched": row.fetched,
                "inserted": row.inserted,
                "updated": row.updated,
                "filtered": row.filtered,
                "rejected": row.rejected,
                "last_error": row.last_error,
            }
            for row in rows
        ]
