"""
SMS (Grizzly) + SMM (Momopanel) — real API via environment keys only.
Keys never appear in code or logs.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.models.database import get_db, User, BalanceLog, ActiveNumber, SmmOrder, AuditLog
from app.dependencies import get_current_user, get_client_info
from app.core.config import get_settings

router = APIRouter(prefix="/api/services", tags=["services"])
settings = get_settings()


# ---------- Schemas ----------
class ServiceItem(BaseModel):
    code: str
    name: str


class CountryPrice(BaseModel):
    code: str
    name: str
    price: float  # user-facing price (AZN-style units after multiplier)


class BuySmsRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=1, max_length=10)


class ActiveNumberOut(BaseModel):
    id: int
    phone: str
    service: str
    country: str
    price: float
    status: str
    sms_code: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SmmServiceOut(BaseModel):
    service: int
    name: str
    category: str
    rate: float  # user price per 1000
    min: int
    max: int


class SmmOrderRequest(BaseModel):
    service_id: int
    link: str = Field(..., min_length=5, max_length=500)
    quantity: int = Field(..., ge=1, le=5_000_000)


class SmmOrderOut(BaseModel):
    id: int
    external_order_id: Optional[str]
    service_id: int
    link: str
    quantity: int
    price: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# Friendly names for common Grizzly service codes
SERVICE_NAMES = {
    "tg": "Telegram",
    "wa": "WhatsApp",
    "ig": "Instagram",
    "fb": "Facebook",
    "go": "Google / Gmail",
    "tw": "Twitter / X",
    "lf": "TikTok",
    "vi": "Viber",
    "ds": "Discord",
    "ok": "OK.ru",
    "vk": "VK",
    "ym": "Yandex",
    "mm": "Microsoft",
    "hw": "Alipay / Huawei",
}

COUNTRY_NAMES = {
    "0": "Rusiya",
    "1": "Ukrayna",
    "2": "Qazaxıstan",
    "12": "ABŞ",
    "16": "İngiltərə",
    "22": "Hindistan",
    "36": "Kanada",
    "43": "Almaniya",
    "46": "İsveç",
    "48": "Hollandiya",
    "62": "Türkiyə",
    "73": "Braziliya",
    "86": "İspaniya",
    "94": "Azərbaycan",
    "187": "BAE",
}


def _require_grizzly():
    if not settings.GRIZZLY_API_KEY:
        raise HTTPException(503, detail="SMS xidməti konfiqurasiya olunmayıb (GRIZZLY_API_KEY)")


def _require_momo():
    if not settings.MOMOPANEL_API_KEY:
        raise HTTPException(503, detail="SMM xidməti konfiqurasiya olunmayıb (MOMOPANEL_API_KEY)")


async def _grizzly(params: dict) -> str:
    _require_grizzly()
    q = {"api_key": settings.GRIZZLY_API_KEY, **params}
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(settings.GRIZZLY_API_URL, params=q)
        return (r.text or "").strip()


async def _momo(payload: dict) -> Any:
    _require_momo()
    data = {"key": settings.MOMOPANEL_API_KEY, **payload}
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.post(settings.MOMOPANEL_API_URL, data=data)
        try:
            return r.json()
        except Exception:
            raise HTTPException(502, detail="SMM panel cavabı oxunmadı")


# ---------- SMS ----------
@router.get("/sms/services")
async def sms_services(user: User = Depends(get_current_user)):
    # Common list; prices come per-country from getPrices
    items = [
        ServiceItem(code=c, name=n) for c, n in SERVICE_NAMES.items()
    ]
    return items


@router.get("/sms/prices/{service}", response_model=List[CountryPrice])
async def sms_prices(service: str, user: User = Depends(get_current_user)):
    """Grizzly getPrices — user price = provider * SMS_PRICE_MULTIPLIER."""
    text = await _grizzly({"action": "getPrices", "service": service})
    # Response formats vary; try JSON first
    out: List[CountryPrice] = []
    try:
        import json
        data = json.loads(text)
        # often { "0": { "cost": 1.2, ... }, ... } or nested by service
        block = data.get(service, data) if isinstance(data, dict) else {}
        if isinstance(block, dict):
            for country, info in block.items():
                if not isinstance(info, dict):
                    continue
                cost = float(info.get("cost") or info.get("price") or 0)
                if cost <= 0:
                    continue
                user_price = round(cost * settings.SMS_PRICE_MULTIPLIER, 2)
                out.append(CountryPrice(
                    code=str(country),
                    name=COUNTRY_NAMES.get(str(country), f"Ölkə {country}"),
                    price=user_price,
                ))
    except Exception:
        # fallback demo-ish empty
        pass
    out.sort(key=lambda x: x.price)
    return out[:80]


@router.post("/sms/buy", response_model=ActiveNumberOut)
async def sms_buy(
    body: BuySmsRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get price for country
    prices = await sms_prices(body.service, user)
    match = next((p for p in prices if p.code == str(body.country)), None)
    if match:
        user_price = match.price
    else:
        user_price = round(0.5 * settings.SMS_PRICE_MULTIPLIER, 2)

    if user.balance < user_price:
        raise HTTPException(402, detail=f"Balans kifayət deyil ({user_price})")

    text = await _grizzly({
        "action": "getNumber",
        "service": body.service,
        "country": body.country,
    })
    # ACCESS_NUMBER:id:phone
    if not text.startswith("ACCESS_NUMBER"):
        err_map = {
            "NO_NUMBERS": "Bu ölkədə nömrə yoxdur",
            "NO_BALANCE": "Provayder balansı bitib",
            "BAD_KEY": "SMS API açarı səhvdir",
            "BAD_SERVICE": "Xidmət kodu səhvdir",
        }
        for k, v in err_map.items():
            if k in text:
                raise HTTPException(400, detail=v)
        raise HTTPException(400, detail=f"Nömrə alına bilmədi: {text[:80]}")

    parts = text.split(":")
    if len(parts) < 3:
        raise HTTPException(502, detail="Provayder cavabı natamamdır")
    activation_id, phone = parts[1], parts[2]

    user.balance = round(user.balance - user_price, 2)
    user.total_spent = round((user.total_spent or 0) + user_price, 2)
    now = datetime.now(timezone.utc)
    row = ActiveNumber(
        user_id=user.id,
        activation_id=activation_id,
        phone=phone,
        service=body.service,
        country=str(body.country),
        price=user_price,
        status="wait",
        expires_at=now + timedelta(minutes=20),
    )
    db.add(row)
    db.add(BalanceLog(
        user_id=user.id, amount=-user_price,
        reason=f"SMS {body.service} {phone}", balance_after=user.balance,
    ))
    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=user.id, action="sms_buy", ip_address=ip, user_agent=ua,
                    details=f"{body.service}:{phone}"))
    await db.flush()
    return row


@router.get("/sms/active", response_model=List[ActiveNumberOut])
async def sms_active(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActiveNumber)
        .where(ActiveNumber.user_id == user.id)
        .order_by(desc(ActiveNumber.id))
        .limit(30)
    )
    return result.scalars().all()


@router.get("/sms/{number_id}/status", response_model=ActiveNumberOut)
async def sms_status(
    number_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActiveNumber).where(
            ActiveNumber.id == number_id, ActiveNumber.user_id == user.id
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, detail="Tapılmadı")
    if row.status in ("ok", "cancel", "timeout"):
        return row

    text = await _grizzly({
        "action": "getStatus",
        "id": row.activation_id,
    })
    # STATUS_OK:code  or STATUS_WAIT_CODE
    if text.startswith("STATUS_OK"):
        code = text.split(":")[-1] if ":" in text else text
        row.status = "ok"
        row.sms_code = code
    elif "WAIT" in text:
        row.status = "wait"
    elif "CANCEL" in text:
        row.status = "cancel"
    return row


@router.post("/sms/{number_id}/cancel")
async def sms_cancel(
    number_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ActiveNumber).where(
            ActiveNumber.id == number_id, ActiveNumber.user_id == user.id
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, detail="Tapılmadı")
    if row.status == "ok":
        raise HTTPException(400, detail="SMS artıq gəlib, ləğv olmaz")
    await _grizzly({"action": "setStatus", "status": "8", "id": row.activation_id})
    row.status = "cancel"
    # optional partial refund policy — here no auto refund
    return {"detail": "Ləğv edildi"}


# ---------- SMM ----------
@router.get("/smm/list", response_model=List[SmmServiceOut])
async def smm_list(user: User = Depends(get_current_user)):
    data = await _momo({"action": "services"})
    if not isinstance(data, list):
        raise HTTPException(502, detail="SMM xidmət siyahısı alınmadı")
    out = []
    for s in data[:300]:
        try:
            rate = float(s.get("rate") or 0) * settings.SMM_PRICE_MULTIPLIER
            out.append(SmmServiceOut(
                service=int(s["service"]),
                name=str(s.get("name") or ""),
                category=str(s.get("category") or ""),
                rate=round(rate, 4),
                min=int(s.get("min") or 1),
                max=int(s.get("max") or 10000),
            ))
        except Exception:
            continue
    return out


@router.post("/smm/order", response_model=SmmOrderOut)
async def smm_order(
    body: SmmOrderRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    services = await smm_list(user)
    svc = next((s for s in services if s.service == body.service_id), None)
    if not svc:
        raise HTTPException(404, detail="Xidmət tapılmadı")
    if body.quantity < svc.min or body.quantity > svc.max:
        raise HTTPException(400, detail=f"Miqdar {svc.min}–{svc.max} arası olmalıdır")

    price = round(svc.rate * (body.quantity / 1000.0), 2)
    if price < 0.01:
        price = 0.01
    if user.balance < price:
        raise HTTPException(402, detail=f"Balans kifayət deyil ({price})")

    resp = await _momo({
        "action": "add",
        "service": body.service_id,
        "link": body.link,
        "quantity": body.quantity,
    })
    if not isinstance(resp, dict) or "order" not in resp:
        err = resp.get("error") if isinstance(resp, dict) else str(resp)[:100]
        raise HTTPException(400, detail=f"Sifariş alınmadı: {err}")

    user.balance = round(user.balance - price, 2)
    user.total_spent = round((user.total_spent or 0) + price, 2)
    row = SmmOrder(
        user_id=user.id,
        external_order_id=str(resp["order"]),
        service_id=body.service_id,
        link=body.link,
        quantity=body.quantity,
        price=price,
        status="Pending",
    )
    db.add(row)
    db.add(BalanceLog(
        user_id=user.id, amount=-price,
        reason=f"SMM #{resp['order']}", balance_after=user.balance,
    ))
    ip, ua = get_client_info(request)
    db.add(AuditLog(user_id=user.id, action="smm_order", ip_address=ip, user_agent=ua,
                    details=str(resp["order"])))
    await db.flush()
    return row


@router.get("/smm/orders", response_model=List[SmmOrderOut])
async def smm_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SmmOrder).where(SmmOrder.user_id == user.id)
        .order_by(desc(SmmOrder.id)).limit(40)
    )
    return result.scalars().all()


@router.get("/smm/orders/{order_id}/status")
async def smm_status(
    order_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SmmOrder).where(SmmOrder.id == order_id, SmmOrder.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if not row or not row.external_order_id:
        raise HTTPException(404, detail="Tapılmadı")
    resp = await _momo({"action": "status", "order": row.external_order_id})
    if isinstance(resp, dict) and "status" in resp:
        row.status = str(resp["status"])
    return {"local": SmmOrderOut.model_validate(row), "provider": resp}
