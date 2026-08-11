from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.scraper.normalize import normalize_name
from packages.shared.models import Incident, Pipeline, Watchlist
from packages.shared.timeutils import utcnow

PIPELINE_STATUSES = ["not_contacted", "contacted", "meeting_booked", "po_won"]


@dataclass
class PipelineOverview:
    companies_hit: int
    by_status: dict[str, int]
    rows: list[tuple[Pipeline, Watchlist, Incident]]

    def funnel_text(self) -> str:
        return (
            f"{self.companies_hit} watchlist companies hit → "
            f"{self.by_status.get('contacted', 0)} contacted → "
            f"{self.by_status.get('meeting_booked', 0)} meetings → "
            f"{self.by_status.get('po_won', 0)} POs"
        )


class Queries:
    def __init__(self, session: Session):
        self.session = session

    def latest(self, n: int = 5) -> list[Incident]:
        n = max(1, min(n, 25))
        stmt = (
            select(Incident)
            .where(Incident.country == "TH")
            .order_by(Incident.discovered_at.desc().nullslast())
            .limit(n)
        )
        return list(self.session.scalars(stmt).all())

    def search_victim(self, name: str) -> list[Incident]:
        normalized = normalize_name(name)
        stmt = (
            select(Incident)
            .where(
                (Incident.normalized_name.contains(normalized))
                | (Incident.victim_name.ilike(f"%{name.strip()}%"))
            )
            .order_by(Incident.discovered_at.desc().nullslast())
            .limit(10)
        )
        return list(self.session.scalars(stmt).all())

    def group_profile(self, name: str) -> tuple[str, list[Incident]]:
        stmt = (
            select(Incident)
            .where(Incident.group_name.ilike(f"%{name.strip()}%"))
            .order_by(Incident.discovered_at.desc().nullslast())
        )
        victims = list(self.session.scalars(stmt).all())
        canonical = victims[0].group_name if victims else name.strip()
        return canonical, victims

    def all_incidents(self) -> list[Incident]:
        return list(self.session.scalars(select(Incident)).all())

    def add_watch(self, company: str) -> Watchlist | None:
        normalized = normalize_name(company)
        existing = self.session.scalars(select(Watchlist)).all()
        for entry in existing:
            if normalize_name(entry.name) == normalized:
                return None
        entry = Watchlist(name=company.strip(), aliases=[], domains=[], priority=1)
        self.session.add(entry)
        self.session.flush()
        return entry

    def remove_watch(self, company: str) -> str | None:
        normalized = normalize_name(company)
        for entry in self.session.scalars(select(Watchlist)).all():
            if normalize_name(entry.name) == normalized:
                self.session.delete(entry)
                self.session.flush()
                return entry.name
        return None

    def pipeline_overview(self) -> PipelineOverview:
        stmt = (
            select(Pipeline, Watchlist, Incident)
            .join(Watchlist, Pipeline.watchlist_id == Watchlist.id)
            .join(Incident, Pipeline.incident_id == Incident.id)
            .order_by(Pipeline.updated_at.desc())
        )
        rows = list(self.session.execute(stmt).all())
        by_status: dict[str, int] = {}
        companies: set = set()
        for pipeline, watchlist, _incident in rows:
            by_status[pipeline.follow_up_status] = by_status.get(pipeline.follow_up_status, 0) + 1
            companies.add(watchlist.id)
        contacted_or_beyond = sum(
            by_status.get(s, 0) for s in ("contacted", "meeting_booked", "po_won")
        )
        by_status["contacted"] = contacted_or_beyond
        return PipelineOverview(companies_hit=len(companies), by_status=by_status, rows=rows)

    def update_pipeline(self, company: str, status: str) -> int:
        if status not in PIPELINE_STATUSES:
            raise ValueError(f"unknown status {status!r}; use one of {PIPELINE_STATUSES}")
        normalized = normalize_name(company)
        entries = [
            e
            for e in self.session.scalars(select(Watchlist)).all()
            if normalize_name(e.name) == normalized
        ]
        if not entries:
            return 0
        ids = [e.id for e in entries]
        rows = self.session.scalars(select(Pipeline).where(Pipeline.watchlist_id.in_(ids))).all()
        now = utcnow()
        for row in rows:
            row.follow_up_status = status
            row.updated_at = now
        self.session.flush()
        return len(rows)
