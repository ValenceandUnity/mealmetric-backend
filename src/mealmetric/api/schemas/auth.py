import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from mealmetric.models.user import Role

EmailType = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class RegisterRequest(BaseModel):
    email: EmailType
    password: str = Field(min_length=8)
    role: Role = Role.CLIENT


class LoginRequest(BaseModel):
    email: EmailType
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    email: EmailType
    role: Role
    created_at: datetime


class LogoutResponse(BaseModel):
    ok: bool
