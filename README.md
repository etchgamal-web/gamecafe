# GameCafe

نظام إدارة كافيه ألعاب: إقلاع شبكي بدون هارد + تسجيل دخول + تايمر ومحفظة + واجهة ألعاب.

## الهيكل
- `boot/`   المرحلة 1+2: iPXE / dnsmasq / iSCSI / ZFS (على لينكس حقيقي أو VM، مش في Codespaces)
- `server/` المرحلة 3: FastAPI (مستخدمين، رصيد، جلسات)
- `client/` المرحلة 4: تطبيق العميل C# WPF (يتبني على ويندوز)
- `admin/`  المرحلة 5: لوحة التحكم React

## تشغيل السيرفر (في Codespaces)
```bash
cd server
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
```
افتح `/docs` لتجربة الـ API. الأدمن الافتراضي: `admin` / `admin123` (غيّره بمتغيرات `ADMIN_USER` و `ADMIN_PASS`).

## الفلوس
كل المبالغ أعداد صحيحة بأصغر وحدة (قرش). سعر الساعة من `RATE_PER_HOUR` (الافتراضي 1000 = 10 جنيه).
