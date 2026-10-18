# Crash Number Bot

Telegram bot xüsusiyyətlərinin veb versiyası.

## Render-ə deploy

`RENDER_DEPLOY.md` faylına baxın — sıfırdan GitHub + Render.

## Lokal

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
