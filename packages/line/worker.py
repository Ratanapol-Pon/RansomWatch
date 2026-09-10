import logging
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import String, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from packages.line.client import LineClient, LineError
from packages.shared.config import get_settings
from packages.shared.db import get_session
from packages.shared.models import Incident, LineDelivery, LineEvent, LineGroup, ThreatReport
from packages.shared.timeutils import utcnow

logger = logging.getLogger(__name__)
BANGKOK = ZoneInfo("Asia/Bangkok")


def quiet(group: LineGroup, now: datetime) -> bool:
    hour = now.astimezone(BANGKOK).hour
    start, end = group.quiet_start, group.quiet_end
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


def scope(model, group, start, end):
    query = select(model).where(model.discovered_at >= start, model.discovered_at < end)
    if group.countries:
        country_match = model.country.in_([c.upper() for c in group.countries])
        if model is ThreatReport and group.include_global_reports:
            country_match = or_(
                country_match, (model.country.is_(None) & (model.kind == "advisory"))
            )
        query = query.where(country_match)
    if group.attack_types:
        query = query.where(model.attack_types.overlap(group.attack_types))
    return query


def incident_line(row: Incident) -> str:
    return (
        f"{row.victim_name} · {', '.join(row.attack_types)} · {row.confidence}\n"
        f"{row.source_url or 'Source URL unavailable'}"
    )


def report_line(row: ThreatReport) -> str:
    return f"{row.title[:180]} · {row.kind}\n{row.source_url}"


def command_text(session, group, command: str, now: datetime) -> str:
    name, _, argument = command.strip().partition(" ")
    name = name.lower()
    th = group.language == "th"
    start = now - timedelta(days=30)
    base = scope(Incident, group, start, now)
    if name == "!help":
        return ("คำสั่ง RansomWatch\n" if th else "RansomWatch commands\n") + (
            "!latest · recent victim reports\n!company NAME · search organizations\n"
            "!reports · threat news and advisories\n!stats · last 30 days\n"
            "!brief · sourced briefing\n"
            "Group filters apply. No private customer or BD notes are shared."
        )
    if name == "!stats":
        count = session.scalar(select(func.count()).select_from(base.subquery()))
        reports = scope(ThreatReport, group, start, now)
        total = session.scalar(select(func.count()).select_from(reports.subquery()))
        return (
            f"30 วันที่ผ่านมา: รายงานผู้เสียหาย {count} รายการ; ข่าว/คำแนะนำ {total} รายการ"
            if th
            else f"Last 30 days: {count} observed victim incidents; {total} threat reports.\n"
            "Counts reflect collected public reports, not all attacks."
        )
    if name == "!reports":
        rows = session.scalars(
            scope(ThreatReport, group, start, now)
            .order_by(ThreatReport.discovered_at.desc())
            .limit(5)
        ).all()
        return "\n\n".join(report_line(row) for row in rows) or (
            "ไม่พบข้อมูล" if th else "No matching reports in the last 30 days."
        )
    if name == "!company":
        if not argument.strip():
            return "!company NAME"
        value = argument.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        base = base.where(Incident.victim_name.ilike(f"%{value}%", escape="\\"))
    rows = session.scalars(base.order_by(Incident.discovered_at.desc()).limit(5)).all()
    return "\n\n".join(incident_line(row) for row in rows) or (
        "ไม่พบข้อมูล" if th else "No matching victim reports in the last 30 days."
    )


def process_events(session, client, now):
    events = session.scalars(
        select(LineEvent)
        .where(LineEvent.processed.is_(False))
        .order_by(LineEvent.received_at)
        .limit(20)
        .with_for_update(skip_locked=True)
    ).all()
    for event in events:
        payload = event.payload
        try:
            group_id = payload["group_id"]
            timestamp = (
                datetime.fromtimestamp(payload["timestamp"] / 1000, UTC)
                if payload.get("timestamp")
                else event.received_at
            )
            group = session.get(LineGroup, group_id)
            if group is None:
                settings = get_settings()
                group = LineGroup(
                    group_id=group_id,
                    name="LINE group " + group_id[-6:],
                    joined=payload["type"] != "leave",
                    active=False,
                    language=settings.line_default_language,
                    delivery_mode=settings.line_default_delivery,
                    last_membership_at=timestamp,
                )
                session.add(group)
                session.flush()
            if payload["type"] in ("join", "leave") and timestamp >= group.last_membership_at:
                group.joined = payload["type"] == "join"
                group.active = False  # Each re-invitation requires dashboard activation.
                group.last_membership_at = timestamp
            elif payload["type"] == "message" and group.active and group.joined:
                # Ignore expired reply tokens; do not turn them into unsolicited pushes.
                fresh = now - event.received_at < timedelta(seconds=50)
                permitted = not group.last_command_at or now - group.last_command_at >= timedelta(
                    seconds=3
                )
                if fresh and permitted and payload.get("reply_token"):
                    client.reply(
                        payload["reply_token"], command_text(session, group, payload["text"], now)
                    )
                    group.last_command_at = now
        except (LineError, KeyError, TypeError, ValueError) as exc:
            event.error = str(exc) if isinstance(exc, LineError) else type(exc).__name__
        event.processed = True
        event.payload = {"type": payload.get("type"), "group_id": payload.get("group_id")}


