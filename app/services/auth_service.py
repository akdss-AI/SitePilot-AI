"""Authentication business logic. No HTTP code here — routes call this."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


def register_user(db: Session, data: UserCreate) -> User:
    existing = db.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        # 409 Conflict — checked in the service so the route stays thin,
        # and backed by the unique constraint on users.email in the DB.
        raise AppError("An account with this email already exists.", 409)
    user = User(
        full_name=data.full_name,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    # One generic message for both "no such user" and "wrong password":
    # different messages would tell an attacker which emails are registered.
    if user is None or not verify_password(password, user.hashed_password):
        raise AppError("Invalid email or password.", 401)
    if not user.is_active:
        raise AppError("This account is inactive.", 401)
    return user
