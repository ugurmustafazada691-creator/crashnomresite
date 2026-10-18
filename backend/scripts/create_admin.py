"""
İlk admin yaratmaq üçün:
  cd backend
  python -m scripts.create_admin
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.models.database import engine, AsyncSessionLocal, init_db, User
from app.core.security import hash_password, generate_secure_token


async def main():
    await init_db()
    email = input("Admin email: ").strip().lower() or "admin@kingbot.local"
    username = input("Admin username: ").strip().lower() or "admin"
    password = input("Admin şifrə (min 8, böyük/kiçik/rəqəm): ").strip()
    if len(password) < 8:
        print("Şifrə çox qısadır")
        return

    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(User).where((User.email == email) | (User.username == username))
        )
        if existing.scalar_one_or_none():
            print("Bu email/username artıq var. Əvvəlcə DB-ni təmizləyin və ya başqa ad seçin.")
            return
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            referral_code=generate_secure_token(8)[:10].upper(),
            is_admin=True,
            accepted_terms=True,
            balance=0.0,
        )
        db.add(user)
        await db.commit()
        print(f"✅ Admin yaradıldı: {username} ({email}) id={user.id}")


if __name__ == "__main__":
    asyncio.run(main())
