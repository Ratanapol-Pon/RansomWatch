from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.scraper.normalize import normalize_name
from packages.shared.models import Incident, Pipeline, Watchlist


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
                if self.session.scalar(
                    select(Pipeline.id).where(Pipeline.watchlist_id == entry.id).limit(1)
                ):
                    raise ValueError(
                        "Company is referenced by archived records; retain it to preserve history"
                    )
                self.session.delete(entry)
                self.session.flush()
                return entry.name
        return None
