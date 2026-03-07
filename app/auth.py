from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db.models import UserORM, UserSessionORM
from .db.session import get_db

bearer = HTTPBearer(auto_error=False)


def get_admin_token() -> str:
    return os.getenv("ADMIN_API_TOKEN", "dev-admin-token")


def get_password_salt() -> str:
    return os.getenv("AUTH_PASSWORD_SALT", "parlay-bot-dev-salt")


def hash_password(password: str) -> str:
    salted = f"{get_password_salt()}::{password}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry(days: int = 14) -> datetime:
    return datetime.utcnow() + timedelta(days=days)


def get_user_session(credentials: HTTPAuthorizationCredentials | None, db: Session) -> UserSessionORM | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    token = credentials.credentials
    session = db.query(UserSessionORM).filter(UserSessionORM.session_token == token, UserSessionORM.is_active == True).first()
    if not session:
        return None
    if session.expires_at and session.expires_at < datetime.utcnow():
        session.is_active = False
        db.commit()
        return None
    session.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session


def require_user_session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> UserSessionORM:
    session = get_user_session(credentials, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User auth required")
    return session


def require_capper_session(session: UserSessionORM = Depends(require_user_session)) -> UserSessionORM:
    role = (session.user.role or 'member').lower()
    if session.user.is_admin or role == 'capper':
        return session
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Capper role required')


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> str:
    expected = get_admin_token()
    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials == expected:
        return credentials.credentials
    session = get_user_session(credentials, db)
    if session and session.user and (session.user.is_admin or (session.user.role or '').lower() == 'admin'):
        return session.session_token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin auth required")
