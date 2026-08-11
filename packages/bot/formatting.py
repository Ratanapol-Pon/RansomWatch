from packages.shared.models import Incident
from packages.shared.timeutils import format_bangkok

MAX_FIELD = 1024


def incident_line(i: Incident) -> str:
    when = format_bangkok(i.discovered_at) if i.discovered_at else "unknown time"
    sector = f" ({i.sector})" if i.sector else ""
    url = i.source_url or "no source url"
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
