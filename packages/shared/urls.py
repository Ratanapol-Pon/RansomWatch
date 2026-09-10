"""Validate link metadata without fetching or resolving destinations."""

from urllib.parse import urlsplit, urlunsplit


def clean_url(value: object, *, onion_only: bool = False) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if any(char.isspace() or ord(char) < 32 for char in value) or "\\" in value:
        return None
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if parts.scheme.lower() not in ("http", "https") or not host:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        if onion_only and (not host.endswith(".onion") or host == ".onion"):
            return None
        port = parts.port  # Validate malformed ports as well.
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        return urlunsplit((parts.scheme.lower(), authority, parts.path, parts.query, ""))
    except ValueError:
        return None
