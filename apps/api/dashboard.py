from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from apps.api.auth import Principal, admin, current_user, database, editor
from packages.scraper.normalize import normalize_name
from packages.scraper.pipeline import ingest_payloads, match_watchlist
from packages.shared.config import get_settings
from packages.shared.models import (
    AlertLog,
    AlertRule,
    Incident,
    IncidentSource,
    LineDelivery,
    LineGroup,
    Pipeline,
    SourceHealth,
    ThreatReport,
    Watchlist,
)
from packages.shared.schemas import (
    AlertRuleCreate,
    AttackType,
    Confidence,
    EvidenceFields,
)
from packages.shared.timeutils import utcnow

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def record(row, *, private=False):
    data = {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in ("raw", "payload")
    }
    if not private:
        data.pop("watchlist_hit", None)
    return data


def require_row(session, model, identity):
    row = session.get(model, identity)
    if row is None:
        raise HTTPException(404, "Record not found")
    return row


def filtered(model, q, country, attack_type, days):
    statement = select(model)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        name = model.victim_name if model is Incident else model.title
        statement = statement.where(name.ilike(f"%{escaped}%", escape="\\"))
    if country:
        statement = statement.where(model.country == country.upper())
    if attack_type:
        statement = statement.where(model.attack_types.any(attack_type))
    if days:
        statement = statement.where(model.discovered_at >= utcnow() - timedelta(days=days))
    return statement


