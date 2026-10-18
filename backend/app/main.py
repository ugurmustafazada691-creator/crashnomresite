"""
KingBot API — Security-hardened FastAPI backend.
Full feature set: auth, balance, deposits, tempmail, tickets, promo, referral, admin.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.models.database import init_db
from app.routers import auth, balance, tempmail, tickets, promo, admin, referral, services

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store"
        if not settings.DEBUG:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Optional: create admin from env on first boot (Render-friendly)
    import os
    email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if email and password:
        try:
            from sqlalchemy import select
            from app.models.database import AsyncSessionLocal, User
            from app.core.security import hash_password, generate_secure_token
            async with AsyncSessionLocal() as db:
                r = await db.execute(select(User).where(User.email == email.lower()))
                if not r.scalar_one_or_none():
                    u = User(
                        username=email.split("@")[0][:30],
                        email=email.lower(),
                        password_hash=hash_password(password),
                        referral_code=generate_secure_token(8)[:10].upper(),
                        is_admin=True,
                        accepted_terms=True,
                    )
                    db.add(u)
                    await db.commit()
                    print(f"Bootstrap admin created: {email}")
        except Exception as e:
            print(f"Bootstrap admin skip: {e}")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_origins = settings.ALLOWED_ORIGINS
_cred = False if _origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_cred,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)

# Routers
app.include_router(auth.router)
app.include_router(balance.router)
app.include_router(tempmail.router)
app.include_router(tickets.router)
app.include_router(promo.router)
app.include_router(referral.router)
app.include_router(admin.router)
app.include_router(services.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if settings.DEBUG:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Daxili xəta baş verdi"})
