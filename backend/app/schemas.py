from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
import re


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    referral_code: Optional[str] = Field(None, max_length=20)
    accept_terms: bool = False

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError("İstifadəçi adı yalnız hərf, rəqəm və _ ola bilər")
        return v

    @field_validator("accept_terms")
    @classmethod
    def terms_accepted(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Şərtləri qəbul etməlisiniz")
        return v


class LoginRequest(BaseModel):
    login: str = Field(..., min_length=3, max_length=255)  # username or email
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    balance: float
    is_admin: bool
    referral_code: str
    created_at: datetime

    class Config:
        from_attributes = True


class BalanceOut(BaseModel):
    balance: float
    low_balance: bool


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0, le=10000)
    method: str = Field(..., pattern="^(card|bep20)$")


class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=100)
    message: str = Field(..., min_length=10, max_length=2000)


class TicketOut(BaseModel):
    id: int
    subject: str
    message: str
    status: str
    admin_reply: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PromoApply(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)

    @field_validator("code")
    @classmethod
    def upper_code(cls, v: str) -> str:
        return v.strip().upper()


class TempMailOut(BaseModel):
    id: int
    email: str
    status: str
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    detail: str
