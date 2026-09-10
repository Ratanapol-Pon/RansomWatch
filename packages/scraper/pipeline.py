import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from packages.scraper.events import emit
from packages.scraper.normalize import normalize_name
from packages.shared.models import Incident, IncidentSource, Pipeline, Watchlist
from packages.shared.schemas import IncidentCreate
from packages.shared.timeutils import ensure_utc, utcnow
from packages.shared.urls import clean_url

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
    name = str(
        payload.get("victim_name") or payload.get("post_title") or payload.get("victim") or ""
    ).strip()
    if not name:
        return None
    group = str(payload.get("group_name") or payload.get("group") or "").strip().lower()
    if group == "unknown":
        group = ""
    published = _parse_dt(payload.get("published_at") or payload.get("published"))
    attack_ts = _parse_dt(payload.get("attack_date") or payload.get("attackdate"))
    attack_date: date | None = attack_ts.date() if attack_ts else None
    domain = str(payload.get("website") or payload.get("domain") or "").strip() or None
    description = str(payload.get("description") or "").strip() or None
    links = [
        payload.get("source_url"),
        payload.get("post_url"),
        payload.get("url"),
        payload.get("dark_web_url"),
    ]
    dark_web_url = next(
        (url for v in [links[-1], *links[:3]] if (url := clean_url(v, onion_only=True))), None
    )
    source_url = next((url for v in links[:3] if (url := clean_url(v))), None)
    ransomware = source in ("ransomware_live", "ransomwatch")
    data = {
        "victim_name": name,
        "normalized_name": normalize_name(name),
        "group_name": group or None,
        "domain": domain,
        "country": str(payload.get("country") or "").upper(),
        "sector": payload.get("activity") or payload.get("sector") or None,
        "attack_date": attack_date,
        "published_at": published,
        "attack_types": payload.get("attack_types")
        or (["ransomware"] if ransomware else ["other"]),
        "affected_products": payload.get("affected_products") or [],
        "cve_ids": payload.get("cve_ids") or [],
        "confidence": "claimed" if ransomware else "reported",
        "source": source,
        "source_url": source_url,
        "dark_web_url": dark_web_url,
        "description": description,
        "status": "unverified",
        "raw": payload,
    }
    # Validate typed fields before persistence; collectors do not confirm claims by default.
    IncidentCreate.model_validate(data)
    return data


