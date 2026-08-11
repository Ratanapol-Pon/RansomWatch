import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.scraper.events import emit
from packages.scraper.normalize import normalize_name
from packages.shared.models import Incident, Pipeline, Watchlist
from packages.shared.timeutils import ensure_utc, utcnow

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    inserted: int = 0
    merged: int = 0
    skipped: int = 0
    watchlist_hits: int = 0
    pipeline_rows: int = 0
    new_incidents: list[Incident] = field(default_factory=list)


def _parse_dt(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def map_victim(payload: dict, source: str = "ransomware_live") -> dict | None:
    name = str(payload.get("post_title") or payload.get("victim") or "").strip()
    if not name:
        return None
    group = str(payload.get("group_name") or payload.get("group") or "").strip().lower()
    published = _parse_dt(payload.get("published"))
    attack_date: date | None = published.date() if published else None
    domain = str(payload.get("website") or payload.get("domain") or "").strip() or None
    description = str(payload.get("description") or "").strip() or None
    return {
        "victim_name": name,
        "normalized_name": normalize_name(name),
        "group_name": group or "unknown",
        "domain": domain,
        "country": str(payload.get("country") or "TH").upper(),
        "sector": payload.get("activity") or payload.get("sector") or None,
        "attack_date": attack_date,
        "source": source,
        "source_url": payload.get("post_url") or payload.get("url") or None,
        "description": description,
        "status": "unverified",
        "raw": payload,
    }


def match_watchlist(
    normalized_name: str, domain: str | None, entries: list[Watchlist]
) -> list[Watchlist]:
    hits = []
    for entry in entries:
        candidates = [entry.name, *(entry.aliases or [])]
        name_hit = False
        for cand in candidates:
            nc = normalize_name(cand or "")
            if nc and (nc in normalized_name or normalized_name in nc):
                name_hit = True
                break
        if name_hit:
            hits.append(entry)
            continue
        if domain:
            for d in entry.domains or []:
                d = (d or "").strip().lower()
                if d and d in domain.lower():
                    hits.append(entry)
                    break
    return hits


def _merge_raw(existing_raw: object, payload: dict) -> dict:
    if isinstance(existing_raw, dict) and "_payloads" in existing_raw:
        merged = existing_raw
    else:
        merged = {"_payloads": [existing_raw]}
    merged["_payloads"].append(payload)
    return merged


def ingest_payloads(
    session: Session,
    payloads: list[dict],
    source: str = "ransomware_live",
    now: datetime | None = None,
) -> IngestResult:
    now = now or utcnow()
    result = IngestResult()
    watchlist_entries = list(session.scalars(select(Watchlist)).all())

    for payload in payloads:
        data = map_victim(payload, source)
        if data is None:
            result.skipped += 1
            continue

        existing = session.scalar(
            select(Incident).where(
                Incident.normalized_name == data["normalized_name"],
                Incident.group_name == data["group_name"],
            )
        )
        if existing is not None:
            existing.raw = _merge_raw(existing.raw, payload)
            result.merged += 1
            continue

        hits = match_watchlist(data["normalized_name"], data["domain"], watchlist_entries)
        incident = Incident(**data, discovered_at=now, watchlist_hit=bool(hits))
        session.add(incident)
        session.flush()
        result.inserted += 1
        result.new_incidents.append(incident)

        for entry in hits:
            session.add(
                Pipeline(
                    incident_id=incident.id,
                    watchlist_id=entry.id,
                    follow_up_status="not_contacted",
                    updated_at=now,
                )
            )
            result.watchlist_hits += 1
            result.pipeline_rows += 1
            logger.warning("WATCHLIST HIT: %s matched %s", data["victim_name"], entry.name)

        emit(
            "incident.created",
            {
                "incident_id": str(incident.id),
                "victim_name": incident.victim_name,
                "group_name": incident.group_name,
                "watchlist_hit": incident.watchlist_hit,
                "source_url": incident.source_url,
            },
        )

    return result
