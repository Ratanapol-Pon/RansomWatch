from datetime import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
BANGKOK = ZoneInfo("Asia/Bangkok")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_bangkok(dt: datetime) -> datetime:
    return ensure_utc(dt).astimezone(BANGKOK)


def format_bangkok(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return to_bangkok(dt).strftime(fmt) + " ICT"
