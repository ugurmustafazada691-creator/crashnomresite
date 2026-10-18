from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db, User, RefreshToken, AuditLog, utcnow
from app.schemas import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest, UserOut, MessageOut
from app.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, hash_token, validate_password_strength, generate_secure_token
)
from app.core.config import get_settings
from app.dependencies import get_current_user, get_client_info

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _make_referral_code() -> str:
    return generate_secure_token(8)[:10].upper()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Password strength
    ok, msg = validate_password_strength(body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Uniqueness checks
    existing = await db.execute(
        select(User).where(or_(User.username == body.username, User.email == body.email.lower()))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="İstifadəçi adı və ya email artıq mövcuddur")

    # Referral
    referred_by = None
    if body.referral_code:
        ref = await db.execute(select(User).where(User.referral_code == body.referral_code.upper()))
        ref_user = ref.scalar_one_or_none()
        if ref_user and ref_user.is_active and not ref_user.is_blocked:
            referred_by = ref_user.id

    user = User(
        username=body.username,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        referral_code=_make_referral_code(),
        referred_by=referred_by,
        accepted_terms=True,
    )
    db.add(user)
    await db.flush()

    # Referral bonus (with limit)
    if referred_by:
        count_q = await db.execute(select(User).where(User.referred_by == referred_by))
        ref_count = len(count_q.scalars().all())
        if ref_count <= settings.MAX_PAID_REFERRALS:
            ref_user = (await db.execute(select(User).where(User.id == referred_by))).scalar_one()
            ref_user.balance = round(ref_user.balance + settings.REFERRAL_BONUS, 2)
            from app.models.database import BalanceLog
            db.add(BalanceLog(
                user_id=referred_by,
                amount=settings.REFERRAL_BONUS,
                reason="Referal bonusu",
                balance_after=ref_user.balance,
            ))

    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=user.id, action="register", ip_address=ip, user_agent=ua))

    access = create_access_token(user.id, {"is_admin": user.is_admin})
    refresh = create_refresh_token(user.id)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=ua,
        ip_address=ip,
    ))

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    login_val = body.login.strip().lower()
    result = await db.execute(
        select(User).where(or_(User.username == login_val, User.email == login_val))
    )
    user = result.scalar_one_or_none()

    ip, ua = get_client_info(request)

    # Generic error to prevent user enumeration
    invalid_msg = "İstifadəçi adı/email və ya şifrə səhvdir"

    if not user:
        raise HTTPException(status_code=401, detail=invalid_msg)

    # Account lockout
    now = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=423,
            detail=f"Hesab müvəqqəti bloklanıb. {remaining} dəqiqə sonra cəhd edin.",
        )

    if user.is_blocked or not user.is_active:
        raise HTTPException(status_code=403, detail="Hesab bloklanıb və ya deaktivdir")

    if not verify_password(body.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
            user.failed_login_attempts = 0
            db.add(AuditLog(user_id=user.id, action="account_locked", ip_address=ip, user_agent=ua))
        await db.commit()
        raise HTTPException(status_code=401, detail=invalid_msg)

    # Success — reset counters
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = now

    access = create_access_token(user.id, {"is_admin": user.is_admin})
    refresh = create_refresh_token(user.id)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=ua,
        ip_address=ip,
    ))
    db.add(AuditLog(user_id=user.id, action="login", ip_address=ip, user_agent=ua))

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Etibarsız token")

    token_h = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_h,
            RefreshToken.revoked == False,  # noqa: E712
        )
    )
    stored = result.scalar_one_or_none()
    if not stored or stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Token vaxtı bitib və ya ləğv edilib")

    # Rotate: revoke old, issue new
    stored.revoked = True
    user_id = int(payload["sub"])

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or user.is_blocked or not user.is_active:
        raise HTTPException(status_code=403, detail="Hesab əlçatan deyil")

    ip, ua = get_client_info(request)
    new_access = create_access_token(user.id, {"is_admin": user.is_admin})
    new_refresh = create_refresh_token(user.id)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=ua,
        ip_address=ip,
    ))

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageOut)
async def logout(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    token_h = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_h,
            RefreshToken.user_id == user.id,
        )
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
    return MessageOut(detail="Çıxış edildi")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
