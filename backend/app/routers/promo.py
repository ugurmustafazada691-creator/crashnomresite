from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator

from app.models.database import get_db, User, PromoCode, PromoUse, BalanceLog, AuditLog
from app.dependencies import get_current_user, get_current_admin, get_client_info

router = APIRouter(prefix="/api/promo", tags=["promo"])


class PromoApply(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)

    @field_validator("code")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class PromoResult(BaseModel):
    detail: str
    bonus: float
    new_balance: float


class PromoCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=50)
    bonus: float = Field(..., gt=0, le=1000)
    max_uses: int = Field(100, ge=1, le=100000)

    @field_validator("code")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.strip().upper()


class PromoOut(BaseModel):
    code: str
    bonus: float
    max_uses: int
    used_count: int
    active: bool

    class Config:
        from_attributes = True


@router.post("/apply", response_model=PromoResult)
async def apply_promo(
    body: PromoApply,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PromoCode).where(PromoCode.code == body.code, PromoCode.active == True)  # noqa: E712
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(404, detail="Promo kod tapılmadı və ya aktiv deyil")
    if promo.used_count >= promo.max_uses:
        raise HTTPException(400, detail="Bu kodun istifadə limiti bitib")

    used = await db.execute(
        select(PromoUse).where(PromoUse.user_id == user.id, PromoUse.code == body.code)
    )
    if used.scalar_one_or_none():
        raise HTTPException(400, detail="Bu kodu artıq istifadə etmisiniz")

    user.balance = round(user.balance + promo.bonus, 2)
    promo.used_count += 1
    db.add(PromoUse(user_id=user.id, code=body.code))
    db.add(BalanceLog(
        user_id=user.id, amount=promo.bonus,
        reason=f"Promo kod: {body.code}", balance_after=user.balance,
    ))
    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=user.id, action="promo_apply", ip_address=ip, user_agent=ua,
                    details=body.code))
    return PromoResult(detail="Promo tətbiq olundu", bonus=promo.bonus, new_balance=user.balance)


@router.get("/my")
async def my_promos(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PromoUse).where(PromoUse.user_id == user.id).order_by(PromoUse.id.desc()).limit(20)
    )
    return [
        {"code": u.code, "used_at": u.created_at.isoformat() if u.created_at else None}
        for u in result.scalars().all()
    ]


# Admin
@router.post("/admin/create", response_model=PromoOut, status_code=201)
async def create_promo(
    body: PromoCreate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(PromoCode).where(PromoCode.code == body.code))
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail="Bu kod artıq var")
    p = PromoCode(code=body.code, bonus=body.bonus, max_uses=body.max_uses)
    db.add(p)
    await db.flush()
    return p


@router.get("/admin/list", response_model=List[PromoOut])
async def list_promos(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PromoCode).order_by(PromoCode.id.desc()).limit(50))
    return result.scalars().all()
