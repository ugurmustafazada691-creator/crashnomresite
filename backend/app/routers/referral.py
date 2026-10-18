from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.models.database import get_db, User, BalanceLog
from app.dependencies import get_current_user
from app.core.config import get_settings

router = APIRouter(prefix="/api/referral", tags=["referral"])
settings = get_settings()


class ReferralStats(BaseModel):
    referral_code: str
    referral_link: str
    invited_count: int
    earned: float
    bonus_per_user: float
    commission_percent: float


class InviteeOut(BaseModel):
    id: int
    username: str
    joined_at: Optional[datetime]


@router.get("/stats", response_model=ReferralStats)
async def referral_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = (await db.execute(
        select(func.count(User.id)).where(User.referred_by == user.id)
    )).scalar() or 0

    earned_row = await db.execute(
        select(func.coalesce(func.sum(BalanceLog.amount), 0.0)).where(
            BalanceLog.user_id == user.id,
            BalanceLog.reason.ilike("%referal%"),
        )
    )
    earned = float(earned_row.scalar() or 0)

    return ReferralStats(
        referral_code=user.referral_code,
        referral_link=f"/register?ref={user.referral_code}",
        invited_count=count,
        earned=round(earned, 2),
        bonus_per_user=settings.REFERRAL_BONUS,
        commission_percent=settings.REFERRAL_COMMISSION_PERCENT,
    )


@router.get("/invitees", response_model=List[InviteeOut])
async def invitees(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.referred_by == user.id)
        .order_by(desc(User.created_at))
        .limit(20)
    )
    return [
        InviteeOut(id=u.id, username=u.username, joined_at=u.created_at)
        for u in result.scalars().all()
    ]
