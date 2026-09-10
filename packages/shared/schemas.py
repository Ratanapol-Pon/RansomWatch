import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.shared.urls import clean_url

AttackType = Literal[
    "ransomware",
    "extortion",
    "data_breach",
    "phishing",
    "bec",
    "malware",
    "ddos",
    "defacement",
    "exploitation",
    "other",
]
Confidence = Literal["claimed", "reported", "confirmed", "disputed"]


class EvidenceFields(BaseModel):
    published_at: datetime | None = None
    attack_types: list[AttackType] = Field(default_factory=list)
    affected_products: list[str] = Field(default_factory=list)
    cve_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "reported"
    dark_web_url: str | None = None

    @field_validator("dark_web_url")
    @classmethod
    def validate_dark_web_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = clean_url(value, onion_only=True)
        if cleaned is None:
            raise ValueError("dark_web_url must be an HTTP(S) .onion URL without credentials")
        return cleaned


class IncidentBase(EvidenceFields):
    attack_types: list[AttackType] = Field(default_factory=lambda: ["ransomware"])
    confidence: Confidence = "claimed"
    alert_eligible: bool = True
    victim_name: str
    normalized_name: str | None = None
    domain: str | None = None
    country: str = "TH"
    sector: str | None = None
    group_name: str | None = None
    discovered_at: datetime | None = None
    attack_date: date | None = None
    source: str | None = None
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


class ThreatReportCreate(EvidenceFields):
    kind: Literal["campaign", "advisory", "news"]
    needs_review: bool = True
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_record_key: str = Field(min_length=1)
    source_url: str
    country: str | None = None
    description: str | None = None
    raw: dict[str, Any] | None = None


class ThreatReportRead(ThreatReportCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    discovered_at: datetime
    updated_at: datetime


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