def summary_window(group, now):
    local = now.astimezone(BANGKOK)
    if group.delivery_mode == "monthly":
        end = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        scheduled = end.replace(hour=group.digest_hour)
        if local < scheduled:
            return None
        start = (end - timedelta(days=1)).replace(day=1)
        key = "monthly:" + start.strftime("%Y-%m")
    else:
        end = local.replace(hour=group.digest_hour, minute=0, second=0, microsecond=0)
        if local < end:
            return None
        start = end - timedelta(days=1)
        key = "daily:" + end.strftime("%Y-%m-%d")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if not group.activated_at or group.activated_at >= end:
        return None
    return max(start, group.activated_at), end, key


def queue_message(session, group, key, message):
    session.execute(
        insert(LineDelivery)
        .values(group_id=group.group_id, delivery_key=key, message=message[:4500])
        .on_conflict_do_nothing(constraint="uq_line_delivery")
    )


def queue_alerts(session, now):
    groups = session.scalars(
        select(LineGroup)
        .where(LineGroup.active.is_(True), LineGroup.joined.is_(True))
        .with_for_update(skip_locked=True)
    ).all()
    for group in groups:
        if quiet(group, now) or not group.activated_at:
            continue
        if group.delivery_mode == "immediate":
            start = max(group.activated_at, now - timedelta(days=1))
            rows = session.scalars(
                scope(Incident, group, start, now)
                .where(
                    Incident.alert_eligible.is_(True),
                    ~exists().where(
                        LineDelivery.group_id == group.group_id,
                        LineDelivery.delivery_key == "incident:" + cast(Incident.id, String),
                    ),
                )
                .order_by(Incident.discovered_at)
                .limit(100)
            ).all()
            for row in rows:
                heading = (
                    "RansomWatch · รายงานผู้เสียหาย"
                    if group.language == "th"
                    else "RansomWatch · victim report"
                )
                queue_message(
                    session, group, "incident:" + str(row.id), heading + "\n" + incident_line(row)
                )
            continue
        window = summary_window(group, now)
        if window is None:
            continue
        start, end, key = window
        if session.scalar(
            select(LineDelivery.id).where(
                LineDelivery.group_id == group.group_id, LineDelivery.delivery_key == key
            )
        ):
            continue
        incident_query = scope(Incident, group, start, end)
        report_query = scope(ThreatReport, group, start, end)
        count = session.scalar(select(func.count()).select_from(incident_query.subquery()))
        report_count = session.scalar(select(func.count()).select_from(report_query.subquery()))
        incidents = session.scalars(
            incident_query.order_by(Incident.discovered_at.desc()).limit(3)
        ).all()
        reports = session.scalars(
            report_query.order_by(ThreatReport.discovered_at.desc()).limit(2)
        ).all()
        period = key.split(":")[1]
        heading = f"RansomWatch · {period}\n"
        heading += (
            f"รายงานผู้เสียหาย {count} รายการ · ข่าว/คำแนะนำ {report_count} รายการ"
            if group.language == "th"
            else f"{count} observed victim incidents · {report_count} threat reports"
        )
        message = (
            heading
            + "\n\n"
            + "\n\n".join(
                [*(incident_line(row) for row in incidents), *(report_line(row) for row in reports)]
            )
        )
        queue_message(session, group, key, message)


def send_pending(session, client, now):
    deliveries = session.scalars(
        select(LineDelivery)
        .where(
            LineDelivery.sent_at.is_(None),
            LineDelivery.attempts < 5,
            or_(LineDelivery.next_attempt_at.is_(None), LineDelivery.next_attempt_at <= now),
        )
        .order_by(LineDelivery.created_at)
        .limit(20)
        .with_for_update(skip_locked=True)
    ).all()
    for delivery in deliveries:
        group = session.get(LineGroup, delivery.group_id)
        if not group or not group.active or not group.joined:
            delivery.error, delivery.attempts = "Cancelled: group inactive", 5
            continue
        if group.activated_at and delivery.created_at < group.activated_at:
            delivery.error, delivery.attempts = "Cancelled: group activation changed", 5
            continue
        if quiet(group, now):
            delivery.next_attempt_at = now + timedelta(hours=1)
            continue
        # Bound retries by the durable creation time even if a prior DB commit failed
        # after LINE accepted the request. LINE retains retry keys for 24 hours.
        if now - delivery.created_at >= timedelta(hours=23):
            delivery.error, delivery.attempts = "Stopped: LINE retry window expired", 5
            continue
        try:
            if not client.quota_available(group.group_id):
                delivery.error = "Monthly LINE message quota is insufficient"
                delivery.next_attempt_at = now + timedelta(hours=6)
                continue
            delivery.attempts += 1
            delivery.first_attempt_at = delivery.first_attempt_at or now
            client.push(group.group_id, delivery.message, str(delivery.id))
            delivery.sent_at, delivery.error = now, None
        except (LineError, KeyError, TypeError, ValueError) as exc:
            delivery.error = str(exc) if isinstance(exc, LineError) else type(exc).__name__
            # Quota/network checks can fail before the push attempt; still back off.
            delivery.next_attempt_at = now + timedelta(minutes=min(60, 2**delivery.attempts))


def tick(client):
    now = utcnow()
    with get_session() as session:
        process_events(session, client, now)
    with get_session() as session:
        queue_alerts(session, now)
    with get_session() as session:
        send_pending(session, client, now)


def main():
    logging.basicConfig(level=logging.INFO)
    client = LineClient(get_settings().line_channel_access_token)
    try:
        while True:
            try:
                tick(client)
            except Exception as exc:
                logger.error("LINE worker cycle failed: %s", type(exc).__name__)
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
