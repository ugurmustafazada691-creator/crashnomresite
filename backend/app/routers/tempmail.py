import random
import string
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import httpx

from app.models.database import get_db, User, TempMail, BalanceLog, AuditLog
from app.dependencies import get_current_user, get_client_info
from app.core.config import get_settings

router = APIRouter(prefix="/api/tempmail", tags=["tempmail"])
settings = get_settings()


class TempMailOut(BaseModel):
    id: int
    email: str
    status: str
    expires_at: datetime
    created_at: datetime
    seconds_left: Optional[int] = None

    class Config:
        from_attributes = True


class MessagePreview(BaseModel):
    id: str
    subject: str
    from_address: str
    intro: str
    created_at: Optional[str] = None


class MessageFull(BaseModel):
    id: str
    subject: str
    from_address: str
    text: str
    created_at: Optional[str] = None


async def _mailtm_create() -> dict:
    """Create account on mail.tm. Returns email, password, token or raises."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(f"{settings.MAILTM_API}/domains")
        if r.status_code != 200:
            raise HTTPException(502, detail="Temp Mail xidməti əlçatan deyil")
        data = r.json()
        members = data.get("hydra:member") or data.get("member") or []
        active = [m for m in members if m.get("isActive", True) and m.get("domain")]
        if not active:
            raise HTTPException(502, detail="Aktiv domain yoxdur")
        domain = random.choice(active)["domain"]
        login = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        email = f"{login}@{domain}"
        password = "".join(random.choices(
            string.ascii_letters + string.digits, k=18
        ))
        r2 = await client.post(
            f"{settings.MAILTM_API}/accounts",
            json={"address": email, "password": password},
        )
        if r2.status_code not in (200, 201):
            raise HTTPException(502, detail="Email yaradıla bilmədi")
        r3 = await client.post(
            f"{settings.MAILTM_API}/token",
            json={"address": email, "password": password},
        )
        if r3.status_code != 200:
            raise HTTPException(502, detail="Token alına bilmədi")
        tok = r3.json().get("token")
        if not tok:
            raise HTTPException(502, detail="Token boşdur")
        return {
            "email": email,
            "login": login,
            "domain": domain,
            "password": password,
            "token": tok,
        }


async def _mailtm_messages(token: str) -> list:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{settings.MAILTM_API}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("hydra:member") or data.get("member") or []


async def _mailtm_read(token: str, msg_id: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{settings.MAILTM_API}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            return None
        return r.json()


async def _refresh_token(email: str, password: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.post(
            f"{settings.MAILTM_API}/token",
            json={"address": email, "password": password},
        )
        if r.status_code == 200:
            return r.json().get("token")
    return None


@router.post("/buy", response_model=TempMailOut, status_code=201)
async def buy_tempmail(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    price = settings.TEMPMAIL_PRICE
    if user.balance < price:
        raise HTTPException(402, detail=f"Balans kifayət deyil ({price} AZN lazımdır)")

    # Deduct first (atomic-ish)
    user.balance = round(user.balance - price, 2)
    user.total_spent = round((user.total_spent or 0) + price, 2)

    try:
        gen = await _mailtm_create()
    except HTTPException:
        user.balance = round(user.balance + price, 2)  # refund
        raise
    except Exception:
        user.balance = round(user.balance + price, 2)
        raise HTTPException(502, detail="Temp Mail yaradıla bilmədi, pul qaytarıldı")

    now = datetime.now(timezone.utc)
    tm = TempMail(
        user_id=user.id,
        email=gen["email"],
        login=gen["login"],
        domain=gen["domain"],
        password=gen["password"],
        token=gen["token"],
        price=price,
        status="active",
        expires_at=now + timedelta(seconds=settings.TEMPMAIL_TTL),
    )
    db.add(tm)
    db.add(BalanceLog(
        user_id=user.id, amount=-price,
        reason="Temp Mail", balance_after=user.balance,
    ))
    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=user.id, action="tempmail_buy", ip_address=ip, user_agent=ua,
                    details=gen["email"]))
    await db.flush()

    out = TempMailOut.model_validate(tm)
    out.seconds_left = settings.TEMPMAIL_TTL
    return out


@router.get("/list", response_model=List[TempMailOut])
async def list_tempmails(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    # Expire old ones
    result = await db.execute(
        select(TempMail).where(
            TempMail.user_id == user.id,
            TempMail.status == "active",
            TempMail.expires_at < now,
        )
    )
    for row in result.scalars().all():
        row.status = "expired"

    result = await db.execute(
        select(TempMail)
        .where(TempMail.user_id == user.id)
        .order_by(desc(TempMail.id))
        .limit(20)
    )
    items = []
    for tm in result.scalars().all():
        o = TempMailOut.model_validate(tm)
        if tm.status == "active" and tm.expires_at > now:
            o.seconds_left = int((tm.expires_at - now).total_seconds())
        else:
            o.seconds_left = 0
        items.append(o)
    return items


@router.get("/{mail_id}/messages", response_model=List[MessagePreview])
async def get_messages(
    mail_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TempMail).where(TempMail.id == mail_id, TempMail.user_id == user.id)
    )
    tm = result.scalar_one_or_none()
    if not tm:
        raise HTTPException(404, detail="Email tapılmadı")
    now = datetime.now(timezone.utc)
    if tm.status != "active" or tm.expires_at < now:
        raise HTTPException(410, detail="Bu emailin vaxtı bitib")

    token = tm.token
    msgs = await _mailtm_messages(token or "")
    if not msgs and tm.password:
        new_tok = await _refresh_token(tm.email, tm.password)
        if new_tok:
            tm.token = new_tok
            token = new_tok
            msgs = await _mailtm_messages(token)

    previews = []
    for m in msgs[:15]:
        fr = m.get("from") or {}
        addr = fr.get("address") if isinstance(fr, dict) else str(fr or "?")
        previews.append(MessagePreview(
            id=str(m.get("id", "")),
            subject=str(m.get("subject") or "(mövzusuz)")[:80],
            from_address=str(addr)[:60],
            intro=str(m.get("intro") or "")[:120],
            created_at=str(m.get("createdAt") or m.get("date") or ""),
        ))
    return previews


@router.get("/{mail_id}/messages/{msg_id}", response_model=MessageFull)
async def read_message(
    mail_id: int,
    msg_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TempMail).where(TempMail.id == mail_id, TempMail.user_id == user.id)
    )
    tm = result.scalar_one_or_none()
    if not tm:
        raise HTTPException(404, detail="Email tapılmadı")
    now = datetime.now(timezone.utc)
    if tm.status != "active" or tm.expires_at < now:
        raise HTTPException(410, detail="Bu emailin vaxtı bitib")

    token = tm.token or ""
    msg = await _mailtm_read(token, msg_id)
    if not msg and tm.password:
        new_tok = await _refresh_token(tm.email, tm.password)
        if new_tok:
            tm.token = new_tok
            msg = await _mailtm_read(new_tok, msg_id)
    if not msg:
        raise HTTPException(404, detail="Məktub oxuna bilmədi")

    body = msg.get("text") or msg.get("html") or msg.get("intro") or ""
    if isinstance(body, list):
        body = "\n".join(str(x) for x in body)
    import re
    body = re.sub(r"<[^>]+>", " ", str(body))
    body = re.sub(r"\s+", " ", body).strip()[:3000]

    fr = msg.get("from") or {}
    addr = fr.get("address") if isinstance(fr, dict) else str(fr or "?")
    return MessageFull(
        id=str(msg.get("id", msg_id)),
        subject=str(msg.get("subject") or "(mövzusuz)"),
        from_address=str(addr),
        text=body or "(boş)",
        created_at=str(msg.get("createdAt") or msg.get("date") or ""),
    )


@router.delete("/{mail_id}")
async def delete_tempmail(
    mail_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TempMail).where(TempMail.id == mail_id, TempMail.user_id == user.id)
    )
    tm = result.scalar_one_or_none()
    if not tm:
        raise HTTPException(404, detail="Tapılmadı")
    tm.status = "deleted"
    return {"detail": "Silindi"}
