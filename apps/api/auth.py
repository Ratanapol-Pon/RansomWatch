from dataclasses import dataclass
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from packages.shared.config import get_settings
from packages.shared.db import get_session
from packages.shared.models import DashboardMember

bearer = HTTPBearer(auto_error=False)


def database():
    with get_session() as session:
        yield session


@dataclass
class Principal:
    user_id: UUID
    role: str


def verified_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UUID:
    if not credentials:
        raise HTTPException(401, "Sign in to continue")
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_auth_key:
        raise HTTPException(503, "Authentication is not configured")
    try:
        response = httpx.get(
            settings.supabase_url.rstrip("/") + "/auth/v1/user",
            headers={
                "apikey": settings.supabase_auth_key,
                "Authorization": "Bearer " + credentials.credentials,
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise HTTPException(
                401 if response.status_code < 500 else 503, "Unable to verify session"
            )
        identity = response.json()
        if identity.get("is_anonymous"):
            raise HTTPException(403, "An invited account is required")
        user_id = UUID(identity["id"])
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(503, "Unable to verify session") from exc
    return user_id


def current_user(
    user_id: UUID = Depends(verified_identity), session: Session = Depends(database)
) -> Principal:
    member = session.get(DashboardMember, user_id)
    if not member or not member.enabled:
        raise HTTPException(403, "This account has no dashboard access")
    return Principal(user_id, member.role)


def editor(user: Principal = Depends(current_user)) -> Principal:
    if user.role not in ("admin", "analyst"):
        raise HTTPException(403, "Analyst access is required")
    return user


def admin(user: Principal = Depends(current_user)) -> Principal:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access is required")
    return user
