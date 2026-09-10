import json

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.dialects.postgresql import insert

from packages.line.client import valid_signature
from packages.shared.config import get_settings
from packages.shared.models import LineEvent

router = APIRouter()
COMMANDS = ("!latest", "!company", "!stats", "!help", "!reports", "!brief")


@router.post("/webhooks/line")
async def line_webhook(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1_000_000:
            raise HTTPException(413, "Webhook is too large")
    settings = get_settings()
    if not settings.line_channel_secret:
        raise HTTPException(503, "LINE webhook is not configured")
    if not valid_signature(
        bytes(body), request.headers.get("x-line-signature", ""), settings.line_channel_secret
    ):
        raise HTTPException(401, "Invalid LINE signature")
    try:
        envelope = json.loads(body)
        events = envelope["events"]
        if not isinstance(events, list) or len(events) > 100:
            raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, "Invalid webhook body") from exc
    accepted = []
    for event in events:
        if not isinstance(event, dict):
            continue
        source = event.get("source") or {}
        if not isinstance(source, dict):
            continue
        if source.get("type") != "group" or not isinstance(source.get("groupId"), str):
            continue
        kind = event.get("type")
        if kind not in ("join", "leave", "message"):
            continue
        if kind == "message":
            message = event.get("message") or {}
            if not isinstance(message, dict):
                continue
            if message.get("type") != "text" or not isinstance(message.get("text"), str):
                continue
            command = message["text"].strip().split(" ", 1)[0].lower()
            if command not in COMMANDS:
                continue  # Ordinary group conversation is never persisted.
        event_id = event.get("webhookEventId")
        if not isinstance(event_id, str) or len(event_id) > 200:
            continue
        accepted.append(
            {
                "event_id": event_id,
                "payload": {
                    "type": kind,
                    "group_id": source["groupId"],
                    "timestamp": event.get("timestamp"),
                    "reply_token": event.get("replyToken"),
                    "text": event.get("message", {}).get("text", "")[:500]
                    if kind == "message"
                    else "",
                },
            }
        )
    if accepted:
        from packages.shared.db import get_session

        with get_session() as session:
            for item in accepted:
                session.execute(
                    insert(LineEvent)
                    .values(**item)
                    .on_conflict_do_nothing(index_elements=["event_id"])
                )
    return {"ok": True}
