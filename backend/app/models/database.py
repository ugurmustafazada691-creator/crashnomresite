from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, Index, UniqueConstraint, event
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import get_settings

settings = get_settings()
Base = declarative_base()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    referral_code = Column(String(20), unique=True, nullable=False, index=True)
    accepted_terms = Column(Boolean, default=False)
    total_spent = Column(Float, default=0.0)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    balance_logs = relationship("BalanceLog", back_populates="user", lazy="selectin")
    tickets = relationship("Ticket", back_populates="user", lazy="selectin")


class RefreshToken(Base):
    """Store hashed refresh tokens for rotation & revocation."""
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)


class BalanceLog(Base):
    __tablename__ = "balance_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    reason = Column(String(255), nullable=False)
    balance_after = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="balance_logs")

    __table_args__ = (Index("idx_balance_user_created", "user_id", "created_at"),)


class PendingDeposit(Base):
    __tablename__ = "pending_deposits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    method = Column(String(20), nullable=False)  # card / bep20
    receipt_hash = Column(String(64), unique=True, nullable=True)  # prevent replay
    status = Column(String(20), default="pending")  # pending / approved / rejected
    created_at = Column(DateTime(timezone=True), default=utcnow)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processed_by = Column(Integer, nullable=True)


class TempMail(Base):
    __tablename__ = "temp_mails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    login = Column(String(100), nullable=False)
    domain = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)  # mail.tm account password
    token = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    status = Column(String(20), default="active")  # active / expired / deleted
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="open")  # open / closed
    admin_reply = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="tickets")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    bonus = Column(Float, nullable=False)
    max_uses = Column(Integer, default=100)
    used_count = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class PromoUse(Base):
    __tablename__ = "promo_uses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_promo"),)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(50), primary_key=True)
    value = Column(String(255), nullable=False)


class AuditLog(Base):
    """Security audit trail for sensitive actions."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)



class ActiveNumber(Base):
    __tablename__ = "active_numbers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    activation_id = Column(String(64), nullable=False, index=True)
    phone = Column(String(32), nullable=False)
    service = Column(String(20), nullable=False)
    country = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String(20), default="wait")  # wait / ok / cancel / timeout
    sms_code = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class SmmOrder(Base):
    __tablename__ = "smm_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    external_order_id = Column(String(64), nullable=True)
    service_id = Column(Integer, nullable=False)
    link = Column(String(500), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String(40), default="Pending")
    created_at = Column(DateTime(timezone=True), default=utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