def page(session, statement, model, offset, limit, private=False):
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(
        statement.order_by(model.discovered_at.desc().nullslast(), model.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return {"items": [record(row, private=private) for row in rows], "total": total}


@router.get("/me")
def me(user: Principal = Depends(current_user)):
    return {"user_id": user.user_id, "role": user.role}


@router.get("/incidents")
def incidents(
    q: str = "",
    country: str = "",
    attack_type: AttackType | None = None,
    confidence: Confidence | None = None,
    group: str = "",
    sector: str = "",
    watchlist_only: bool = False,
    days: int = Query(30, ge=0, le=3650),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    session: Session = Depends(database),
    user: Principal = Depends(current_user),
):
    statement = filtered(Incident, q, country, attack_type, days)
    if confidence:
        statement = statement.where(Incident.confidence == confidence)
    if group:
        statement = statement.where(Incident.group_name == group)
    if sector:
        statement = statement.where(Incident.sector == sector)
    if watchlist_only:
        if user.role == "viewer":
            raise HTTPException(403, "Analyst access is required")
        statement = statement.where(Incident.watchlist_hit.is_(True))
    return page(session, statement, Incident, offset, limit, user.role != "viewer")


@router.get("/incidents/{identity}")
def incident_detail(
    identity: UUID, session: Session = Depends(database), user: Principal = Depends(current_user)
):
    row = require_row(session, Incident, identity)
    sources = session.scalars(
        select(IncidentSource).where(IncidentSource.incident_id == identity)
    ).all()
    return {**record(row, private=user.role != "viewer"), "sources": [record(s) for s in sources]}


@router.get("/reports")
def reports(
    q: str = "",
    country: str = "",
    attack_type: AttackType | None = None,
    kind: Literal["news", "advisory", "campaign"] | None = None,
    needs_review: bool | None = None,
    days: int = Query(30, ge=0, le=3650),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    session: Session = Depends(database),
):
    statement = filtered(ThreatReport, q, country, attack_type, days)
    if kind:
        statement = statement.where(ThreatReport.kind == kind)
    if needs_review is not None:
        statement = statement.where(ThreatReport.needs_review == needs_review)
    return page(session, statement, ThreatReport, offset, limit)


@router.get("/reports/{identity}")
def report_detail(identity: UUID, session: Session = Depends(database)):
    return record(require_row(session, ThreatReport, identity))


class Review(EvidenceFields):
    kind: Literal["news", "advisory", "campaign"]
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    needs_review: bool = False


@router.patch("/reports/{identity}", dependencies=[Depends(editor)])
def review(identity: UUID, body: Review, session: Session = Depends(database)):
    row = require_row(session, ThreatReport, identity)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.needs_review = body.needs_review
    row.updated_at = utcnow()
    return record(row)


class Promotion(BaseModel):
    victim_name: str = Field(min_length=1, max_length=300)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    group_name: str | None = None
    sector: str | None = None
    attack_date: date | None = None
    attack_types: list[AttackType] = Field(min_length=1)
    confidence: Confidence = "reported"


@router.post("/reports/{identity}/promote", dependencies=[Depends(editor)])
def promote(identity: UUID, body: Promotion, session: Session = Depends(database)):
    row = session.scalar(select(ThreatReport).where(ThreatReport.id == identity).with_for_update())
    if not row:
        raise HTTPException(404, "Report not found")
    if row.kind == "advisory":
        raise HTTPException(422, "A vulnerability advisory is not a victim incident")
    if row.promoted_incident_id:
        return {"incident_id": row.promoted_incident_id}
    if not body.victim_name.strip():
        raise HTTPException(422, "Victim name is required")
    payload = {
        **body.model_dump(mode="json"),
        "source_record_id": f"report:{identity}",
        "source_url": row.source_url,
        "dark_web_url": row.dark_web_url,
        "published": row.published_at.isoformat() if row.published_at else None,
        "description": row.description,
        "cve_ids": row.cve_ids,
        "affected_products": row.affected_products,
    }
    result = ingest_payloads(session, [payload], source=row.source, alert_eligible=False)
    if not result.new_incidents:
        raise HTTPException(409, "Source already belongs to an incident; review its evidence")
    incident = result.new_incidents[0]
    incident.confidence = body.confidence
    row.promoted_incident_id, row.needs_review = incident.id, False
    row.updated_at = utcnow()
    return {"incident_id": incident.id}


@router.get("/summary")
def summary(
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(database),
    user: Principal = Depends(current_user),
):
    cutoff = utcnow() - timedelta(days=days)

    def count(model):
        return session.scalar(
            select(func.count()).select_from(model).where(model.discovered_at >= cutoff)
        )

    day = func.date_trunc("day", func.timezone("Asia/Bangkok", Incident.discovered_at))
    timeline = session.execute(
        select(day, func.count())
        .where(Incident.discovered_at >= cutoff)
        .group_by(day)
        .order_by(day)
    ).all()
    tags = func.unnest(Incident.attack_types).label("tag")
    tag_rows = select(tags).where(Incident.discovered_at >= cutoff).subquery()
    breakdown = session.execute(select(tag_rows.c.tag, func.count()).group_by(tag_rows.c.tag)).all()
    return {
        "incidents": count(Incident),
        "reports": count(ThreatReport),
        "review_pending": session.scalar(
            select(func.count())
            .select_from(ThreatReport)
            .where(ThreatReport.needs_review.is_(True))
        ),
        "watchlist_hits": session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.watchlist_hit.is_(True), Incident.discovered_at >= cutoff)
        )
        if user.role != "viewer"
        else None,
        "timeline": [
            {"date": value.date().isoformat(), "count": total} for value, total in timeline
        ],
        "attack_types": [{"type": key, "count": total} for key, total in breakdown],
        "generated_at": utcnow(),
    }


class WatchBody(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=3)
    notes: str | None = Field(default=None, max_length=3000)


@router.get("/watchlist", dependencies=[Depends(editor)])
def watchlist(session: Session = Depends(database)):
    return [
        record(r)
        for r in session.scalars(select(Watchlist).order_by(Watchlist.priority, Watchlist.name))
    ]


def save_watch(session, body, row=None):
    session.execute(text("select pg_advisory_xact_lock(742901, 1)"))
    normalized = normalize_name(body.name)
    if not normalized:
        raise HTTPException(422, "Company name is required")
    existing = session.scalars(select(Watchlist)).all()
    if any(
        normalize_name(r.name) == normalized and (row is None or row.id != r.id) for r in existing
    ):
        raise HTTPException(409, "Company is already on the watchlist")
    row = row or Watchlist()
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    session.add(row)
    session.flush()
    for incident in session.scalars(select(Incident)):
        if match_watchlist(incident.normalized_name or "", incident.domain, [row]):
            incident.watchlist_hit = True
    return record(row)


