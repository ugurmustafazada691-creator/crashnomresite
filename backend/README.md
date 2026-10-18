# Crash Number Bot Backend — Tam funksional + güclü təhlükəsizlik

## Xüsusiyyətlər

| Modul | Endpoint | Status |
|-------|----------|--------|
| Auth (qeydiyyat/giriş/JWT) | /api/auth | Real |
| Balans + depozit | /api/balance | Real |
| Temp Mail (mail.tm) | /api/tempmail | Real |
| Ticket / dəstək | /api/tickets | Real |
| Promo kod | /api/promo | Real |
| Referal | /api/referral | Real |
| Admin panel API | /api/admin | Real |
| SMS / SMM | /api/services | Demo (API açarı ilə real) |

## Təhlükəsizlik

- bcrypt şifrə (cost 12) + güc yoxlaması
- JWT access (30 dəq) + refresh token rotation (hash DB-də)
- 5 uğursuz giriş → 15 dəq lockout
- Rate limiting (slowapi)
- Security headers (HSTS, X-Frame-Options DENY, nosniff)
- CORS yalnız icazəli origin
- Audit log
- SQLAlchemy ORM
- Production-da daxili xətalar gizlədilir

## Quraşdırma

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# SECRET_KEY dəyişin
python -m scripts.create_admin
DEBUG=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Docs: http://127.0.0.1:8000/api/docs (DEBUG=true)

## Frontend

HTML: artifacts/*.html
