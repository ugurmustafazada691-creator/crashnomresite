from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List
import secrets


class Settings(BaseSettings):
    APP_NAME: str = "Crash Number Bot"
    APP_ENV: str = "production"
    DEBUG: bool = False

    SECRET_KEY: str = secrets.token_urlsafe(64)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    DATABASE_URL: str = "sqlite+aiosqlite:///./kingbot.db"

    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_SENSITIVE: str = "5/minute"

    MIN_PASSWORD_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15

    CORS_ORIGINS: str = "*"

    TEMPMAIL_PRICE: float = 0.10
    TEMPMAIL_TTL: int = 3600
    MAILTM_API: str = "https://api.mail.tm"

    # --- External APIs (ONLY from environment — never hardcode keys) ---
    GRIZZLY_API_KEY: str = ""
    GRIZZLY_API_URL: str = "https://api.grizzlysms.com/stubs/handler_api.php"
    SMS_PRICE_MULTIPLIER: float = 4.61  # user price = provider * multiplier

    MOMOPANEL_API_KEY: str = ""
    MOMOPANEL_API_URL: str = "https://momopanel.com/api/v2"
    SMM_PRICE_MULTIPLIER: float = 1.5

    MIN_DEPOSIT: float = 3.0
    DEPOSIT_BONUS_MIN: float = 10.0
    DEPOSIT_BONUS_PERCENT: float = 5.0
    REFERRAL_BONUS: float = 0.03
    REFERRAL_COMMISSION_PERCENT: float = 3.0
    MAX_PAID_REFERRALS: int = 50
    USER_LOW_BALANCE: float = 0.50

    SUPER_ADMIN_EMAIL: str = "admin@kingbot.local"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
