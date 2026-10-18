"""
Strong security utilities:
- Argon2/bcrypt password hashing
- JWT access + refresh tokens
- Constant-time comparisons
- Secure random tokens
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import secrets
import hashlib
import hmac

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

# bcrypt is widely supported; cost factor 12 is strong
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(subject), "exp": expire, "type": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    # jti prevents reuse of stolen refresh tokens after rotation
    payload = {
        "sub": str(subject),
        "exp": expire,
        "type": "refresh",
        "jti": secrets.token_urlsafe(32),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def generate_secure_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Store only hashes of refresh tokens / API keys."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def validate_password_strength(password: str) -> tuple[bool, str]:
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        return False, f"Şifrə ən azı {settings.MIN_PASSWORD_LENGTH} simvol olmalıdır"
    if not any(c.isupper() for c in password):
        return False, "Şifrədə ən azı 1 böyük hərf olmalıdır"
    if not any(c.islower() for c in password):
        return False, "Şifrədə ən azı 1 kiçik hərf olmalıdır"
    if not any(c.isdigit() for c in password):
        return False, "Şifrədə ən azı 1 rəqəm olmalıdır"
    return True, ""
