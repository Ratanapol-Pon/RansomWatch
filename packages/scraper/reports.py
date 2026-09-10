"""Persist source reports and operational health without sending incident alerts."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from packages.shared.models import ThreatReport
from packages.shared.schemas import ThreatReportCreate
from packages.shared.timeutils import utcnow


@dataclass
class ReportResult:
    inserted: int = 0
    updated: int = 0


def ingest_reports(
    session: Session, reports: list[ThreatReportCreate], now: datetime | None = None
) -> ReportResult:
    now = now or utcnow()
    session.execute(text("select pg_advisory_xact_lock(742901, 2)"))
    result = ReportResult()
    for report in reports:
        row = session.scalar(
            select(ThreatReport).where(
                ThreatReport.source == report.source,
                ThreatReport.source_record_key == report.source_record_key,
            )
        )
        values = report.model_dump()
        if row is None:
            session.add(ThreatReport(**values, discovered_at=now, updated_at=now))
            session.flush()
            result.inserted += 1
            continue
        changed = False
        for key, value in values.items():
            # Preserve human review decisions on RSS; keep the latest source metadata.
            if (
                not row.needs_review
                and report.needs_review
                and key
                in (
                    "kind",
                    "needs_review",
                    "attack_types",
                    "confidence",
                    "country",
                    "affected_products",
                )
            ):
                continue
            if getattr(row, key) != value:
                setattr(row, key, value)
                changed = True
        if changed:
            row.updated_at = now
            result.updated += 1
    return result
