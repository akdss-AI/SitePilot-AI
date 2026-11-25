"""User schemas.

UserCreate is the only schema that ever contains a plain password.
UserOut deliberately has no password/hash field — if it is not in the
schema, it cannot leak in a response.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    # bcrypt only uses the first 72 bytes of a password. Rejecting longer
    # passwords explicitly is safer than silently truncating them.
    password: str = Field(min_length=8, max_length=72)

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        # Emails are stored lower-cased so 'A@x.com' and 'a@x.com'
        # are the same account for the uniqueness check.
        return v.strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
