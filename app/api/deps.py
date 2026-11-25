"""Shared API dependencies — authentication lives here.

get_current_user is the single gate for every protected JSON endpoint:
no valid bearer token → 401, before any route or service code runs.

Page auth (Phase 6): browsers do not send an Authorization header on
plain navigation, so the HTML pages accept the same JWT from an
HttpOnly cookie (`sitepilot_token`, set by POST /login) as well as
from the Authorization header. get_page_user returns None instead of
raising, so page routes can redirect unauthenticated visitors to
/login (302). The JSON API is unchanged: Bearer only, 401 when absent.
"""
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

COOKIE_NAME = "sitepilot_token"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    user = _user_from_token(db, token)
    if user is None:
        raise AppError("Invalid or expired authentication token.", 401)
    return user


def get_page_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """Page auth: Bearer header first, then the HttpOnly login cookie.
    Returns None (never raises) when no valid token is presented."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else None
    if token is None:
        token = request.cookies.get(COOKIE_NAME)
    return _user_from_token(db, token)