@router.post("/watchlist", dependencies=[Depends(editor)])
def add_watch(body: WatchBody, session: Session = Depends(database)):
    return save_watch(session, body)


@router.put("/watchlist/{identity}", dependencies=[Depends(editor)])
def edit_watch(identity: UUID, body: WatchBody, session: Session = Depends(database)):
    return save_watch(session, body, require_row(session, Watchlist, identity))


@router.delete("/watchlist/{identity}", dependencies=[Depends(editor)])
def delete_watch(identity: UUID, session: Session = Depends(database)):
    if session.scalar(select(Pipeline.id).where(Pipeline.watchlist_id == identity).limit(1)):
        raise HTTPException(
            409, "Company is referenced by archived records; retain it to preserve history"
        )
    session.delete(require_row(session, Watchlist, identity))
    return {"ok": True}


@router.get("/sources")
def sources(session: Session = Depends(database)):
    cutoff = utcnow() - timedelta(minutes=get_settings().intel_poll_minutes * 2)
    return [
        {**record(row), "stale": not row.last_success_at or row.last_success_at < cutoff}
        for row in session.scalars(select(SourceHealth).order_by(SourceHealth.source))
    ]


@router.get("/alert-rules", dependencies=[Depends(admin)])
def alert_rules(session: Session = Depends(database)):
    return [record(row) for row in session.scalars(select(AlertRule))]


@router.post("/alert-rules", dependencies=[Depends(admin)])
def add_rule(body: AlertRuleCreate, session: Session = Depends(database)):
    row = AlertRule(**body.model_dump())
    session.add(row)
    session.flush()
    return record(row)


@router.put("/alert-rules/{identity}", dependencies=[Depends(admin)])
def update_rule(identity: UUID, body: AlertRuleCreate, session: Session = Depends(database)):
    row = require_row(session, AlertRule, identity)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    return record(row)


@router.get("/alert-log", dependencies=[Depends(admin)])
def alert_log(session: Session = Depends(database)):
    return [
        record(row)
        for row in session.scalars(select(AlertLog).order_by(AlertLog.sent_at.desc()).limit(50))
    ]


@router.get("/line/groups", dependencies=[Depends(admin)])
def line_groups(session: Session = Depends(database)):
    return [record(row) for row in session.scalars(select(LineGroup).order_by(LineGroup.name))]


class GroupBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    active: bool
    language: Literal["en", "th"]
    delivery_mode: Literal["monthly", "digest", "immediate"]
    countries: list[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]] = Field(
        default_factory=lambda: ["TH"]
    )
    attack_types: list[AttackType] = Field(default_factory=list)
    include_global_reports: bool = True
    digest_hour: int = Field(default=8, ge=0, le=23)
    quiet_start: int = Field(default=22, ge=0, le=23)
    quiet_end: int = Field(default=8, ge=0, le=23)


@router.patch("/line/groups/{identity}", dependencies=[Depends(admin)])
def update_group(identity: str, body: GroupBody, session: Session = Depends(database)):
    row = session.scalar(select(LineGroup).where(LineGroup.group_id == identity).with_for_update())
    if row is None:
        raise HTTPException(404, "Record not found")
    if body.active and not row.joined:
        raise HTTPException(409, "Invite the bot back to this group first")
    if body.active and not row.active:
        row.activated_at = utcnow()
    if any(getattr(row, key) != value for key, value in body.model_dump().items() if key != "name"):
        session.execute(
            update(LineDelivery)
            .where(LineDelivery.group_id == identity, LineDelivery.sent_at.is_(None))
            .values(attempts=5, error="Cancelled: group settings changed")
        )
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    return record(row)


@router.get("/line/deliveries", dependencies=[Depends(admin)])
def line_deliveries(session: Session = Depends(database)):
    return [
        record(row)
        for row in session.scalars(
            select(LineDelivery).order_by(LineDelivery.created_at.desc()).limit(50)
        )
    ]
