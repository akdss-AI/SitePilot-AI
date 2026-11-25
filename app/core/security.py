"""Password hashing and JWT creation/verification.

Passwords: bcrypt directly. (passlib 1.7.4 is incompatible with modern
bcrypt >= 4.1 — verified by running it in Phase 2 — so we use the small,
maintained bcrypt API itself instead of pinning an old version.)

Tokens: signed JWTs (HS256). The secret comes only from the environment.
A token carries just the user id ("sub") and an expiry — no email, no
roles, nothing sensitive, because anyone holding a token can read it.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # A malformed stored hash can never be a match.
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id from a valid token, or None for any invalid one."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None