def source_record_key(payload: dict, data: dict) -> str:
    """Prefer feed IDs; otherwise identify a dated source observation, not a company."""
    source_id = next(
        (
            payload[key]
            for key in ("id", "victim_id", "source_record_id")
            if payload.get(key) is not None and str(payload[key]).strip()
        ),
        None,
    )
    if source_id is not None:
        identity = ["id", str(source_id)]
    else:
        published = data.get("published_at")
        attacked = data.get("attack_date")
        identity = [
            "observation",
            data["normalized_name"],
            data.get("group_name"),
            data.get("source_url") or data.get("dark_web_url"),
            published.isoformat() if published else (attacked.isoformat() if attacked else None),
        ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _lock_ingestion(session: Session) -> None:
    # Low-volume worker: serialize identity checks through commit, across worker instances.
    session.execute(text("select pg_advisory_xact_lock(742901, 1)"))


def _source_row(incident: Incident, payload: dict, data: dict, now: datetime) -> IncidentSource:
    return IncidentSource(
        incident_id=incident.id,
        source=data["source"],
        source_record_key=source_record_key(payload, data),
        source_url=data["source_url"],
        dark_web_url=data["dark_web_url"],
        published_at=data["published_at"],
        first_seen_at=now,
        last_seen_at=now,
        raw=payload,
    )


def upgrade_legacy_incidents(session: Session) -> int:
    """Idempotently enrich legacy rows in place, without INSERTing incidents or sending events."""
    _lock_ingestion(session)
    rows = session.scalars(
        select(Incident).where(
            ~select(IncidentSource.id).where(IncidentSource.incident_id == Incident.id).exists()
        )
    ).all()
    upgraded = 0
    for incident in rows:
        raw = incident.raw or {}
        payloads = raw.get("_payloads", [raw]) if isinstance(raw, dict) else []
        primary = next((p for p in payloads if isinstance(p, dict)), {})
        # Preserve legacy attribution; older merged payloads did not record their source.
        payload = primary or {
            "victim_name": incident.victim_name,
            "group_name": incident.group_name,
            "source_url": incident.source_url,
        }
        data = map_victim(payload, incident.source or "legacy")
        if data is None:
            raise ValueError(f"legacy incident {incident.id} has no usable victim metadata")
        incident.dark_web_url = (
            incident.dark_web_url
            or data["dark_web_url"]
            or clean_url(incident.source_url, onion_only=True)
        )
        incident.published_at = incident.published_at or data["published_at"]
        if incident.source in ("ransomware_live", "ransomwatch"):
            if data["attack_date"] is not None:
                incident.attack_date = data["attack_date"]
            elif incident.published_at and incident.attack_date == incident.published_at.date():
                incident.raw = {**raw, "_legacy_attack_date": incident.attack_date.isoformat()}
                incident.attack_date = None
        evidence = _source_row(incident, payload, data, incident.discovered_at or utcnow())
        collision = session.scalar(
            select(IncidentSource).where(
                IncidentSource.source == evidence.source,
                IncidentSource.source_record_key == evidence.source_record_key,
            )
        )
        if collision is not None:
            # Never silently reparent BD links or delete previously duplicated rows.
            raise ValueError(f"legacy source collision at incident {incident.id}; review required")
        session.add(evidence)
        session.flush()
        upgraded += 1
    return upgraded


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
        merged = {**existing_raw, "_payloads": list(existing_raw["_payloads"])}
    else:
        merged = {"_payloads": [existing_raw]}
    if payload not in merged["_payloads"]:
        merged["_payloads"].append(payload)
    return merged


def _find_corroborated_incident(session: Session, data: dict) -> Incident | None:
    """Conservative cross-source merge: matching entity, dated evidence and exact story URL."""
    if not data.get("published_at") or not data.get("group_name"):
        return None
    links = [data.get("dark_web_url"), data.get("source_url")]
    links = [url for url in links if url and urlsplit(url).path.strip("/")]
    if not links:
        return None
    candidates = session.scalars(
        select(Incident)
        .join(IncidentSource)
        .where(
            Incident.normalized_name == data["normalized_name"],
            Incident.group_name == data["group_name"],
            IncidentSource.published_at == data["published_at"],
            (IncidentSource.source_url.in_(links) | IncidentSource.dark_web_url.in_(links)),
        )
        .distinct()
    ).all()
    candidates = [
        item
        for item in candidates
        if (
            (
                not item.attack_date
                or not data["attack_date"]
                or item.attack_date == data["attack_date"]
            )
            and set(item.attack_types or []) & set(data["attack_types"])
        )
    ]
    return candidates[0] if len(candidates) == 1 else None


def ingest_payloads(
    session: Session,
    payloads: list[dict],
    source: str = "ransomware_live",
    now: datetime | None = None,
    *,
    alert_eligible: bool = True,
) -> IngestResult:
    now = ensure_utc(now) if now else utcnow()
    result = IngestResult()
    upgrade_legacy_incidents(session)
    watchlist_entries = list(session.scalars(select(Watchlist)).all())

    for payload in payloads:
        data = map_victim(payload, source)
        if data is None:
            result.skipped += 1
            continue

        key = source_record_key(payload, data)
        evidence = session.scalar(
            select(IncidentSource).where(
                IncidentSource.source == source,
                IncidentSource.source_record_key == key,
            )
        )
        existing = session.get(Incident, evidence.incident_id) if evidence else None
        if existing is None:
            existing = _find_corroborated_incident(session, data)
        if existing is not None:
            if evidence is None:
                session.add(_source_row(existing, payload, data, now))
                existing.raw = _merge_raw(existing.raw, payload)
            else:
                evidence.last_seen_at = now
                if evidence.raw != payload:
                    evidence.raw = payload
                    evidence.source_url = data["source_url"]
                    evidence.dark_web_url = data["dark_web_url"]
                    evidence.published_at = data["published_at"]
                    if existing.source == source:
                        existing.published_at = data["published_at"] or existing.published_at
                        existing.source_url = data["source_url"] or existing.source_url
                        existing.dark_web_url = data["dark_web_url"] or existing.dark_web_url
            # Supplement unknown fields; do not overwrite reviewed facts with feed claims.
            for field_name in ("attack_date", "published_at", "dark_web_url", "source_url"):
                if getattr(existing, field_name) is None and data[field_name] is not None:
                    setattr(existing, field_name, data[field_name])
            result.merged += 1
            continue

        hits = match_watchlist(data["normalized_name"], data["domain"], watchlist_entries)
        incident = Incident(
            **data, discovered_at=now, watchlist_hit=bool(hits), alert_eligible=alert_eligible
        )
        session.add(incident)
        session.flush()
        session.add(_source_row(incident, payload, data, now))
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

        if not alert_eligible:
            continue
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
