import base64

from packages.shared.models import Incident
from packages.shared.timeutils import format_bangkok

MAX_FIELD = 1024

TOR_SOURCE_NOTE = "(original source: Tor leak site)"


def clearnet_source_url(victim_name: str | None, group_name: str | None) -> str | None:
    """Clearnet ransomware.live equivalent of a Tor (.onion) leak-site URL.

    Verified against the live site (2026-08-16):
      /id/<base64("victim@group")> -> 200 (per-victim page, e.g. KT RESTAURANT)
      /group/<group>               -> 200 (group page, e.g. /group/majinahanashi)
      /victim/<name>               -> 404 (route does NOT exist)
    """
    group = (group_name or "").strip()
    if not group or group.lower() == "unknown":
        return None
    victim = (victim_name or "").strip()
    if victim:
        vid = base64.b64encode(f"{victim}@{group}".encode()).decode()
        return f"https://www.ransomware.live/id/{vid}"
    return f"https://www.ransomware.live/group/{group}"


def display_source(i: Incident) -> str:
    """Display-ready source link. The original .onion URL stays in
    incidents.source_url/raw for audit; only the rendered link is replaced."""
    url = i.source_url
    if url and ".onion" in url:
        clearnet = clearnet_source_url(i.victim_name, i.group_name)
        if clearnet:
            return f"{clearnet} {TOR_SOURCE_NOTE}"
        return f"no clearnet link available {TOR_SOURCE_NOTE}"
    return url or "no source url"


def incident_line(i: Incident) -> str:
    when = format_bangkok(i.discovered_at) if i.discovered_at else "unknown time"
    sector = f" ({i.sector})" if i.sector else ""
    url = display_source(i)
    flag = " ⚠️ WATCHLIST" if i.watchlist_hit else ""
    return f"**{i.victim_name}**{sector} — {i.group_name or 'unknown'} — {when}{flag}\n{url}"


def incident_list_text(incidents: list[Incident], empty_msg: str) -> str:
    if not incidents:
        return empty_msg
    return "\n\n".join(incident_line(i) for i in incidents)


def chunk_text(text: str, limit: int = 1900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            while len(block) > limit:
                chunks.append(block[:limit])
                block = block[limit:]
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
