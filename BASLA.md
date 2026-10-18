# Crash Number Bot — Nə etməlisiniz (addım-addım)

Layihə iki hissədən ibarətdir:
1. **Backend** (Python / FastAPI) — `backend/` qovluğu
2. **Frontend** (HTML) — `*.html` faylları

---

## 1. Backend-i işə salın

Komputerinizdə terminal açın:

```bash
cd backend

# Virtual mühit
python3 -m venv venv
source venv/bin/activate
# Windows: venv\Scripts\activate

# Paketlər
pip install -r requirements.txt

# .env artıq var; production üçün SECRET_KEY-i dəyişin

# İlk admin hesabı
python -m scripts.create_admin
# Email, username və güclü şifrə daxil edin

# Serveri başladın
DEBUG=true uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Açılmalıdır: **http://127.0.0.1:8000/api/docs**

---

## 2. Frontend-i açın

HTML fayllarını brauzerdə açın (və ya sadə server):

```bash
# artifacts qovluğunda
cd ..
python3 -m http.server 3000
```

Sonra: **http://127.0.0.1:3000**

`js/api.js` backend ünvanını `http://127.0.0.1:8000` kimi istifadə edir.

---

## 3. Test axını

1. `register.html` — qeydiyyat (şifrə: min 8, böyük+kiçik hərf, rəqəm)
2. `login.html` — giriş
3. Admin ilə: `create_admin` ilə yaratdığınız hesab → `admin.html`
4. Temp Mail: balansınız varsa `/api/tempmail/buy` (əvvəl admin ilə balans artırın)

Admin balans artırmaq:
- API docs-dan `POST /api/admin/balance/adjust`
- və ya frontend admin paneli

---

## 4. Real SMS / SMM üçün

`.env` faylına əlavə edin:

```
GRIZZLY_API_KEY=sizin_acariniz
MOMOPANEL_API_KEY=sizin_acariniz
```

Sonra `app/routers/services.py` içində demo əvəzinə real API çağırışları yazılmalıdır (struktur hazırdır).

---

## 5. Production (canlı server)

1. `DEBUG=false` edin
2. Güclü `SECRET_KEY` qoyun
3. HTTPS (nginx + Let's Encrypt)
4. `ALLOWED_ORIGINS`-ə öz domain-inizi yazın (`app/core/config.py`)
5. SQLite əvəzinə PostgreSQL tövsiyə olunur (böyük trafik üçün)

---

## Fayl xəritəsi

```
artifacts/
├── *.html              ← Frontend səhifələr
├── js/api.js           ← API köməkçisi
├── BASLA.md            ← Bu təlimat
└── backend/
    ├── app/            ← FastAPI kodu
    ├── scripts/create_admin.py
    ├── requirements.txt
    ├── .env
    └── README.md
```

---

## Vacib

- Botdakı köhnə API açarlarını (Telegram, Grizzly, Momopanel) **dərhal dəyişin** — onlar açıq kodda idi.
- SMS və SMM xidmətləri **pulludur**; Temp Mail pulsuzdur.
- Frontend hələ bütün düymələrdə API-yə tam bağlanmayıb; `js/api.js` və `/api/docs` ilə özünüz də bağlaya bilərsiniz.

Uğurlar.
