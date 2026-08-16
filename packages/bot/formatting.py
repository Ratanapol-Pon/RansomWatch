import base64

from packages.shared.models import Incident
from packages.shared.timeutils import format_bangkok

MAX_FIELD = 1024

TOR_SOURCE_NOTE = "(original source: Tor leak site)"


def clearnet_source_url(victim_name: str | None, group_name: str | None) -> str | None:
    """Clearnet ransomware.live links. Verified in a real browser (2026-08-16):
    ransomware.live is a hash-routed SPA — there is NO server-side /victims
    route. Working patterns:
      /id/<base64("victim@group")>  per-victim page, e.g.
        KT RESTAURANT + majinahanashi ->
        https://www.ransomware.live/id/S1QgUkVTVEFVUkFOVEBtYWppbmFoYW5hc2hp
      /#/group/<group>              group page (fallback when uncertain)
    Standard base64 (UTF-8), matching the site's encoding exactly.
    """
    group = (group_name or "").strip()
    if not group or group.lower() == "unknown":
        return None
    victim = (victim_name or "").strip()
    if victim:
        vid = base64.b64encode(f"{victim}@{group}".encode()).decode()
        return f"https://www.ransomware.live/id/{vid}"
    return f"https://www.ransomware.live/#/group/{group}"


def is_ransomware_live_source(i: Incident) -> bool:
    src = (i.source or "").lower()
    url = (i.source_url or "").lower()
    return "ransomware" in src or "ransomware.live" in url or ".onion" in url


def display_source(i: Incident) -> str:
    """Display-ready source link. ALL ransomware.live-sourced incidents render
    the canonical clearnet /id/ (or #/group/) link — the original source_url
    (incl. .onion) stays in incidents.source_url/raw for audit. The Tor note
    is added only when the original link was a .onion."""
    url = i.source_url
    if is_ransomware_live_source(i):
        tor = bool(url) and ".onion" in url
        note = f" {TOR_SOURCE_NOTE}" if tor else ""
        clearnet = clearnet_source_url(i.victim_name, i.group_name)
        if clearnet:
            return f"{clearnet}{note}"
        if tor:
            return f"no clearnet link available{note}"
        return url or "no source url"
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
