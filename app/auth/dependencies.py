from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from app.auth.security import get_session_by_token
from app.config import settings
from app.db.models import Session as SessionModel
from app.db.models import User


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: SessionModel


def load_auth_context(request: Request, db: DbSession) -> AuthContext | None:
    token = request.cookies.get(settings.session_cookie_name)
    session = get_session_by_token(db, token)
    if session is None:
        return None
    return AuthContext(user=session.user, session=session)


def require_csrf(request: Request, db: DbSession, csrf_token: str) -> AuthContext:
    auth = load_auth_context(request, db)
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required.")
    if not csrf_token or csrf_token != auth.session.csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
    return auth

