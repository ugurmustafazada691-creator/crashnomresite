from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, User
from app.core.security import decode_token

security = HTTPBearer(auto_error=True)


def get_client_info(request: Request) -> tuple[str, str]:
    ip = request.client.host if request.client else "unknown"
    # Prefer real IP behind proxy
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    ua = request.headers.get("user-agent", "")[:255]
    return ip, ua


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Etibarsız və ya vaxtı bitmiş token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Etibarsız token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="İstifadəçi tapılmadı")
    if user.is_blocked or not user.is_active:
        raise HTTPException(status_code=403, detail="Hesab bloklanıb")
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=423, detail="Hesab müvəqqəti bloklanıb")

    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Yalnız admin")
    return user
