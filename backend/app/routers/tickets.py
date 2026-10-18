from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.models.database import get_db, User, Ticket
from app.dependencies import get_current_user, get_current_admin

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


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
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminReply(BaseModel):
    reply: str = Field(..., min_length=1, max_length=2000)
    close: bool = True


@router.post("/", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Limit open tickets
    open_count = await db.execute(
        select(Ticket).where(Ticket.user_id == user.id, Ticket.status == "open")
    )
    if len(open_count.scalars().all()) >= 5:
        raise HTTPException(400, detail="Maksimum 5 açıq ticket ola bilər")

    t = Ticket(user_id=user.id, subject=body.subject.strip(), message=body.message.strip())
    db.add(t)
    await db.flush()
    return t


@router.get("/", response_model=List[TicketOut])
async def my_tickets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ticket)
        .where(Ticket.user_id == user.id)
        .order_by(desc(Ticket.id))
        .limit(30)
    )
    return result.scalars().all()


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.user_id == user.id)
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, detail="Ticket tapılmadı")
    return t


# Admin
@router.get("/admin/open", response_model=List[TicketOut])
async def admin_open_tickets(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Ticket).where(Ticket.status == "open").order_by(desc(Ticket.id)).limit(50)
    )
    return result.scalars().all()


@router.post("/admin/{ticket_id}/reply", response_model=TicketOut)
async def admin_reply(
    ticket_id: int,
    body: AdminReply,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(404, detail="Ticket tapılmadı")
    t.admin_reply = body.reply.strip()
    if body.close:
        t.status = "closed"
    return t
