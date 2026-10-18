# Crash Number Bot — Sıfırdan GitHub + Render (addım-addım)

Bu təlimatı **sırayla** oxuyun. Hər addımı bitirmədən növbətiyə keçməyin.

---

## A) GitHub hesabı (bir dəfə)

1. Telefonda və ya komputerdə açın: https://github.com
2. **Sign up** basın
3. Email, şifrə, username yazın → təsdiq edin
4. Giriş edin

---

## B) Layihəni GitHub-a yükləmək

### Üsul 1 — Brauzerdən (ən asan, telefondan da olar)

1. GitHub-da sağ yuxarı **+** → **New repository**
2. Repository name: `crash-number-bot`
3. **Public** seçin
4. **Create repository** basın
5. Səhifədə **uploading an existing file** / **Add file → Upload files** basın
6. Komputerinizdə ZIP-i açıb **içindəki bütün faylları** (backend qovluğu, html-lər və s.) sürükləyib buraxın  
   - `backend` qovluğu da daxil olsun  
   - `venv` qovluğu **yükləməyin** (yoxdursa problem yoxdur)
7. Aşağıda **Commit changes** basın

Bitdi: repoda fayllar görünməlidir.

### Üsul 2 — Komputer + Git (istəyə bağlı)

```text
cd Desktop\Crash-Number-Bot
git init
git add .
git commit -m "first"
git branch -M main
git remote add origin https://github.com/SIZIN_USERNAME/crash-number-bot.git
git push -u origin main
```

---

## C) Render hesabı və server

1. Açın: https://render.com  
2. **Get Started** → **Sign in with GitHub** (GitHub hesabınızla bağlayın)
3. GitHub icazəsini verin (repository-ləri görmək üçün)

### Web Service yaratmaq

4. Render Dashboard → **New +** → **Web Service**
5. **Connect** yanında `crash-number-bot` repozu seçin (yoxdursa **Configure account** ilə icazə verin)
6. Ayarlar:

| Sahə | Dəyər |
|------|--------|
| Name | `crash-number-bot` |
| Region | Frankfurt (və ya ən yaxın) |
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | **Free** |

7. **Environment** (Environment Variables) əlavə edin:

| Key | Value |
|-----|--------|
| `SECRET_KEY` | Uzun random (aşağıda necə yaradılır) |
| `DEBUG` | `false` |
| `CORS_ORIGINS` | `*` |

**SECRET_KEY yaratmaq:**  
https://generate-secret.vercel.app/64  
və ya hər hansı uzun qarışıq mətn (40+ simvol).

8. **Create Web Service** basın  
9. 5–10 dəqiqə build gedir. Status **Live** olanda hazırdır.

10. Yuxarıda ünvan görünəcək, məsələn:  
    `https://crash-number-bot.onrender.com`

11. Yoxlayın:  
    `https://crash-number-bot.onrender.com/api/health`  
    `{"status":"ok"...}` görünsə OK.

API sənədi (DEBUG false olduğu üçün bağlı ola bilər). Test üçün müvəqqəti `DEBUG=true` qoya bilərsiniz.

---

## D) Admin yaratmaq (Render-də)

Render free-də shell məhdud ola bilər. Alternativ:

1. Müvəqqəti Environment-ə əlavə edin: `DEBUG` = `true`
2. Redeploy
3. Lokal komputerdən API ilə qeydiyyat:  
   `POST https://SIZIN-URL.onrender.com/api/auth/register`  
   Sonra DB-də admin etmək üçün bir dəfə lokal script və ya admin endpoint.

**Daha sadə yol:**  
Lokal komputerdə admin yaradıb SQLite faylını Render-ə yükləmək çətindir (ephemeral disk).  

Ona görə:
1. Saytdan / API-dən normal **qeydiyyat** edin  
2. Render **Shell** varsa (paid/plan):  
   `python -m scripts.create_admin`  
3. Shell yoxdursa: kodda müvəqqəti ilk istifadəçini admin etmək üçün bir dəfəlik endpoint açmaq lazımdır — istəsəniz sonradan əlavə edə bilərik.

**Praktik həll (indi):**  
Environment-ə yazın:
```
BOOTSTRAP_ADMIN_EMAIL=sizin@email.com
BOOTSTRAP_ADMIN_PASSWORD=Admin12345
```
(əgər bu funksiya kodda yoxdursa, qeydiyyatdan sonra əl ilə DB lazımdır — free Render-də SQLite restart-da silinə bilər!)

---

## E) Vacib xəbərdarlıqlar (Render Free)

1. **15 dəqiqə heç kim girməsə** server “yuxuya” gedir. İlk açılış 30–60 saniyə çəkə bilər.  
2. **SQLite məlumatları** bəzən restart/redeploy-da **sıfırlanır**. Ciddi istifadə üçün ödənişli plan + PostgreSQL lazımdır.  
3. Free plan **sınaq / demo** üçündür, real pul/depozit biznesi üçün deyil.

---

## F) Frontend (HTML) — ayrı, pulsuz

1. https://app.netlify.com → GitHub ilə giriş  
2. **Add new site → Import** → eyni repo  
3. Build settings:
   - Build command: (boş)
   - Publish directory: `.` (kök — html fayllar oradadır)
4. Deploy  
5. Ünvan: `https://random-name.netlify.app`

Sonra `js/api.js` içində:
```js
const API_BASE = "https://crash-number-bot.onrender.com";
```
və yenidən GitHub-a yükləyin / Netlify yeniləsin.

---

## G) Domain (istəyə bağlı)

1. Domain alın (Namecheap, Hostinger və s.)  
2. Netlify və ya Render-də **Custom domain** əlavə edin  
3. DNS-də CNAME / A record göstərişinə uyğun yazın  

---

## Xəta cədvəli

| Problem | Həll |
|---------|------|
| Build failed | Root Directory = `backend` olduğuna əmin olun |
| Application error | Logs-a baxın (Render → Logs) |
| CORS xətası | `CORS_ORIGINS=*` |
| Yuxudan oyanmır | 1 dəqiqə gözləyin, yenidən açın |
| Module not found | `requirements.txt` `backend` içindədir |

---

## Qısa yoxlama siyahısı

- [ ] GitHub hesabı
- [ ] Repo yaradıldı, fayllar yükləndi
- [ ] Render + GitHub bağlandı
- [ ] Web Service: Root = `backend`, Start = uvicorn ...
- [ ] SECRET_KEY əlavə olundu
- [ ] `/api/health` açılır
- [ ] (İstəyə bağlı) Netlify-də HTML

Uğurlar. Bu faylı saxlayın — `RENDER_DEPLOY.md`.
