from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List

from app.models.database import get_db, User, BalanceLog, PendingDeposit, AuditLog
from app.dependencies import get_current_user, get_current_admin, get_client_info
from app.core.config import get_settings

router = APIRouter(prefix="/api/balance", tags=["balance"])
settings = get_settings()


class BalanceOut(BaseModel):
    balance: float
    low_balance: bool


class BalanceLogOut(BaseModel):
    id: int
    amount: float
    reason: str
    balance_after: float
    created_at: datetime

    class Config:
        from_attributes = True


class DepositCreate(BaseModel):
    amount: float = Field(..., gt=0, le=50000)
    method: str = Field(..., pattern="^(card|bep20)$")
    receipt_hash: Optional[str] = Field(None, max_length=64)


class DepositOut(BaseModel):
    id: int
    amount: float
    method: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class AdminDepositAction(BaseModel):
    deposit_id: int
    action: str = Field(..., pattern="^(approve|reject)$")


@router.get("/", response_model=BalanceOut)
async def get_balance(user: User = Depends(get_current_user)):
    return BalanceOut(
        balance=round(user.balance, 2),
        low_balance=user.balance < settings.USER_LOW_BALANCE,
    )


@router.get("/history", response_model=List[BalanceLogOut])
async def balance_history(
    limit: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(limit, 1), 100)
    result = await db.execute(
        select(BalanceLog)
        .where(BalanceLog.user_id == user.id)
        .order_by(desc(BalanceLog.id))
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/deposit", response_model=DepositOut, status_code=201)
async def create_deposit(
    body: DepositCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.amount < settings.MIN_DEPOSIT:
        raise HTTPException(400, detail=f"Minimum depozit: {settings.MIN_DEPOSIT} AZN")

    if body.receipt_hash:
        existing = await db.execute(
            select(PendingDeposit).where(PendingDeposit.receipt_hash == body.receipt_hash)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, detail="Bu çek artıq göndərilib")

    dep = PendingDeposit(
        user_id=user.id,
        amount=round(body.amount, 2),
        method=body.method,
        receipt_hash=body.receipt_hash,
        status="pending",
    )
    db.add(dep)
    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=user.id, action=f"deposit_request_{body.method}", ip_address=ip, user_agent=ua,
                    details=f"amount={body.amount}"))
    await db.flush()
    return dep


@router.get("/deposits/pending", response_model=List[DepositOut])
async def my_pending_deposits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PendingDeposit)
        .where(PendingDeposit.user_id == user.id, PendingDeposit.status == "pending")
        .order_by(desc(PendingDeposit.id))
        .limit(20)
    )
    return result.scalars().all()


# ---------- Admin ----------
@router.get("/admin/pending", response_model=List[DepositOut])
async def admin_pending(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PendingDeposit)
        .where(PendingDeposit.status == "pending")
        .order_by(desc(PendingDeposit.id))
        .limit(50)
    )
    return result.scalars().all()


@router.post("/admin/process")
async def admin_process_deposit(
    body: AdminDepositAction,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PendingDeposit).where(PendingDeposit.id == body.deposit_id)
    )
    dep = result.scalar_one_or_none()
    if not dep or dep.status != "pending":
        raise HTTPException(404, detail="Depozit tapılmadı və ya artıq emal olunub")

    now = datetime.now(timezone.utc)
    dep.processed_at = now
    dep.processed_by = admin.id

    if body.action == "reject":
        dep.status = "rejected"
        ip, ua = get_client_info(request)
        db.add(AuditLog(user_id=admin.id, action="deposit_reject", ip_address=ip, user_agent=ua,
                        details=f"deposit_id={dep.id}"))
        return {"detail": "Rədd edildi", "deposit_id": dep.id}

    # Approve
    dep.status = "approved"
    target = (await db.execute(select(User).where(User.id == dep.user_id))).scalar_one()
    amount = dep.amount
    target.balance = round(target.balance + amount, 2)
    db.add(BalanceLog(
        user_id=target.id, amount=amount,
        reason=f"Depozit ({dep.method})", balance_after=target.balance,
    ))

    bonus = 0.0
    if amount >= settings.DEPOSIT_BONUS_MIN:
        bonus = round(amount * settings.DEPOSIT_BONUS_PERCENT / 100, 2)
        target.balance = round(target.balance + bonus, 2)
        db.add(BalanceLog(
            user_id=target.id, amount=bonus,
            reason=f"Depozit bonusu (+{settings.DEPOSIT_BONUS_PERCENT}%)",
            balance_after=target.balance,
        ))

    # Referral commission
    if target.referred_by and settings.REFERRAL_COMMISSION_PERCENT > 0:
        commission = round(amount * settings.REFERRAL_COMMISSION_PERCENT / 100, 2)
        if commission >= 0.01:
            ref = (await db.execute(select(User).where(User.id == target.referred_by))).scalar_one_or_none()
            if ref and ref.is_active and not ref.is_blocked:
                ref.balance = round(ref.balance + commission, 2)
                db.add(BalanceLog(
                    user_id=ref.id, amount=commission,
                    reason=f"Referal komissiya ({settings.REFERRAL_COMMISSION_PERCENT}%)",
                    balance_after=ref.balance,
                ))

    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=admin.id, action="deposit_approve", ip_address=ip, user_agent=ua,
                    details=f"deposit_id={dep.id} amount={amount} bonus={bonus}"))
    return {
        "detail": "Təsdiq olundu",
        "deposit_id": dep.id,
        "credited": amount,
        "bonus": bonus,
        "new_balance": target.balance,
    }
