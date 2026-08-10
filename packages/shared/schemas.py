import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class IncidentBase(BaseModel):
    victim_name: str
    normalized_name: str | None = None
    domain: str | None = None
    country: str = "TH"
    sector: str | None = None
    group_name: str | None = None
    discovered_at: datetime | None = None
    attack_date: date | None = None
    source: Literal["ransomware_live", "ransomwatch", "thaicert", "news"] | None = None
    source_url: str | None = None
    description: str | None = None
    status: Literal["unverified", "confirmed", "removed", "paid"] = "unverified"
    watchlist_hit: bool = False
    raw: dict[str, Any] | None = None


class IncidentCreate(IncidentBase):
    pass


class IncidentRead(IncidentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class WatchlistBase(BaseModel):
    name: str
    aliases: list[str] | None = None
    domains: list[str] | None = None
    priority: int = 1
    notes: str | None = None


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistRead(WatchlistBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


FollowUpStatus = Literal["not_contacted", "contacted", "meeting_booked", "po_won", "dead"]


class PipelineBase(BaseModel):
    incident_id: uuid.UUID
    watchlist_id: uuid.UUID
    follow_up_status: FollowUpStatus = "not_contacted"
    owner_note: str | None = None


class PipelineCreate(PipelineBase):
    pass


class PipelineUpdate(BaseModel):
    follow_up_status: FollowUpStatus | None = None
    owner_note: str | None = None


class PipelineRead(PipelineBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    updated_at: datetime


class AlertRuleBase(BaseModel):
    name: str | None = None
    match_mode: Literal["any_thailand", "watchlist_only", "group", "sector"] | None = None
    match_value: str | None = None
    channel: Literal["discord", "email", "both"] | None = None
    discord_channel_id: str | None = None
    email_recipients: list[str] | None = None
    enabled: bool = True


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRuleRead(AlertRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class AlertLogBase(BaseModel):
    incident_id: uuid.UUID
    rule_id: uuid.UUID
    channel: str | None = None
    sent_at: datetime | None = None
    success: bool | None = None
    error: str | None = None


class AlertLogCreate(AlertLogBase):
    pass


class AlertLogRead(AlertLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
