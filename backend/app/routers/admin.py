from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.models.database import (
    get_db, User, BalanceLog, PendingDeposit, Ticket, TempMail,
    AuditLog, Setting
)
from app.dependencies import get_current_admin, get_client_info
from app.core.config import get_settings
from app.core.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])
settings = get_settings()


class DashboardOut(BaseModel):
    total_users: int
    new_users_today: int
    blocked_users: int
    total_balance: float
    pending_deposits: int
    open_tickets: int
    active_tempmails: int
    today_deposit_volume: float


class UserAdminOut(BaseModel):
    id: int
    username: str
    email: str
    balance: float
    is_blocked: bool
    is_admin: bool
    referred_by: Optional[int]
    total_spent: float
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class BalanceAdjust(BaseModel):
    user_id: int
    amount: float = Field(..., description="Positive to add, negative to subtract")
    reason: str = Field("Admin əməliyyatı", max_length=200)


class BlockToggle(BaseModel):
    user_id: int
    block: bool


class SettingUpdate(BaseModel):
    key: str
    value: str


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    new_today = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )).scalar() or 0
    blocked = (await db.execute(
        select(func.count(User.id)).where(User.is_blocked == True)  # noqa: E712
    )).scalar() or 0
    total_bal = (await db.execute(select(func.coalesce(func.sum(User.balance), 0.0)))).scalar() or 0.0
    pending = (await db.execute(
        select(func.count(PendingDeposit.id)).where(PendingDeposit.status == "pending")
    )).scalar() or 0
    open_t = (await db.execute(
        select(func.count(Ticket.id)).where(Ticket.status == "open")
    )).scalar() or 0
    active_tm = (await db.execute(
        select(func.count(TempMail.id)).where(
            TempMail.status == "active",
            TempMail.expires_at > datetime.now(timezone.utc),
        )
    )).scalar() or 0
    dep_vol = (await db.execute(
        select(func.coalesce(func.sum(BalanceLog.amount), 0.0)).where(
            BalanceLog.amount > 0,
            BalanceLog.reason.like("Depozit%"),
            BalanceLog.created_at >= today_start,
        )
    )).scalar() or 0.0

    return DashboardOut(
        total_users=total_users,
        new_users_today=new_today,
        blocked_users=blocked,
        total_balance=round(float(total_bal), 2),
        pending_deposits=pending,
        open_tickets=open_t,
        active_tempmails=active_tm,
        today_deposit_volume=round(float(dep_vol), 2),
    )


@router.get("/users/search", response_model=List[UserAdminOut])
async def search_users(
    q: str = "",
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    q = q.strip()
    if not q:
        result = await db.execute(select(User).order_by(desc(User.id)).limit(20))
        return result.scalars().all()
    if q.isdigit():
        result = await db.execute(select(User).where(User.id == int(q)))
    else:
        result = await db.execute(
            select(User).where(
                or_(User.username.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"))
            ).limit(20)
        )
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=UserAdminOut)
async def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, detail="İstifadəçi tapılmadı")
    return u


@router.post("/balance/adjust")
async def adjust_balance(
    body: BalanceAdjust,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == body.user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, detail="İstifadəçi tapılmadı")
    if body.amount < 0 and u.balance + body.amount < -0.001:
        raise HTTPException(400, detail="Balans mənfiyə düşə bilməz")
    u.balance = round(u.balance + body.amount, 2)
    db.add(BalanceLog(
        user_id=u.id, amount=body.amount,
        reason=f"Admin: {body.reason}", balance_after=u.balance,
    ))
    ip, ua = get_client_info(request)
    db.add(AuditLog(
        user_id=admin.id, action="admin_balance_adjust",
        ip_address=ip, user_agent=ua,
        details=f"target={u.id} amount={body.amount}",
    ))
    return {"detail": "OK", "new_balance": u.balance}


@router.post("/users/block")
async def toggle_block(
    body: BlockToggle,
    request: Request,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.user_id == admin.id:
        raise HTTPException(400, detail="Özünüzü bloklaya bilməzsiniz")
    result = await db.execute(select(User).where(User.id == body.user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, detail="İstifadəçi tapılmadı")
    u.is_blocked = body.block
    ip, ua = get_client_info(request)
    db.add(AuditLog(
        user_id=admin.id,
        action="block" if body.block else "unblock",
        ip_address=ip, user_agent=ua,
        details=f"target={u.id}",
    ))
    return {"detail": "Bloklandı" if body.block else "Blokdan çıxarıldı"}


@router.get("/audit")
async def audit_logs(
    limit: int = 50,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    limit = min(max(limit, 1), 200)
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "action": r.action,
            "ip": r.ip_address,
            "details": r.details,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/settings")
async def update_setting(
    body: SettingUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    allowed = {
        "min_deposit", "deposit_bonus_min", "deposit_bonus_percent",
        "referral_bonus", "referral_commission_percent", "tempmail_price",
        "maintenance_mode",
    }
    if body.key not in allowed:
        raise HTTPException(400, detail="Bu açar dəyişdirilə bilməz")
    result = await db.execute(select(Setting).where(Setting.key == body.key))
    s = result.scalar_one_or_none()
    if s:
        s.value = body.value
    else:
        db.add(Setting(key=body.key, value=body.value))
    return {"detail": "Yeniləndi", "key": body.key, "value": body.value}


@router.post("/make-admin")
async def make_admin(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, detail="Tapılmadı")
    u.is_admin = True
    return {"detail": f"{u.username} indi admindir"}
